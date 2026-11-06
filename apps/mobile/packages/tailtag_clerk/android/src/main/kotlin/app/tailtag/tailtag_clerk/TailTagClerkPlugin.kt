package app.tailtag.tailtag_clerk

import android.content.Context
import com.clerk.api.Clerk
import com.clerk.api.ClerkConfigurationOptions
import com.clerk.api.auth.types.VerificationType
import com.clerk.api.network.model.error.ClerkErrorResponse
import com.clerk.api.network.serialization.ClerkResult
import com.clerk.api.session.GetTokenOptions
import com.clerk.api.session.Session
import com.clerk.api.signin.SignIn
import com.clerk.api.signin.sendEmailCode
import com.clerk.api.signin.verifyCode
import com.clerk.api.signup.SignUp
import com.clerk.api.signup.sendEmailCode
import com.clerk.api.signup.verifyCode
import io.flutter.embedding.engine.plugins.FlutterPlugin
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
 * An email code belongs to one bound attempt: the sign-in or sign-up that the last start call
 * created. Resend and verify act only on that attempt. A new start or a sign-out ends it.
 */
class TailTagClerkPlugin :
    FlutterPlugin,
    MethodChannel.MethodCallHandler,
    EventChannel.StreamHandler {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var context: Context? = null
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
                unwrap(Clerk.auth.signOut())
                return null
            }
            else -> throw NotImplemented()
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
            "authentication_invalid",
            "signed_out",
            "resource_not_found",
            "session_token_request_superseded" -> SESSION_ENDED
            else -> UNEXPECTED
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
        const val CONNECTIVITY = "connectivity"
        const val INVALID_CODE = "invalidCode"
        const val SESSION_ENDED = "sessionEnded"
        const val RATE_LIMITED = "rateLimited"
        const val ACCOUNT_EXISTS = "accountExists"
        const val ACCOUNT_NOT_FOUND = "accountNotFound"
        const val UNEXPECTED = "unexpected"
        const val FAILED_PREFIX = "failed:"
        const val HTTP_TOO_MANY_REQUESTS = 429
        const val RELOAD_TIMEOUT_MS = 20_000L
        const val STARTUP_TIMEOUT_MS = 20_000L
    }
}
