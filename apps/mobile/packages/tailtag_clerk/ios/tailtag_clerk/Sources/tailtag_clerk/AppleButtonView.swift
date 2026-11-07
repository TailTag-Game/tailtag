import AuthenticationServices
import Flutter
import UIKit

/// Creates the native "Continue with Apple" button for the Dart
/// `AppleButton` widget.
///
/// The system button draws Apple's logo and text, so the app needs no Apple
/// artwork and always meets Apple's Human Interface Guidelines. The button
/// only draws. It gets no touches and has no accessibility element, because
/// the Dart widget owns the tap, the focus, the disabled state, and the
/// semantics.
final class AppleButtonViewFactory: NSObject, FlutterPlatformViewFactory {
    /// The view type. The Dart `appleButtonViewType` uses the same value.
    static let viewType = "app.tailtag/apple-button"

    func create(
        withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?
    ) -> FlutterPlatformView {
        let style = (args as? [String: Any])?["style"] as? String
        return AppleButtonPlatformView(frame: frame, white: style == "white")
    }

    func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol {
        FlutterStandardMessageCodec.sharedInstance()
    }
}

/// Holds one system Apple button.
private final class AppleButtonPlatformView: NSObject, FlutterPlatformView {
    private let button: PillAppleIDButton

    /// Black is for light backgrounds, and white is for dark ones.
    init(frame: CGRect, white: Bool) {
        button = PillAppleIDButton(
            authorizationButtonType: .continue,
            authorizationButtonStyle: white ? .white : .black)
        button.frame = frame
        button.isUserInteractionEnabled = false
        button.isAccessibilityElement = false
        button.accessibilityElementsHidden = true
        super.init()
    }

    func view() -> UIView { button }
}

/// The system Apple button with the TailTag pill shape. The corner radius
/// follows the height, so the shape stays a pill at any text scale.
private final class PillAppleIDButton: ASAuthorizationAppleIDButton {
    override func layoutSubviews() {
        super.layoutSubviews()
        cornerRadius = bounds.height / 2
    }
}
