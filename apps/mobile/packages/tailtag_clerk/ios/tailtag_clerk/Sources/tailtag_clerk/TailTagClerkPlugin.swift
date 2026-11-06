import AuthenticationServices
import ClerkKit
import Flutter
import Foundation
import Observation

/// Forwards the Dart bridge calls to the Clerk iOS SDK and maps its errors.
///
/// Nothing here logs, and no token, email address, error message, or Clerk
/// identifier goes into a `FlutterError` or a state event. A failure leaves
/// this file as one error code and nothing else.
///
/// An email code belongs to one bound attempt: the sign-in or sign-up that the
/// last start call or Google call created. Resend and verify act only on that
/// attempt. A new start, a Google call, or a sign-out ends it.
///
/// Google uses the SDK-owned browser session (`ASWebAuthenticationSession`).
/// The session is ephemeral, so it keeps no Safari cookies after sign-out.
/// ClerkKit consumes the `app.tailtag://callback` redirect inside that
/// session, so the Runner registers no URL scheme.
public final class TailTagClerkPlugin: NSObject, FlutterPlugin, FlutterStreamHandler {
    /// How long the SDK can stay unloaded after `configure` before the bridge
    /// reports a startup failure. ClerkKit 1.6.1 retries its startup refresh
    /// three times and then only logs (`ClerkRuntime.swift`).
    private static let startupTimeout: Duration = .seconds(20)

    private var eventSink: FlutterEventSink?
    private var lastSentState: String?
    private var configured = false
    private var startupFailure: String?
    private var startupWatch: Task<Void, Never>?
    private var boundSignIn: SignIn?
    private var boundSignUp: SignUp?

    public static func register(with registrar: FlutterPluginRegistrar) {
        let instance = TailTagClerkPlugin()
        let methods = FlutterMethodChannel(
            name: "app.tailtag/clerk", binaryMessenger: registrar.messenger())
        registrar.addMethodCallDelegate(instance, channel: methods)
        let states = FlutterEventChannel(
            name: "app.tailtag/clerk/state", binaryMessenger: registrar.messenger())
        states.setStreamHandler(instance)
    }

    // MARK: Method channel

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        let method = call.method
        let arguments = call.arguments as? [String: Any]
        Task { @MainActor in
            do {
                result(try await self.perform(method, arguments))
            } catch BridgeError.notImplemented {
                result(FlutterMethodNotImplemented)
            } catch {
                result(FlutterError(code: Self.errorCode(for: error), message: nil, details: nil))
            }
        }
    }

    @MainActor
    private func perform(_ method: String, _ arguments: [String: Any]?) async throws -> Any? {
        switch method {
        case "configure":
            guard let publishableKey = arguments?["publishableKey"] as? String else {
                throw BridgeError.unexpected
            }
            if !configured {
                // `Clerk.configure` does not throw on a malformed key. It asserts in debug
                // builds and leaves the shared instance unset, so check the key first.
                guard Self.isValidPublishableKey(publishableKey) else {
                    throw BridgeError.unexpected
                }
                Clerk.configure(
                    publishableKey: publishableKey,
                    options: .init(logLevel: .error, telemetryEnabled: false))
                configured = true
                observeState()
                watchStartup()
            }
            return nil
        case "startEmailSignIn":
            guard let emailAddress = arguments?["emailAddress"] as? String, configured else {
                throw BridgeError.unexpected
            }
            clearBinding()
            // signInWithEmailCode creates the sign-in and sends the code.
            boundSignIn = try await Clerk.shared.auth.signInWithEmailCode(emailAddress: emailAddress)
            return nil
        case "startEmailSignUp":
            guard let emailAddress = arguments?["emailAddress"] as? String, configured else {
                throw BridgeError.unexpected
            }
            clearBinding()
            let created = try await Clerk.shared.auth.signUp(emailAddress: emailAddress)
            boundSignUp = created
            boundSignUp = try await created.sendEmailCode()
            return nil
        case "resendEmailCode":
            guard configured else { throw BridgeError.unexpected }
            if let signIn = boundSignIn {
                boundSignIn = try await signIn.sendEmailCode()
            } else if let signUp = boundSignUp {
                boundSignUp = try await signUp.sendEmailCode()
            } else {
                throw BridgeError.sessionEnded
            }
            return nil
        case "verifyEmailCode":
            guard let code = arguments?["code"] as? String, configured else {
                throw BridgeError.unexpected
            }
            let complete: Bool
            if let signIn = boundSignIn {
                let verified = try await signIn.verifyCode(code)
                boundSignIn = verified
                complete = verified.status == .complete
            } else if let signUp = boundSignUp {
                let verified = try await signUp.verifyEmailCode(code)
                boundSignUp = verified
                complete = verified.status == .complete
            } else {
                throw BridgeError.sessionEnded
            }
            // Success needs a complete attempt and an active session, not only
            // a verified code.
            guard complete, Clerk.shared.session?.status == .active else {
                throw BridgeError.unexpected
            }
            clearBinding()
            return "completed"
        case "continueWithGoogle":
            guard configured else { throw BridgeError.unexpected }
            clearBinding()
            let result: TransferFlowResult
            do {
                result = try await Clerk.shared.auth.signInWithOAuth(
                    provider: .google,
                    prefersEphemeralWebBrowserSession: true,
                    transferable: true)
            } catch {
                if Self.isCancellation(error) { return "cancelled" }
                throw error
            }
            return try await googleOutcome(result)
        case "reload":
            guard configured else { throw BridgeError.unexpected }
            try await reload()
            return nil
        case "getToken":
            guard configured else { throw BridgeError.unexpected }
            guard Clerk.shared.session?.status == .active else { return nil }
            let skipCache = arguments?["skipCache"] as? Bool ?? false
            return try await Clerk.shared.auth.getToken(.init(skipCache: skipCache))
        case "signOut":
            guard configured else { throw BridgeError.unexpected }
            clearBinding()
            try await Clerk.shared.auth.signOut()
            return nil
        default:
            throw BridgeError.notImplemented
        }
    }

    // MARK: Google outcome

    /// Maps a Google result to a TailTag result name. `completed` needs a
    /// complete attempt and an active session. An attempt that needs an email
    /// code binds this plugin and has a sent code.
    @MainActor
    private func googleOutcome(_ result: TransferFlowResult) async throws -> String {
        switch result {
        case .signIn(let signIn):
            switch signIn.status {
            case .complete:
                return try Self.completedIfActive()
            case .needsFirstFactor:
                boundSignIn = try await Self.preparedSignInCode(signIn)
                return "needsEmailCode"
            default:
                throw BridgeError.unexpected
            }
        case .signUp(let signUp):
            switch signUp.status {
            case .complete:
                return try Self.completedIfActive()
            case .missingRequirements:
                guard signUp.missingFields.isEmpty, signUp.unverifiedFields == [.emailAddress] else {
                    throw BridgeError.unexpected
                }
                let verification = signUp.verifications["email_address"] ?? nil
                boundSignUp =
                    Self.isPreparedEmailCode(verification) ? signUp : try await signUp.sendEmailCode()
                return "needsEmailCode"
            default:
                throw BridgeError.unexpected
            }
        }
    }

    /// The sign-in with a sent email code. It sends the code when Clerk has
    /// not sent it yet.
    @MainActor
    private static func preparedSignInCode(_ signIn: SignIn) async throws -> SignIn {
        if isPreparedEmailCode(signIn.firstFactorVerification) { return signIn }
        guard
            let factor = signIn.supportedFirstFactors?.first(where: {
                $0.strategy == .emailCode && $0.emailAddressId != nil
            })
        else {
            throw BridgeError.unexpected
        }
        return try await signIn.sendEmailCode(emailAddressId: factor.emailAddressId)
    }

    private static func isPreparedEmailCode(_ verification: Verification?) -> Bool {
        verification?.strategy == .emailCode && verification?.status == .unverified
    }

    @MainActor
    private static func completedIfActive() throws -> String {
        guard Clerk.shared.session?.status == .active else { throw BridgeError.unexpected }
        return "completed"
    }

    /// A dismissed browser session. ClerkKit throws `CancellationError`
    /// (`Utils/WebAuthentication.swift`). The system can also report
    /// `canceledLogin`.
    private static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let webError = error as? ASWebAuthenticationSessionError {
            return webError.code == .canceledLogin
        }
        return false
    }

    private func clearBinding() {
        boundSignIn = nil
        boundSignUp = nil
    }

    // MARK: Startup and reload

    /// Reports a startup failure when the SDK has not loaded in time.
    @MainActor
    private func watchStartup() {
        startupWatch?.cancel()
        startupWatch = Task { @MainActor [weak self] in
            try? await Task.sleep(for: Self.startupTimeout)
            guard let self, !Task.isCancelled, !Clerk.shared.isLoaded else { return }
            self.startupFailure = "unexpected"
            self.sendCurrentState()
        }
    }

    /// Loads the environment and the client again without clearing storage.
    @MainActor
    private func reload() async throws {
        startupFailure = nil
        // Forget the last sent state, so a failure during this reload is
        // sent even when it repeats the failure that started the reload.
        lastSentState = nil
        // Watch again, so a reload that returns without a loaded SDK still
        // ends in a reported failure.
        watchStartup()
        do {
            try await Clerk.shared.refreshEnvironment()
            try await Clerk.shared.refreshClient()
        } catch {
            // Keep the failed state, so a later observation cannot report
            // loading without a failure.
            startupFailure = Self.errorCode(for: error)
            sendCurrentState()
            throw error
        }
        sendCurrentState()
    }

    // MARK: State channel

    public func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink)
        -> FlutterError?
    {
        eventSink = events
        lastSentState = nil
        Task { @MainActor in self.sendCurrentState() }
        return nil
    }

    public func onCancel(withArguments arguments: Any?) -> FlutterError? {
        eventSink = nil
        return nil
    }

    @MainActor
    private func observeState() {
        withObservationTracking {
            _ = Clerk.shared.isLoaded
            _ = Clerk.shared.session?.status
        } onChange: { [weak self] in
            // `onChange` runs before the new value is stored, so read it on the next turn.
            Task { @MainActor in
                self?.sendCurrentState()
                self?.observeState()
            }
        }
    }

    @MainActor
    private func sendCurrentState() {
        guard let eventSink else { return }
        let state: String
        if configured, !Clerk.shared.isLoaded, let startupFailure {
            let failedState = "failed:\(startupFailure)"
            guard failedState != lastSentState else { return }
            lastSentState = failedState
            eventSink(FlutterError(code: startupFailure, message: nil, details: nil))
            return
        } else if !configured || !Clerk.shared.isLoaded {
            state = "loading"
        } else if Clerk.shared.session?.status == .active {
            state = "signedIn"
        } else {
            state = "signedOut"
        }
        guard state != lastSentState else { return }
        lastSentState = state
        eventSink(state)
    }

    // MARK: Publishable key

    /// Mirrors the key rule of ClerkKit 1.6.1 (`ConfigurationManager.validatePublishableKey`
    /// and `extractFrontendApiUrl`). Keep it in step with the pinned version.
    private static func isValidPublishableKey(_ key: String) -> Bool {
        let key = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard key.hasPrefix("pk_test_") || key.hasPrefix("pk_live_") else { return false }
        let range = key.range(of: "pk_live_") ?? key.range(of: "pk_test_")
        guard let range, range.upperBound < key.endIndex else { return false }
        var base64 = String(key[range.upperBound...])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        let paddingLength = 4 - (base64.count % 4)
        if paddingLength < 4 {
            base64 = base64.padding(toLength: base64.count + paddingLength, withPad: "=", startingAt: 0)
        }
        guard let data = Data(base64Encoded: base64) else { return false }
        return String(data: data, encoding: .utf8) != nil
    }

    // MARK: Error mapping

    private enum BridgeError: Error {
        case unexpected
        case sessionEnded
        case notImplemented
    }

    private static let connectivityCodes: Set<URLError.Code> = [
        .notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotConnectToHost,
        .cannotFindHost, .dnsLookupFailed, .dataNotAllowed, .internationalRoamingOff,
    ]

    private static func errorCode(for error: Error) -> String {
        if case BridgeError.sessionEnded = error {
            return "sessionEnded"
        }
        if let urlError = error as? URLError {
            return connectivityCodes.contains(urlError.code) ? "connectivity" : "unexpected"
        }
        if let apiError = error as? ClerkAPIError {
            switch apiError.code {
            case "form_code_incorrect", "verification_expired", "verification_failed":
                return "invalidCode"
            case "too_many_requests":
                return "rateLimited"
            case "form_identifier_exists":
                return "accountExists"
            case "form_identifier_not_found":
                return "accountNotFound"
            case "authentication_invalid", "signed_out", "resource_not_found":
                return "sessionEnded"
            default:
                return "unexpected"
            }
        }
        return "unexpected"
    }
}
