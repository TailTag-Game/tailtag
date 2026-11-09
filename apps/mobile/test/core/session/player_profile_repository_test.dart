import "dart:convert";

import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_profile_repository.dart";

import "../../support/api_test_support.dart";

PlayerProfileRepository _repository(FakeHttpClient client) =>
    PlayerProfileRepository(createTestTransport(client));

Future<PlayerProfile> _fetch(String body) =>
    _repository(FakeHttpClient.respond(200, body: body)).fetch();

void main() {
  group("fetch maps the server response", () {
    const incomplete =
        '{"handle": null, "display_name": null, "avatar_url": null, '
        '"onboarding_complete": false, "is_enabled": true}';
    const disabled =
        '{"handle": "finn_42", "display_name": "Finn", '
        '"avatar_url": "https://cdn.example/a.webp", '
        '"onboarding_complete": true, "is_enabled": false}';

    test("an incomplete profile keeps its null text fields", () async {
      final profile = await _fetch(incomplete);

      expect(profile.handle, isNull);
      expect(profile.displayName, isNull);
      expect(profile.avatarUrl, isNull);
      expect(profile.onboardingComplete, isFalse);
      expect(profile.isEnabled, isTrue);
    });

    test("a completed, disabled profile keeps every server value", () async {
      final profile = await _fetch(disabled);

      expect(profile.handle, "finn_42");
      expect(profile.displayName, "Finn");
      expect(profile.avatarUrl, Uri.parse("https://cdn.example/a.webp"));
      expect(profile.onboardingComplete, isTrue);
      expect(profile.isEnabled, isFalse);
    });

    const noCompletion =
        '{"handle": null, "display_name": null, "avatar_url": null, '
        '"is_enabled": true}';
    const noEligibility =
        '{"handle": null, "display_name": null, "avatar_url": null, '
        '"onboarding_complete": false}';

    for (final body in [noCompletion, noEligibility]) {
      test("a 200 with no state flag fails closed: $body", () {
        expect(_fetch(body), throwsA(isA<ApiUnexpectedFailure>()));
      });
    }
  });

  group("save", () {
    const complete =
        '{"handle": "finn_42", "display_name": "Finn", "avatar_url": null, '
        '"onboarding_complete": true, "is_enabled": true}';

    test("sends both fields exactly as typed and maps the reply", () async {
      final client = FakeHttpClient.respond(200, body: complete);

      final profile = await _repository(client)
          .save(handle: " Finn_42 ", displayName: "  Finn  ");

      final request = client.requests.single;
      expect(request.method, "PUT");
      expect(request.url, Uri.parse("https://dev.tailtag.app/api/profile/"));
      expect(jsonDecode(utf8.decode(request.bodyBytes)), {
        "handle": " Finn_42 ",
        "display_name": "  Finn  ",
      });
      expect(profile.onboardingComplete, isTrue);
    });
  });
}
