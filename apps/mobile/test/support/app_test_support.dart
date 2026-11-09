import "dart:async";
import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter/services.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:http/http.dart" as http;
import "package:tailtag_mobile/app/app.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/conventions/convention_repository.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";
import "package:tailtag_mobile/core/session/player_profile_providers.dart";
import "package:tailtag_mobile/core/session/player_profile_repository.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";

import "api_test_support.dart";
import "auth_test_support.dart";

/// One answer to a `/api/profile/` request, in the server's response shape.
final class ProfileReply {
  /// Creates an answer with [status] and [body].
  const new({
    this.status = 200,
    this.body = _completeBody,
    this.fails = false,
    this.held = false,
  });

  static const _completeBody =
      '{"handle": "finn_42", "display_name": "Finn", "avatar_url": null, '
      '"onboarding_complete": true, "is_enabled": true}';

  /// An enabled, completed profile.
  static const complete = ProfileReply();

  /// An enabled profile with no onboarding yet.
  static const incomplete = ProfileReply(
    body:
        '{"handle": null, "display_name": null, "avatar_url": null, '
        '"onboarding_complete": false, "is_enabled": true}',
  );

  /// A disabled profile that finished onboarding.
  static const disabled = ProfileReply(
    body:
        '{"handle": "finn_42", "display_name": "Finn", "avatar_url": null, '
        '"onboarding_complete": true, "is_enabled": false}',
  );

  /// A disabled profile with no onboarding yet.
  static const disabledIncomplete = ProfileReply(
    body:
        '{"handle": null, "display_name": null, "avatar_url": null, '
        '"onboarding_complete": false, "is_enabled": false}',
  );

  /// The connection breaks before an answer arrives.
  static const brokenConnection = ProfileReply(fails: true);

  /// The answer waits until the test calls `releaseProfile`.
  static const stalled = ProfileReply(held: true);

  final int status;
  final String body;
  final bool fails;
  final bool held;
}

/// A `Convention` in the server's response shape.
String conventionJson({
  int id = 10,
  String name = "Test Con",
  String status = "active",
  String start = "2026-11-08",
  String end = "2026-11-10",
}) =>
    '{"id": $id, "name": "$name", "status": "$status", '
    '"start_date": "$start", "end_date": "$end"}';

/// A `ConventionEnrollment` in the server's response shape.
String enrollmentJson({int id = 7, String? convention, bool selected = true}) =>
    '{"id": $id, "convention": ${convention ?? conventionJson()}, '
    '"is_active": $selected, "created_at": "2026-10-01T12:00:00Z"}';

/// One answer to a `/api/conventions/` request.
final class ConventionReply {
  /// Creates an answer with [status] and [body].
  const new({
    this.status = 200,
    this.body = "{}",
    this.fails = false,
    this.held = false,
  });

  /// An array answer of [items].
  factory list(List<String> items) =>
      ConventionReply(body: "[${items.join(", ")}]");

  /// The `{enrollment: ...}` answer of `/api/conventions/active/`. A null
  /// [enrollment] means no selection.
  factory selection(String? enrollment) =>
      ConventionReply(body: '{"enrollment": ${enrollment ?? "null"}}');

  /// The connection breaks before an answer arrives.
  static const brokenConnection = ConventionReply(fails: true);

  /// The answer waits until the test calls `releaseConvention`.
  static const stalled = ConventionReply(held: true);

  final int status;
  final String body;
  final bool fails;
  final bool held;
}

/// A network for the entry reads, whose answers the test controls.
///
/// Each `GET /api/me/` gets the next queued status at once. When that queue
/// is empty, the request waits until the test calls [release].
///
/// Each `/api/profile/` request gets the next [ProfileReply]. When that queue
/// is empty, the answer is a completed profile. When the selection queue is
/// empty, the answer is a selected convention, so a test about identity or
/// sign-out reaches the home.
final class ScriptedNetwork extends http.BaseClient {
  /// Creates a network that answers `GET /api/me/` with [statuses] and
  /// `/api/profile/` with [profiles], in order.
  new([List<int> statuses = const [], List<ProfileReply> profiles = const []])
    : _queue = [...statuses],
      _profiles = [...profiles];

  /// Creates a network with answers for the convention requests too, in
  /// order.
  factory withConventions(
    List<int> statuses,
    List<ProfileReply> profiles, {
    List<ConventionReply> selections = const [],
    List<ConventionReply> conventions = const [],
    List<ConventionReply> enrollments = const [],
    List<ConventionReply> writes = const [],
  }) => ScriptedNetwork(statuses, profiles)
    .._selections.addAll(selections)
    .._conventions.addAll(conventions)
    .._enrollments.addAll(enrollments)
    .._writes.addAll(writes);

  final List<int> _queue;
  final List<ProfileReply> _profiles;
  final List<ConventionReply> _selections = [];
  final List<ConventionReply> _conventions = [];
  final List<ConventionReply> _enrollments = [];
  final List<ConventionReply> _writes = [];
  final List<Completer<http.StreamedResponse>> _heldConventions = [];
  final List<Completer<http.StreamedResponse>> _held = [];
  final List<Completer<http.StreamedResponse>> _heldProfiles = [];

  /// The number of `GET /api/me/` requests sent so far.
  int requests = 0;

  /// Each request as `METHOD path`, in the order that it was sent.
  final List<String> log = [];

  /// The JSON body of each `PUT /api/profile/`, in order.
  final List<Map<String, Object?>> profilePuts = [];

  /// The number of `GET /api/profile/` requests sent so far.
  int profileGets = 0;

  /// The number of held profile requests whose abort trigger fired.
  int profileAborts = 0;

  /// Each convention write as `METHOD path` and its JSON body, in order.
  final List<({String request, Map<String, Object?> body})> conventionWrites =
      [];

  /// The number of held convention requests whose abort trigger fired.
  int conventionAborts = 0;

  /// The number of requests sent to [request], such as
  /// `GET /api/profile/`.
  int count(String request) => log.where((item) => item == request).length;

  /// Queues [reply] for the next selection read.
  void enqueueSelection(ConventionReply reply) => _selections.add(reply);

  /// Queues [reply] for the next conventions read.
  void enqueueConventions(ConventionReply reply) => _conventions.add(reply);

  /// Queues [reply] for the next enrollments read.
  void enqueueEnrollments(ConventionReply reply) => _enrollments.add(reply);

  /// Queues [reply] for the next convention write.
  void enqueueWrite(ConventionReply reply) => _writes.add(reply);

  /// Answers held convention request [index] with [reply].
  void releaseConvention(int index, ConventionReply reply) =>
      _heldConventions[index].complete(_replyWith(reply.status, reply.body));

  /// Queues [status] for the next `GET /api/me/`.
  void enqueue(int status) => _queue.add(status);

  /// Queues [reply] for the next `/api/profile/` request.
  void enqueueProfile(ProfileReply reply) => _profiles.add(reply);

  /// Answers held `GET /api/me/` request [index] with [status].
  void release(int index, int status) => _held[index].complete(_reply(status));

  /// Answers held `/api/profile/` request [index] with [reply].
  void releaseProfile(int index, ProfileReply reply) =>
      _heldProfiles[index].complete(_replyWith(reply.status, reply.body));

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    log.add("${request.method} ${request.url.path}");
    if (request.url.path == "/api/profile/") {
      return await _sendProfile(request);
    }
    if (request.url.path.startsWith("/api/conventions/")) {
      return await _sendConvention(request);
    }
    requests++;
    if (_queue.isNotEmpty) {
      return _reply(_queue.removeAt(0));
    }
    final held = Completer<http.StreamedResponse>();
    _held.add(held);
    return await held.future;
  }

  Future<http.StreamedResponse> _sendProfile(http.BaseRequest request) async {
    final bytes = await request.finalize().toBytes();
    if (request.method == "PUT") {
      profilePuts.add(jsonDecode(utf8.decode(bytes)) as Map<String, Object?>);
    } else {
      profileGets++;
    }
    final reply = _profiles.isNotEmpty
        ? _profiles.removeAt(0)
        : ProfileReply.complete;
    if (reply.fails) {
      throw http.ClientException("connection broke", request.url);
    }
    if (!reply.held) {
      return _replyWith(reply.status, reply.body);
    }
    final held = Completer<http.StreamedResponse>();
    _heldProfiles.add(held);
    if (request case http.Abortable(:final abortTrigger?)) {
      unawaited(abortTrigger.then((_) => profileAborts++));
    }
    return await held.future;
  }

  Future<http.StreamedResponse> _sendConvention(
    http.BaseRequest request,
  ) async {
    final bytes = await request.finalize().toBytes();
    final path = request.url.path;
    final ConventionReply reply;
    if (request.method == "GET") {
      final (queue, fallback) = switch (path) {
        "/api/conventions/" => (_conventions, ConventionReply.list(const [])),
        "/api/conventions/enrollments/" => (
          _enrollments,
          ConventionReply.list(const []),
        ),
        _ => (_selections, ConventionReply.selection(enrollmentJson())),
      };
      reply = queue.isNotEmpty ? queue.removeAt(0) : fallback;
    } else {
      conventionWrites.add((
        request: "${request.method} $path",
        body: jsonDecode(utf8.decode(bytes)) as Map<String, Object?>,
      ));
      reply = _writes.isNotEmpty
          ? _writes.removeAt(0)
          : ConventionReply(status: 201, body: enrollmentJson());
    }
    if (reply.fails) {
      throw http.ClientException("connection broke", request.url);
    }
    if (!reply.held) {
      return _replyWith(reply.status, reply.body);
    }
    final held = Completer<http.StreamedResponse>();
    _heldConventions.add(held);
    if (request case http.Abortable(:final abortTrigger?)) {
      unawaited(abortTrigger.then((_) => conventionAborts++));
    }
    return await held.future;
  }

  static http.StreamedResponse _reply(int status) =>
      _replyWith(status, status == 200 ? '{"id": 42}' : "{}");

  static http.StreamedResponse _replyWith(int status, String body) =>
      http.StreamedResponse(
        Stream.value(utf8.encode(body)),
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
  final transport = createTestTransport(net, tokenProvider: session);
  final container = ProviderContainer(
    overrides: [
      authSessionProvider.overrideWithValue(session),
      currentUserRepositoryProvider.overrideWithValue(
        CurrentUserRepository(transport),
      ),
      playerProfileRepositoryProvider.overrideWithValue(
        PlayerProfileRepository(transport),
      ),
      conventionRepositoryProvider.overrideWithValue(
        ConventionRepository(transport),
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

/// Answers the engine's platform-view calls, so a native view such as the
/// Apple button can be created in a widget test. The engine is the real
/// boundary here, so a fake is the only way to run it in a test.
void fakePlatformViews() {
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        ..setMockMethodCallHandler(
          SystemChannels.platform_views,
          (call) async => null,
        );
  addTearDown(
    () =>
        messenger.setMockMethodCallHandler(SystemChannels.platform_views, null),
  );
}
