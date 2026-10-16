import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/config/app_config.dart";
import "package:tailtag_mobile/core/config/app_config_provider.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";

import "../../support/auth_test_support.dart";

void main() {
  test("providers assemble from AppConfig and default to no token", () async {
    final container = ProviderContainer(
      overrides: [
        appConfigProvider.overrideWithValue(
          AppConfig.parse({
            apiBaseUrlKey: "https://dev.tailtag.app",
            clerkPublishableKeyKey: "pk_test_abc123",
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    expect(await container.read(apiTokenProviderProvider).token(), isNull);
    expect(
      container.read(currentUserRepositoryProvider),
      isA<CurrentUserRepository>(),
    );
  });

  test("authTokenOverride makes the auth session the API token provider", () {
    final session = FakeAuthSession();
    final container = ProviderContainer(
      overrides: [
        authSessionProvider.overrideWithValue(session),
        authTokenOverride,
      ],
    );
    addTearDown(container.dispose);

    expect(container.read(apiTokenProviderProvider), same(session));
  });
}
