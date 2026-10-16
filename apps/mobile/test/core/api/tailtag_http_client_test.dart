import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/tailtag_http_client.dart";

import "../../support/api_test_support.dart";

typedef _Case = ({
  String label,
  String base,
  String url,
  String? token,
  String? preExisting,
  String? expected,
});

void main() {
  group("TailTagHttpClient token seam", () {
    const cases = <_Case>[
      (
        label: "https same origin with a token adds the bearer header",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: "Bearer tok-1",
      ),
      (
        label: "a pre-existing Authorization is replaced, not duplicated",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app/api/me/",
        token: "tok-1",
        preExisting: "Bearer caller-supplied",
        expected: "Bearer tok-1",
      ),
      (
        label: "explicit default port is the same origin",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app:443/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: "Bearer tok-1",
      ),
      (
        label: "http base URL never carries a token",
        base: "http://127.0.0.1:8000",
        url: "http://127.0.0.1:8000/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: null,
      ),
      (
        label: "another host gets none",
        base: "https://dev.tailtag.app",
        url: "https://elsewhere.example/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: null,
      ),
      (
        label: "a host that merely starts with the base host gets none",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app.evil.example/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: null,
      ),
      (
        label: "another port gets none",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app:8443/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: null,
      ),
      (
        label: "downgrade to http on the same host gets none",
        base: "https://dev.tailtag.app",
        url: "http://dev.tailtag.app/api/me/",
        token: "tok-1",
        preExisting: null,
        expected: null,
      ),
      (
        label: "a null token adds none and strips a pre-existing header",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app/api/me/",
        token: null,
        preExisting: "Bearer caller-supplied",
        expected: null,
      ),
      (
        label: "an empty token adds none",
        base: "https://dev.tailtag.app",
        url: "https://dev.tailtag.app/api/me/",
        token: "",
        preExisting: null,
        expected: null,
      ),
    ];

    for (final c in cases) {
      test(c.label, () async {
        final inner = FakeHttpClient.respond(204);
        final client = TailTagHttpClient(
          inner: inner,
          apiBaseUrl: Uri.parse(c.base),
          tokenProvider: FakeApiTokenProvider(c.token),
        );

        await client.get(
          Uri.parse(c.url),
          headers: {if (c.preExisting != null) "Authorization": c.preExisting!},
        );

        final request = inner.requests.single;
        expect(request.authorization, c.expected);
        // Redirects are never followed, whatever the destination.
        expect(request.followRedirects, isFalse);
      });
    }
  });
}
