/// Supplies the bearer token for authenticated requests.
///
/// This is TailTag's own seam so the transport never imports an auth SDK.
/// Return null when there is no session; the transport then sends no
/// `Authorization` header.
abstract interface class ApiTokenProvider {
  /// The current token, or null when there is no session.
  Future<String?> token();
}
