import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";

/// A token-shaped value built at runtime, so no token literal sits in the
/// repository (#511 G14).
final String _token = "Z" * 43;

void main() {
  test("the printed format is a TailTag, and the value is kept as is", () {
    final raw = "https://tailtag.app/t#$_token";

    final payload = TagPayload.parse(raw);

    expect(payload?.value, raw);
    expect(payload.toString(), isNot(contains(_token)));
  });

  // Anything else never reaches the server (#511 AC11).
  final notTags = <String, String>{
    "a short token": "https://tailtag.app/t#${"Z" * 42}",
    "a long token": "https://tailtag.app/t#${"Z" * 44}",
    "a character outside URL-safe base64": "https://tailtag.app/t#${"Z" * 42}+",
    "plain HTTP": "http://tailtag.app/t#$_token",
    "another host": "https://tailtag.example/t#$_token",
    "another path": "https://tailtag.app/u#$_token",
    "a query in place of the fragment": "https://tailtag.app/t?$_token",
    "trailing text": "https://tailtag.app/t#$_token\n",
  };
  for (final MapEntry(key: label, value: raw) in notTags.entries) {
    test("$label is not a TailTag", () {
      expect(TagPayload.parse(raw), isNull);
    });
  }
}
