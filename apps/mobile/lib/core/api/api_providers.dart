import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:http/http.dart" as http;
import "package:tailtag_mobile/core/api/api_token_provider.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/api/tailtag_http_client.dart";
import "package:tailtag_mobile/core/config/app_config_provider.dart";

/// The token seam. Defaults to no token; the auth integration (#135)
/// overrides it with a provider backed by the Clerk session.
final apiTokenProviderProvider = Provider<ApiTokenProvider>(
  (ref) => const _NoApiTokenProvider(),
);

/// The shared transport, configured from [appConfigProvider]. It closes its
/// HTTP client when the provider is disposed.
final apiTransportProvider = Provider<ApiTransport>((ref) {
  final config = ref.watch(appConfigProvider);
  final client = TailTagHttpClient(
    inner: http.Client(),
    apiBaseUrl: config.apiBaseUrl,
    tokenProvider: ref.watch(apiTokenProviderProvider),
  );
  ref.onDispose(client.close);
  return ApiTransport(client: client, apiBaseUrl: config.apiBaseUrl);
});

final class _NoApiTokenProvider implements ApiTokenProvider {
  const new();

  @override
  Future<String?> token() async => null;
}
