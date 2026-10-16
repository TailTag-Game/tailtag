// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:http/http.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

class _HttpClientAdapter {
  _HttpClientAdapter(this.serverConfig);

  final _i1.ServerConfig<_i2.Client> serverConfig;

  _i2.Client? _$client;

  _i3.bool _$ownsClient = false;

  _i3.bool _$isClosed = false;

  final _i3.StateError _$closedError = _i3.StateError(
    'Cannot access the HTTP client after the server has been closed.',
  );

  _i2.Client get client {
    if (_$isClosed) {
      throw _$closedError;
    }

    final cachedClient = _$client;
    if (cachedClient != null) {
      return cachedClient;
    }

    final configuredClient = serverConfig.client;
    final resolvedClient =
        configuredClient ?? serverConfig.clientFactory?.call() ?? _i2.Client();
    _$ownsClient = configuredClient == null;
    return _$client = resolvedClient;
  }

  void close() {
    if (_$isClosed) {
      return;
    }

    _$isClosed = true;
    if (_$ownsClient) {
      _$client?.close();
    }
  }
}

sealed class Server {
  Server({required this.baseUrl, required this.serverConfig})
    : _$httpClientAdapter = _HttpClientAdapter(serverConfig);

  final _i3.String baseUrl;

  final _i1.ServerConfig<_i2.Client> serverConfig;

  final _HttpClientAdapter _$httpClientAdapter;

  _i2.Client get client => _$httpClientAdapter.client;

  void close() => _$httpClientAdapter.close();
}

/// Custom server with user-defined base URL
class CustomServer extends Server {
  CustomServer({
    required super.baseUrl,
    super.serverConfig = const _i1.ServerConfig<_i2.Client>(),
  });
}
