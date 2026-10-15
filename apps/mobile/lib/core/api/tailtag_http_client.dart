import "package:http/http.dart" as http;
import "package:tailtag_mobile/core/api/api_token_provider.dart";

/// The `package:http` client that enforces TailTag's request rules.
///
/// - Redirects are never followed, so a token can never travel to a redirect
///   target.
/// - `Authorization: Bearer <token>` is sent only over HTTPS to the
///   configured API origin (same scheme, host, and effective port), and only
///   when the token is non-empty. Any other request has the header removed.
///
/// The request is mutated and forwarded as the same object, so an
/// `Abortable` request's abort trigger still reaches the inner client.
final class TailTagHttpClient extends http.BaseClient {
  /// Wraps the inner client, applying the token and redirect rules for the
  /// configured API base URL.
  new({
    required this._inner,
    required this._apiBaseUrl,
    required this._tokenProvider,
  });

  final http.Client _inner;
  final Uri _apiBaseUrl;
  final ApiTokenProvider _tokenProvider;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    request
      ..followRedirects = false
      ..headers.remove("authorization");

    if (_isApiOrigin(request.url)) {
      final token = await _tokenProvider.token();
      if (token != null && token.isNotEmpty) {
        request.headers["Authorization"] = "Bearer $token";
      }
    }
    return await _inner.send(request);
  }

  @override
  void close() => _inner.close();

  /// Dart's `Uri.port` is the scheme default when the URL names none.
  bool _isApiOrigin(Uri url) =>
      _apiBaseUrl.scheme == "https" &&
      url.scheme == "https" &&
      url.host == _apiBaseUrl.host &&
      url.port == _apiBaseUrl.port;
}
