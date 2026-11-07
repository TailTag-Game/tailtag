package app.tailtag.tailtag_clerk

import android.app.Activity
import android.content.Context
import android.os.Build
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.exceptions.CreateCredentialException
import androidx.credentials.exceptions.CreateCredentialUnsupportedException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.GetCredentialUnsupportedException
import com.clerk.api.Clerk
import com.clerk.api.ClerkConfigurationOptions
import com.clerk.api.auth.types.VerificationType
import com.clerk.api.credentials.shouldSuppressAutomaticCredentialFlowError
import com.clerk.api.credentials.shouldSuppressCredentialFlowError
import com.clerk.api.network.model.verification.Verification
import com.clerk.api.network.model.error.ClerkErrorResponse
import com.clerk.api.network.serialization.ClerkResult
import com.clerk.api.passkeys.Passkey
import com.clerk.api.passkeys.delete
import com.clerk.api.session.GetTokenOptions
import com.clerk.api.session.Session
import com.clerk.api.signin.SignIn
import com.clerk.api.signin.sendEmailCode
import com.clerk.api.signin.verifyCode
import com.clerk.api.signup.SignUp
import com.clerk.api.signup.sendEmailCode
import com.clerk.api.signup.verifyCode
import com.clerk.api.sso.OAuthResult
import com.clerk.api.user.User
import com.clerk.api.user.createPasskey
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Forwards the Dart bridge calls to the Clerk Android SDK and maps its errors.
 *
 * Nothing here logs, and no token, email address, error message, or Clerk identifier goes into a
 * Flutter error or a state event. A failure leaves this file as one error code and nothing else.
 *
 * An email code belongs to one bound attempt: the sign-in or sign-up that the last start call or
 * Google call created. Resend and verify act only on that attempt. A new start, a Google call, or a
 * sign-out ends it.
 *
 * Google uses Clerk's Credential Manager flow, which needs the current Activity. The plugin hands
 * the Activity to Clerk, because Clerk starts after the Activity has resumed and so misses the
 * lifecycle callback that would tell it. Google never falls back to browser OAuth here.
 *
 * Passkeys use the same Credential Manager flow and need Android 9 (API 28). Passkey sign-in always
 * allows the full system sheet, so it can offer a passkey from another device. The passkey list holds
 * only verified passkeys: Clerk creates a passkey before the sheet opens and never removes it after
 * a cancel. A passkey ID leaves this file only in the list and only to name a removal.
 */
class TailTagClerkPlugin :
    FlutterPlugin,
    ActivityAware,
    MethodChannel.MethodCallHandler,
    EventChannel.StreamHandler {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var context: Context? = null
    private var activity: Activity? = null
    private var methods: MethodChannel? = null
    private var states: EventChannel? = null
    private var stateJob: Job? = null
    private var configured = false
    private var startupWatch: Job? = null

    /** True when the SDK stayed uninitialized too long with no startup error. */
    private val startupTimedOut = MutableStateFlow(false)
    private var boundSignIn: SignIn? = null
    private var boundSignUp: SignUp? = null

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        methods = MethodChannel(binding.binaryMessenger, "app.tailtag/clerk").also {
            it.setMethodCallHandler(this)
        }
        states = EventChannel(binding.binaryMessenger, "app.tailtag/clerk/state").also {
            it.setStreamHandler(this)
        }
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        methods?.setMethodCallHandler(null)
        states?.setStreamHandler(null)
        stateJob?.cancel()
        startupWatch?.cancel()
        // Cancel only the children: Flutter can attach this instance to an engine again.
        scope.coroutineContext.cancelChildren()
        clearBinding()
        context = null
    }

    // Activity

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
        Clerk.attachActivity(binding.activity)
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        onAttachedToActivity(binding)
    }

    override fun onDetachedFromActivityForConfigChanges() {
        activity = null
    }

    override fun onDetachedFromActivity() {
        activity = null
    }

    // Method channel

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        scope.launch {
            try {
                result.success(perform(call))
            } catch (error: NotImplemented) {
                result.notImplemented()
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                result.error(errorCode(error), null, null)
            }
        }
    }

    private suspend fun perform(call: MethodCall): Any? {
        when (call.method) {
            "configure" -> {
                val publishableKey = call.argument<String>("publishableKey") ?: throw Failure(UNEXPECTED)
                if (!configured) {
                    val appContext = context ?: throw Failure(UNEXPECTED)
                    Clerk.initialize(
                        appContext,
                        publishableKey,
                        ClerkConfigurationOptions(enableDebugMode = false, telemetryEnabled = false),
                    )
                    configured = true
                    activity?.let(Clerk::attachActivity)
                    watchStartup()
                }
                return null
            }
            "startEmailSignIn" -> {
                val emailAddress = call.argument<String>("emailAddress") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                clearBinding()
                // signInWithOtp creates the sign-in and sends the code.
                boundSignIn = unwrap(Clerk.auth.signInWithOtp { email = emailAddress })
                return null
            }
            "startEmailSignUp" -> {
                val emailAddress = call.argument<String>("emailAddress") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                clearBinding()
                val created = unwrap(Clerk.auth.signUp { email = emailAddress })
                boundSignUp = created
                boundSignUp = unwrap(created.sendEmailCode())
                return null
            }
            "resendEmailCode" -> {
                requireConfigured()
                val signIn = boundSignIn
                val signUp = boundSignUp
                when {
                    signIn != null -> boundSignIn = unwrap(signIn.sendEmailCode())
                    signUp != null -> boundSignUp = unwrap(signUp.sendEmailCode())
                    else -> throw Failure(SESSION_ENDED)
                }
                return null
            }
            "verifyEmailCode" -> {
                val code = call.argument<String>("code") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                val signIn = boundSignIn
                val signUp = boundSignUp
                val complete =
                    when {
                        signIn != null ->
                            unwrap(signIn.verifyCode(code)).also { boundSignIn = it }.status ==
                                SignIn.Status.COMPLETE
                        signUp != null ->
                            unwrap(signUp.verifyCode(code, VerificationType.EMAIL))
                                .also { boundSignUp = it }
                                .status == SignUp.Status.COMPLETE
                        else -> throw Failure(SESSION_ENDED)
                    }
                // Success needs a complete attempt and an active session, not only a verified code.
                if (!complete || Clerk.session?.status != Session.SessionStatus.ACTIVE) {
                    throw Failure(UNEXPECTED)
                }
                clearBinding()
                return COMPLETED
            }
            "continueWithGoogle" -> {
                requireConfigured()
                clearBinding()
                val oauth =
                    when (val result = Clerk.auth.signInWithGoogleOneTap(transferable = true)) {
                        is ClerkResult.Success -> result.value
                        is ClerkResult.Failure -> {
                            if (result.shouldSuppressCredentialFlowError) {
                                return CANCELLED
                            }
                            throw Failure(googleFailureCode(result))
                        }
                    }
                return googleOutcome(oauth)
            }
            "passkeyAvailability" -> {
                if (!configured) return false
                return passkeysSupported() && Clerk.passkeyFirstFactorIsEnabled
            }
            "signInWithPasskey" -> {
                requireConfigured()
                clearBinding()
                if (!passkeysSupported()) throw Failure(PASSKEY_UNAVAILABLE)
                val signIn =
                    when (
                        val result =
                            Clerk.auth.signInWithPasskey(preferImmediatelyAvailableCredentials = false)
                    ) {
                        is ClerkResult.Success -> result.value
                        is ClerkResult.Failure -> {
                            if (result.shouldSuppressCredentialFlowError) return CANCELLED
                            throw Failure(passkeyFailureCode(result))
                        }
                    }
                if (signIn.status != SignIn.Status.COMPLETE) throw Failure(UNEXPECTED)
                return completedIfActive()
            }
            "createPasskey" -> {
                requireConfigured()
                if (!passkeysSupported()) throw Failure(PASSKEY_UNAVAILABLE)
                val passkey =
                    when (val result = activeUser().createPasskey()) {
                        is ClerkResult.Success -> result.value
                        is ClerkResult.Failure -> {
                            if (result.shouldSuppressCredentialFlowError) return CANCELLED
                            throw Failure(passkeyFailureCode(result))
                        }
                    }
                // Success needs Clerk's acknowledgement of a verified passkey.
                if (!passkey.isVerified()) throw Failure(UNEXPECTED)
                return COMPLETED
            }
            "listPasskeys" -> {
                requireConfigured()
                return verifiedPasskeys(refreshedUser()).map {
                    mapOf(
                        "id" to it.id,
                        "name" to it.name,
                        "createdAt" to it.createdAt,
                        "lastUsedAt" to it.lastUsedAt,
                    )
                }
            }
            "passkeyRemovalFacts" -> {
                val passkeyId = call.argument<String>("passkeyId") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                val user = refreshedUser()
                val passkeys = verifiedPasskeys(user)
                if (passkeys.none { it.id == passkeyId }) throw Failure(UNEXPECTED)
                // Facts only: the Dart session applies the last-method rule. Android has no Apple.
                return mapOf(
                    "otherVerifiedPasskey" to passkeys.any { it.id != passkeyId },
                    "verifiedEmail" to
                        user.emailAddresses.orEmpty().any { it.verification.isVerified() },
                    // Android exposes the attribute, not the strategy. The Development instance
                    // allows email codes as the only email first factor (#476).
                    "emailCodeEnabled" to Clerk.enabledFirstFactorAttributes.contains(EMAIL_ADDRESS),
                    "verifiedGoogle" to
                        user.externalAccounts.orEmpty().any {
                            it.provider in GOOGLE_PROVIDERS && it.verification.isVerified()
                        },
                    "googleEnabled" to Clerk.isGoogleOneTapEnabled,
                    "verifiedApple" to false,
                    "appleEnabled" to false,
                )
            }
            "removePasskey" -> {
                val passkeyId = call.argument<String>("passkeyId") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                val passkey =
                    verifiedPasskeys(activeUser()).firstOrNull { it.id == passkeyId }
                        ?: throw Failure(UNEXPECTED)
                unwrap(passkey.delete())
                return null
            }
            "reload" -> {
                requireConfigured()
                reload()
                return null
            }
            "getToken" -> {
                requireConfigured()
                if (Clerk.session?.status != Session.SessionStatus.ACTIVE) return null
                val skipCache = call.argument<Boolean>("skipCache") ?: false
                return unwrap(Clerk.auth.getToken(GetTokenOptions(skipCache = skipCache)))
            }
            "signOut" -> {
                requireConfigured()
                clearBinding()
                try {
                    unwrap(Clerk.auth.signOut())
                } finally {
                    // Credential Manager auto-selects the last Google account. Once the SDK has
                    // no active session, clear that state so the next player can choose.
                    if (Clerk.session?.status != Session.SessionStatus.ACTIVE) {
                        clearGoogleCredentialState()
                    }
                }
                return null
            }
            else -> throw NotImplemented()
        }
    }

    /**
     * Maps a Google result to a TailTag result name. `completed` needs a complete attempt and an
     * active session. An attempt that needs an email code binds this plugin and has a sent code.
     */
    private suspend fun googleOutcome(oauth: OAuthResult): String {
        val signUp = oauth.signUp
        val signIn = oauth.signIn
        // A transfer to a new account carries the sign-up, which then decides the outcome.
        return when {
            signUp != null -> signUpOutcome(signUp)
            signIn != null -> signInOutcome(signIn)
            else -> throw Failure(UNEXPECTED)
        }
    }

    private suspend fun signInOutcome(signIn: SignIn): String =
        when (signIn.status) {
            SignIn.Status.COMPLETE -> completedIfActive()
            SignIn.Status.NEEDS_FIRST_FACTOR -> {
                boundSignIn = preparedSignInCode(signIn)
                NEEDS_EMAIL_CODE
            }
            else -> throw Failure(UNEXPECTED)
        }

    private suspend fun signUpOutcome(signUp: SignUp): String =
        when (signUp.status) {
            SignUp.Status.COMPLETE -> completedIfActive()
            SignUp.Status.MISSING_REQUIREMENTS -> {
                if (signUp.missingFields.isNotEmpty() || signUp.unverifiedFields != listOf(EMAIL_ADDRESS)) {
                    throw Failure(UNEXPECTED)
                }
                val verification = signUp.verifications[EMAIL_ADDRESS]
                boundSignUp =
                    if (verification.isPreparedEmailCode()) signUp else unwrap(signUp.sendEmailCode())
                NEEDS_EMAIL_CODE
            }
            else -> throw Failure(UNEXPECTED)
        }

    /** The sign-in with a sent email code. It sends the code when Clerk has not sent it yet. */
    private suspend fun preparedSignInCode(signIn: SignIn): SignIn {
        if (signIn.firstFactorVerification.isPreparedEmailCode()) return signIn
        val factor =
            signIn.supportedFirstFactors?.firstOrNull {
                it.strategy == EMAIL_CODE && it.emailAddressId != null
            } ?: throw Failure(UNEXPECTED)
        return unwrap(signIn.sendEmailCode(factor.emailAddressId))
    }

    private fun Verification?.isPreparedEmailCode(): Boolean =
        this != null && strategy == EMAIL_CODE && status == Verification.Status.UNVERIFIED

    /** Clerk's Android passkey guide requires Android 9 (API 28). */
    private fun passkeysSupported(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P

    /** The signed-in user, or `sessionEnded` when no session is active. */
    private fun activeUser(): User {
        if (Clerk.session?.status != Session.SessionStatus.ACTIVE) throw Failure(SESSION_ENDED)
        return Clerk.user ?: throw Failure(SESSION_ENDED)
    }

    /** The signed-in user after a fresh client read. */
    private suspend fun refreshedUser(): User {
        unwrap(Clerk.refreshClient())
        return activeUser()
    }

    private fun verifiedPasskeys(user: User): List<Passkey> =
        user.passkeys.orEmpty().filter { it.isVerified() }

    private fun Passkey.isVerified(): Boolean = verification.isVerified()

    private fun Verification?.isVerified(): Boolean = this?.status == Verification.Status.VERIFIED

    private fun completedIfActive(): String {
        if (Clerk.session?.status != Session.SessionStatus.ACTIVE) throw Failure(UNEXPECTED)
        return COMPLETED
    }

    /** Clears Credential Manager state. A failure is ignored: it never changes the sign-out result. */
    private suspend fun clearGoogleCredentialState() {
        val appContext = context ?: return
        try {
            // A hung Play services call must not hold the sign-out result.
            withTimeoutOrNull(CLEAR_CREDENTIAL_TIMEOUT_MS) {
                CredentialManager.create(appContext)
                    .clearCredentialState(ClearCredentialStateRequest())
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            // Ignored on purpose.
        }
    }

    /**
     * Starts the SDK again without clearing its storage, then waits until it loads or reports a new
     * startup error.
     */
    private suspend fun reload() {
        // Watch again, so a reload that never initializes still ends in a reported failure.
        watchStartup()
        val previousError = Clerk.initializationError.value
        if (!Clerk.reinitialize()) throw Failure(UNEXPECTED)
        activity?.let(Clerk::attachActivity)
        val outcome =
            withTimeoutOrNull(RELOAD_TIMEOUT_MS) {
                combine(Clerk.isInitialized, Clerk.initializationError) { initialized, error ->
                        initialized to error
                    }
                    .first { (initialized, error) ->
                        initialized || (error != null && error !== previousError)
                    }
            } ?: throw Failure(UNEXPECTED)
        val error = outcome.second
        if (!outcome.first && error != null) throw Failure(startupErrorCode(error))
    }

    /**
     * Reports a startup failure when the SDK has not initialized in time and has reported no error.
     * The SDK can keep retrying on its own without setting an error.
     */
    private fun watchStartup() {
        startupWatch?.cancel()
        startupTimedOut.value = false
        startupWatch =
            scope.launch {
                delay(STARTUP_TIMEOUT_MS)
                if (!Clerk.isInitialized.value) startupTimedOut.value = true
            }
    }

    private fun requireConfigured() {
        if (!configured) throw Failure(UNEXPECTED)
    }

    private fun clearBinding() {
        boundSignIn = null
        boundSignUp = null
    }

    // State channel

    override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
        stateJob?.cancel()
        stateJob =
            combine(
                    Clerk.isInitialized,
                    Clerk.sessionFlow,
                    Clerk.initializationError,
                    startupTimedOut,
                ) { initialized, session, error, timedOut ->
                    when {
                        !initialized && error != null -> FAILED_PREFIX + startupErrorCode(error)
                        !initialized && timedOut -> FAILED_PREFIX + UNEXPECTED
                        !initialized -> "loading"
                        session?.status == Session.SessionStatus.ACTIVE -> "signedIn"
                        else -> "signedOut"
                    }
                }
                .distinctUntilChanged()
                .onEach {
                    if (it.startsWith(FAILED_PREFIX)) {
                        events.error(it.removePrefix(FAILED_PREFIX), null, null)
                    } else {
                        events.success(it)
                    }
                }
                .launchIn(scope)
    }

    override fun onCancel(arguments: Any?) {
        stateJob?.cancel()
        stateJob = null
    }

    // Error mapping

    private class Failure(val code: String) : Exception()

    private class NotImplemented : Exception()

    private fun <T : Any> unwrap(result: ClerkResult<T, ClerkErrorResponse>): T =
        when (result) {
            is ClerkResult.Success -> result.value
            is ClerkResult.Failure -> throw Failure(failureCode(result))
        }

    private fun failureCode(failure: ClerkResult.Failure<ClerkErrorResponse>): String {
        if (failure.throwable is IOException) return CONNECTIVITY
        if (failure.code == HTTP_TOO_MANY_REQUESTS) return RATE_LIMITED
        return when (failure.error?.errors?.firstOrNull()?.code) {
            "form_code_incorrect",
            "verification_expired",
            "verification_failed" -> INVALID_CODE
            "too_many_requests" -> RATE_LIMITED
            "form_identifier_exists" -> ACCOUNT_EXISTS
            "form_identifier_not_found" -> ACCOUNT_NOT_FOUND
            "session_reverification_required" -> REVERIFICATION_REQUIRED
            "authentication_invalid",
            "signed_out",
            "resource_not_found",
            "session_token_request_superseded" -> SESSION_ENDED
            else -> UNEXPECTED
        }
    }

    /**
     * Credential Manager outcomes first, then the shared Clerk table. Never browser OAuth.
     *
     * Clerk 1.2.1 keeps its CredentialFlowException types internal to Kotlin, so the plugin reads
     * Clerk's public flags. Clerk turns the Credential Manager failures that it knows into its own
     * types: no Google account, no saved credential, provider unavailable, or a missing Activity.
     * Those are `providerUnavailable`. A raw GetCredentialException is one that Clerk did not
     * classify, such as an interrupted or unknown failure, so it is `unexpected`. API and network
     * failures use the shared table.
     */
    private fun googleFailureCode(failure: ClerkResult.Failure<ClerkErrorResponse>): String =
        when {
            failure.throwable is GetCredentialException -> UNEXPECTED
            failure.shouldSuppressAutomaticCredentialFlowError -> PROVIDER_UNAVAILABLE
            else -> failureCode(failure)
        }

    /**
     * Credential Manager outcomes for passkeys, then the shared Clerk table. The caller has already
     * mapped a cancellation. An unsupported request is `passkeyUnavailable`. Another raw
     * Credential Manager failure, such as an interrupted one, is `unexpected`. Clerk's own types (no
     * saved credential, provider unavailable, or a missing Activity) are `passkeyUnavailable`.
     */
    private fun passkeyFailureCode(failure: ClerkResult.Failure<ClerkErrorResponse>): String =
        when (failure.throwable) {
            is GetCredentialUnsupportedException,
            is CreateCredentialUnsupportedException -> PASSKEY_UNAVAILABLE
            is GetCredentialException,
            is CreateCredentialException -> UNEXPECTED
            else ->
                if (failure.shouldSuppressAutomaticCredentialFlowError) {
                    PASSKEY_UNAVAILABLE
                } else {
                    failureCode(failure)
                }
        }

    private fun startupErrorCode(error: Throwable): String =
        if (error is IOException) CONNECTIVITY else UNEXPECTED

    private fun errorCode(error: Exception): String =
        when (error) {
            is Failure -> error.code
            is IOException -> CONNECTIVITY
            else -> UNEXPECTED
        }

    private companion object {
        const val COMPLETED = "completed"
        const val CANCELLED = "cancelled"
        const val NEEDS_EMAIL_CODE = "needsEmailCode"
        const val PROVIDER_UNAVAILABLE = "providerUnavailable"
        const val PASSKEY_UNAVAILABLE = "passkeyUnavailable"
        const val REVERIFICATION_REQUIRED = "reverificationRequired"
        const val EMAIL_CODE = "email_code"
        const val EMAIL_ADDRESS = "email_address"
        const val CONNECTIVITY = "connectivity"
        const val INVALID_CODE = "invalidCode"
        const val SESSION_ENDED = "sessionEnded"
        const val RATE_LIMITED = "rateLimited"
        const val ACCOUNT_EXISTS = "accountExists"
        const val ACCOUNT_NOT_FOUND = "accountNotFound"
        const val UNEXPECTED = "unexpected"
        const val FAILED_PREFIX = "failed:"
        // The SDK documents `google`, and its sample data uses `oauth_google`. The #480 live proof
        // records the value that a device reports.
        val GOOGLE_PROVIDERS = setOf("google", "oauth_google")
        const val HTTP_TOO_MANY_REQUESTS = 429
        const val RELOAD_TIMEOUT_MS = 20_000L
        const val STARTUP_TIMEOUT_MS = 20_000L
        const val CLEAR_CREDENTIAL_TIMEOUT_MS = 5_000L
    }
}
