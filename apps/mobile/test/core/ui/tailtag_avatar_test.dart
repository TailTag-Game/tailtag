import "dart:async";
import "dart:io";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";

import "support/ui_test_app.dart";

/// A valid 1 by 1 transparent PNG.
const List<int> _png = [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, //
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00, //
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, //
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, //
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82, //
];

/// Runs [body] while every image request answers [statusCode] with [_png].
///
/// This fakes the network boundary that `Image.network` crosses. The hook
/// must be unset before the test ends, so it is not a tear-down.
Future<void> _servingImages(
  int statusCode,
  Future<void> Function() body,
) async {
  debugNetworkImageHttpClientProvider = () => _FakeHttpClient(statusCode);
  try {
    await body();
  } finally {
    debugNetworkImageHttpClientProvider = null;
  }
}

/// Pumps real time until [finder] matches, because image decoding runs
/// outside the fake test clock.
Future<void> _pumpUntil(WidgetTester tester, Finder finder) async {
  for (var i = 0; i < 500 && finder.evaluate().isEmpty; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pump();
  }
}

void main() {
  group("initials", () {
    const cases = {
      "Finn the Panther": "FT",
      "  sable  ": "S",
      "émile zola": "ÉZ",
      "🦊 Fox": "🦊F",
      "   ": "",
    };
    for (final MapEntry(key: name, value: initials) in cases.entries) {
      test("'$name' gives '$initials'", () {
        expect(TailTagAvatar.initialsOf(name), initials);
      });
    }
  });

  const kinds = {
    AvatarKind.player: (
      Icons.person_outlined,
      (TokenColors.primaryContainer, TokenColors.onPrimaryContainer),
    ),
    AvatarKind.fursuit: (
      Icons.pets_outlined,
      (TokenColors.tertiaryContainer, TokenColors.onTertiaryContainer),
    ),
  };
  for (final MapEntry(key: kind, value: (icon, (background, foreground)))
      in kinds.entries) {
    testWidgets("a $kind placeholder uses its colors, and its icon when the "
        "name is empty", (tester) async {
      await tester.pumpWidget(themed(TailTagAvatar(name: "", kind: kind)));
      expect(tester.widget<Icon>(find.byIcon(icon)).color, foreground);
      expect(
        tester.widget<ColoredBox>(find.byType(ColoredBox).last).color,
        background,
      );

      await tester.pumpWidget(themed(TailTagAvatar(name: "Sable", kind: kind)));
      expect(find.byIcon(icon), findsNothing);
      expect(tester.widget<Text>(find.text("S")).style?.color, foreground);
    });
  }

  const sizes = {AvatarSize.small: 40.0, AvatarSize.large: 80.0};
  for (final MapEntry(key: size, value: diameter) in sizes.entries) {
    testWidgets("a $size avatar is a $diameter circle at any text scale", (
      tester,
    ) async {
      for (final scale in [1.0, 2.0]) {
        await tester.pumpWidget(
          themed(
            Center(
              child: TailTagAvatar(
                name: "Finn Panther",
                kind: AvatarKind.player,
                size: size,
              ),
            ),
            textScale: scale,
          ),
        );
        expect(
          tester.getSize(find.byType(TailTagAvatar)),
          Size.square(diameter),
        );
        expect(find.byType(ClipOval), findsOneWidget);
      }
      // The initials scale with the avatar, not with the text.
      await tester.pumpWidget(
        themed(
          Center(
            child: TailTagAvatar(
              name: "Finn Panther",
              kind: AvatarKind.player,
              size: size,
            ),
          ),
        ),
      );
      final atOne = tester.getSize(find.text("FP"));
      await tester.pumpWidget(
        themed(
          Center(
            child: TailTagAvatar(
              name: "Finn Panther",
              kind: AvatarKind.player,
              size: size,
            ),
          ),
          textScale: 2,
        ),
      );
      expect(tester.getSize(find.text("FP")), atOne);
    });
  }

  for (final MapEntry(key: size, value: diameter) in sizes.entries) {
    testWidgets("a $size avatar decodes its image at twice its pixel width", (
      tester,
    ) async {
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        themed(
          TailTagAvatar(
            name: "Sable",
            kind: AvatarKind.fursuit,
            imageUrl: "https://media.example/sable.png",
            size: size,
          ),
        ),
      );
      final image = tester.widget<Image>(find.byType(Image)).image;
      expect(image, isA<ResizeImage>());
      expect((image as ResizeImage).width, (diameter * 2 * 3).ceil());
    });
  }

  testWidgets("a photo avatar is a square at the full width of its parent", (
    tester,
  ) async {
    await tester.pumpWidget(
      themed(
        const Center(
          child: SizedBox(
            width: 200,
            child: TailTagAvatar(
              name: "Sable",
              kind: AvatarKind.fursuit,
              size: AvatarSize.photo,
            ),
          ),
        ),
      ),
    );
    expect(tester.getSize(find.byType(TailTagAvatar)), const Size.square(200));
    expect(find.byType(ClipRRect), findsOneWidget);
  });

  testWidgets("the placeholder shows while the image loads, then the image", (
    tester,
  ) async {
    await _servingImages(200, () async {
      await tester.pumpWidget(
        themed(
          const TailTagAvatar(
            name: "Sable",
            kind: AvatarKind.fursuit,
            imageUrl: "https://media.example/sable.png",
          ),
        ),
      );
      expect(find.text("S"), findsOneWidget);
      expect(find.byType(RawImage), findsNothing);

      await _pumpUntil(tester, find.byType(RawImage));
      expect(find.byType(RawImage), findsOneWidget);
      expect(find.text("S"), findsNothing);
    });
  });

  // An expired presigned media URL answers 403.
  testWidgets("the placeholder stays when the image fails", (tester) async {
    await _servingImages(403, () async {
      await tester.pumpWidget(
        themed(
          const TailTagAvatar(
            name: "Sable",
            kind: AvatarKind.fursuit,
            imageUrl: "https://media.example/expired.png",
          ),
        ),
      );
      // Wait until the image request has failed, so the error builder runs.
      await tester.runAsync(
        () => precacheImage(
          const NetworkImage("https://media.example/expired.png"),
          tester.element(find.byType(TailTagAvatar)),
          onError: (_, _) {},
        ),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
      expect(find.text("S"), findsOneWidget);
      expect(find.byType(RawImage), findsNothing);
    });
  });

  testWidgets("the avatar adds nothing to the semantics tree", (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      themed(const TailTagAvatar(name: "Sable Fox", kind: AvatarKind.fursuit)),
    );
    expect(find.bySemanticsLabel(RegExp("SF")), findsNothing);
    semantics.dispose();
  });
}

final class _FakeHttpClient extends Fake implements HttpClient {
  new(this.statusCode);

  final int statusCode;

  @override
  bool autoUncompress = true;

  @override
  Future<HttpClientRequest> getUrl(Uri url) async => _FakeRequest(statusCode);
}

final class _FakeRequest extends Fake implements HttpClientRequest {
  new(this.statusCode);

  final int statusCode;

  @override
  Future<HttpClientResponse> close() async => _FakeResponse(statusCode);
}

final class _FakeResponse extends Stream<List<int>>
    implements HttpClientResponse {
  new(this.statusCode);

  @override
  final int statusCode;

  @override
  int get contentLength => _png.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.value(_png).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError(invocation.memberName.toString());
}
