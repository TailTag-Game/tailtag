package app.tailtag.tailtag_clerk

import android.content.Context
import com.clerk.api.Clerk
import com.clerk.api.ClerkConfigurationOptions
import com.clerk.api.network.model.error.ClerkErrorResponse
import com.clerk.api.network.serialization.ClerkResult
import com.clerk.api.session.GetTokenOptions
import com.clerk.api.session.Session
import com.clerk.api.signin.SignIn
import com.clerk.api.signin.verifyCode
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
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

/**
 * Forwards the Dart bridge calls to the Clerk Android SDK and maps its errors.
 *
 * Nothing here logs, and no token, email address, error message, or Clerk identifier goes into a
 * Flutter error or a state event. A failure leaves this file as one of five error codes and
 * nothing else.
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
        scope.cancel()
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
                }
                return null
            }
            "startEmailCode" -> {
                val emailAddress = call.argument<String>("emailAddress") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                unwrap(Clerk.auth.signInWithOtp { email = emailAddress })
                return null
            }
            "verifyCode" -> {
                val code = call.argument<String>("code") ?: throw Failure(UNEXPECTED)
                requireConfigured()
                val signIn = Clerk.auth.currentSignIn ?: throw Failure(UNEXPECTED)
                if (unwrap(signIn.verifyCode(code)).status != SignIn.Status.COMPLETE) {
                    throw Failure(UNEXPECTED)
                }
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
                unwrap(Clerk.auth.signOut())
                return null
            }
            else -> throw NotImplemented()
        }
    }

    private fun requireConfigured() {
        if (!configured) throw Failure(UNEXPECTED)
    }

    // State channel

    override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
        stateJob?.cancel()
        stateJob =
            combine(Clerk.isInitialized, Clerk.sessionFlow) { initialized, session ->
                    when {
                        !initialized -> "loading"
                        session?.status == Session.SessionStatus.ACTIVE -> "signedIn"
                        else -> "signedOut"
                    }
                }
                .distinctUntilChanged()
                .onEach { events.success(it) }
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
        return when (failure.error?.errors?.firstOrNull()?.code) {
            "form_code_incorrect",
            "verification_expired" -> INVALID_CODE
            "authentication_invalid",
            "signed_out",
            "resource_not_found",
            "session_token_request_superseded" -> SESSION_ENDED
            else -> UNEXPECTED
        }
    }

    private fun errorCode(error: Exception): String =
        when (error) {
            is Failure -> error.code
            is IOException -> CONNECTIVITY
            else -> UNEXPECTED
        }

    private companion object {
        const val CONNECTIVITY = "connectivity"
        const val INVALID_CODE = "invalidCode"
        const val SESSION_ENDED = "sessionEnded"
        const val UNEXPECTED = "unexpected"
    }
}
