import "dart:convert";

/// Whether the payload of the JWT [token] has an `azp` claim.
///
/// It reads only the key names of the payload and keeps no value. It never
/// logs and never throws: a malformed token gives false.
bool tokenHasAzpClaim(String token) {
  final segments = token.split(".");
  if (segments.length != 3) {
    return false;
  }
  try {
    final payload = jsonDecode(
      utf8.decode(base64Url.decode(base64Url.normalize(segments[1]))),
    );
    return payload is Map<String, Object?> && payload.containsKey("azp");
  } on FormatException {
    return false;
  }
}
