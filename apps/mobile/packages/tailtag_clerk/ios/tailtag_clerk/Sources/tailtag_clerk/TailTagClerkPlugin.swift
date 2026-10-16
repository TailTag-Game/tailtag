import ClerkKit
import Flutter
import Foundation
import Observation

/// Forwards the Dart bridge calls to the Clerk iOS SDK and maps its errors.
///
/// Nothing here logs, and no token, email address, error message, or Clerk
/// identifier goes into a `FlutterError` or a state event. A failure leaves
/// this file as one of five error codes and nothing else.
public final class TailTagClerkPlugin: NSObject, FlutterPlugin, FlutterStreamHandler {
    private var eventSink: FlutterEventSink?
    private var lastSentState: String?
    private var configured = false

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
            }
            return nil
        case "startEmailCode":
            guard let emailAddress = arguments?["emailAddress"] as? String, configured else {
                throw BridgeError.unexpected
            }
            try await Clerk.shared.auth.signInWithEmailCode(emailAddress: emailAddress)
            return nil
        case "verifyCode":
            guard let code = arguments?["code"] as? String, configured,
                let signIn = Clerk.shared.auth.currentSignIn
            else {
                throw BridgeError.unexpected
            }
            let verified = try await signIn.verifyCode(code)
            guard verified.status == .complete else { throw BridgeError.unexpected }
            return nil
        case "getToken":
            guard configured else { throw BridgeError.unexpected }
            guard Clerk.shared.session?.status == .active else { return nil }
            let skipCache = arguments?["skipCache"] as? Bool ?? false
            return try await Clerk.shared.auth.getToken(.init(skipCache: skipCache))
        case "signOut":
            guard configured else { throw BridgeError.unexpected }
            try await Clerk.shared.auth.signOut()
            return nil
        default:
            throw BridgeError.notImplemented
        }
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
        if !configured || !Clerk.shared.isLoaded {
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
        case notImplemented
    }

    private static let connectivityCodes: Set<URLError.Code> = [
        .notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotConnectToHost,
        .cannotFindHost, .dnsLookupFailed, .dataNotAllowed, .internationalRoamingOff,
    ]

    private static func errorCode(for error: Error) -> String {
        if let urlError = error as? URLError {
            return connectivityCodes.contains(urlError.code) ? "connectivity" : "unexpected"
        }
        if let apiError = error as? ClerkAPIError {
            switch apiError.code {
            case "form_code_incorrect", "verification_expired":
                return "invalidCode"
            case "authentication_invalid", "signed_out", "resource_not_found":
                return "sessionEnded"
            default:
                return "unexpected"
            }
        }
        return "unexpected"
    }
}
