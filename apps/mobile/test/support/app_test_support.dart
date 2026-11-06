import "dart:async";
import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:http/http.dart" as http;
import "package:tailtag_mobile/app/app.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";

import "api_test_support.dart";
import "auth_test_support.dart";

/// A network for `GET /api/me/` whose answers the test controls.
///
/// Each request gets the next queued status at once. When the queue is
/// empty, the request waits until the test calls [release].
final class ScriptedNetwork extends http.BaseClient {
  /// Creates a network that answers with [statuses] in order.
  new([List<int> statuses = const []]) : _queue = [...statuses];

  final List<int> _queue;
  final List<Completer<http.StreamedResponse>> _held = [];

  /// The number of requests sent so far.
  int requests = 0;

  /// Queues [status] for the next request.
  void enqueue(int status) => _queue.add(status);

  /// Answers held request [index] with [status].
  void release(int index, int status) => _held[index].complete(_reply(status));

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests++;
    if (_queue.isNotEmpty) {
      return _reply(_queue.removeAt(0));
    }
    final held = Completer<http.StreamedResponse>();
    _held.add(held);
    return await held.future;
  }

  static http.StreamedResponse _reply(int status) => http.StreamedResponse(
    Stream.value(utf8.encode(status == 200 ? '{"id": 42}' : "{}")),
    status,
    headers: {"content-type": "application/json"},
  );
}

/// The running app over [session] and [network], with its container.
final class AppHarness {
  /// Creates the harness.
  const new(this.tester, this.container, this.session, this.network);

  final WidgetTester tester;
  final ProviderContainer container;
  final FakeAuthSession session;
  final ScriptedNetwork network;

  /// The router's current path.
  String get path => container
      .read(routerProvider)
      .routerDelegate
      .currentConfiguration
      .uri
      .path;

  /// Lets async work finish, the loading delay pass, and page transitions
  /// end. Loading spinners never settle, so it pumps fixed times.
  Future<void> settle() async {
    for (var i = 0; i < 3; i++) {
      await tester.pump();
    }
    await tester.pump(loadingIndicatorDelay);
    await tester.pump(const Duration(seconds: 1));
  }

  /// Taps the widget with [key] and settles.
  Future<void> tap(String key) async {
    await tester.tap(find.byKey(Key(key)));
    await settle();
  }
}

/// Pumps the whole app with only the network and the native session faked.
Future<AppHarness> pumpApp(
  WidgetTester tester, {
  required FakeAuthSession session,
  ScriptedNetwork? network,
}) async {
  final net = network ?? ScriptedNetwork();
  final container = ProviderContainer(
    overrides: [
      authSessionProvider.overrideWithValue(session),
      currentUserRepositoryProvider.overrideWithValue(
        CurrentUserRepository(createTestTransport(net, tokenProvider: session)),
      ),
    ],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(container: container, child: const TailTagApp()),
  );
  final harness = AppHarness(tester, container, session, net);
  await harness.settle();
  return harness;
}
