import "dart:convert";

import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/debug/azp_probe.dart";

import "../support/auth_test_support.dart";

String _segment(String json) =>
    base64Url.encode(utf8.encode(json)).replaceAll("=", "");

void main() {
  // The widget test proves the screen for a token with and without `azp`.
  // This table adds what a real token can look like on the wire and the
  // malformed input the probe must survive without throwing.
  group("tokenHasAzpClaim", () {
    // Chosen so the unpadded base64url payload needs the URL-safe alphabet.
    final urlSafePayload = {"n": "???>>>", "azp": "https://example.invalid"};

    test("fixture really uses the URL-safe alphabet and no padding", () {
      final segment = fakeJwt(urlSafePayload).split(".")[1];
      expect(segment, matches(RegExp("[-_]")));
      expect(segment, isNot(contains("=")));
    });

    final cases = <({String label, String token, bool expected})>[
      (
        label: "unpadded URL-safe payload with azp",
        token: fakeJwt(urlSafePayload),
        expected: true,
      ),
      (
        label: "payload without azp",
        token: fakeJwt({"sub": "user_test"}),
        expected: false,
      ),
      (label: "empty string", token: "", expected: false),
      (label: "not a JWT", token: "not-a-jwt", expected: false),
      (
        label: "payload that is not base64",
        token: fakeJwtWithRawPayload("!!!"),
        expected: false,
      ),
      (
        label: "payload that is not JSON",
        token: fakeJwtWithRawPayload(_segment("not json")),
        expected: false,
      ),
      (
        label: "payload that is JSON but not an object",
        token: fakeJwtWithRawPayload(_segment('["azp"]')),
        expected: false,
      ),
    ];

    for (final c in cases) {
      test(c.label, () {
        expect(tokenHasAzpClaim(c.token), c.expected);
      });
    }
  });
}
