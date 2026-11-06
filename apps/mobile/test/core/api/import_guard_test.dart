import "dart:io";

import "package:flutter_test/flutter_test.dart";

/// The only `core/api/` files a feature may import: the error model it
/// handles and the cancellation handle it ties to provider disposal.
const _publicApiFiles = {"api_failure.dart", "api_cancellation.dart"};

final _directive = RegExp(
  r'''^\s*(?:import|export|part)\s+(['"])(.+?)\1''',
  multiLine: true,
);

/// The only `core/auth/` files a feature may import: the session interface,
/// its state, result, and failure model, and the providers that expose them.
const _publicAuthFiles = {
  "auth_attempt_result.dart",
  "auth_session.dart",
  "auth_state.dart",
  "auth_failure.dart",
  "auth_providers.dart",
};

/// [target] as a path inside `lib/`, or null when it points elsewhere.
String? _libPath(Uri file, String target) {
  const packagePrefix = "package:tailtag_mobile/";
  if (target.startsWith(packagePrefix)) {
    return target.substring(packagePrefix.length);
  }
  if (target.contains(":")) {
    return null;
  }
  final resolved = file.resolve(target).path;
  const marker = "/lib/";
  final at = resolved.lastIndexOf(marker);
  return at < 0 ? null : resolved.substring(at + marker.length);
}

bool _isForbidden(Uri file, String target) {
  if (target.startsWith("dart:")) {
    return false;
  }
  if (target.startsWith("package:http/") ||
      target.startsWith("package:tailtag_api/") ||
      target.startsWith("package:tailtag_clerk/")) {
    return true;
  }
  final path = _libPath(file, target);
  if (path == null) {
    return false;
  }
  const apiPrefix = "core/api/";
  const authPrefix = "core/auth/";
  if (path.startsWith(apiPrefix)) {
    return !_publicApiFiles.contains(path.substring(apiPrefix.length));
  }
  if (path.startsWith(authPrefix)) {
    return !_publicAuthFiles.contains(path.substring(authPrefix.length));
  }
  return false;
}

/// Every `file: directive` under [root] that bypasses the transport
/// boundary. [root] is a parameter so the guard can be shown to fail.
List<String> findForbiddenImports(Directory root) {
  final violations = <String>[];
  if (!root.existsSync()) {
    return violations;
  }
  for (final entity in root.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith(".dart")) {
      continue;
    }
    for (final match in _directive.allMatches(entity.readAsStringSync())) {
      final target = match.group(2)!;
      if (_isForbidden(entity.uri, target)) {
        violations.add("${entity.path}: $target");
      }
    }
  }
  return violations;
}

/// Every file under [libRoot], outside `core/auth/`, that imports the Clerk
/// bridge package. [libRoot] is a parameter so the guard can be shown to
/// fail.
List<String> findClerkImportsOutsideAuth(Directory libRoot) {
  final violations = <String>[];
  if (!libRoot.existsSync()) {
    return violations;
  }
  for (final entity in libRoot.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith(".dart")) {
      continue;
    }
    final relative = entity.path.substring(libRoot.path.length);
    if (relative.replaceAll(r"\", "/").contains("/core/auth/")) {
      continue;
    }
    for (final match in _directive.allMatches(entity.readAsStringSync())) {
      final target = match.group(2)!;
      if (target.startsWith("package:tailtag_clerk/")) {
        violations.add("${entity.path}: $target");
      }
    }
  }
  return violations;
}

/// Packages that shared UI must not import: network, generated API, Clerk,
/// navigation, and app state.
const _uiForbiddenPackages = [
  "package:http/",
  "package:tailtag_api/",
  "package:tailtag_clerk/",
  "package:go_router/",
  "package:flutter_riverpod/",
];

/// `lib/` folders that shared UI must not import.
const _uiForbiddenPaths = [
  "app/",
  "features/",
  "core/auth/",
  "core/config/",
  "core/session/",
];

/// Every `file: directive` under [uiRoot] that breaks the shared UI
/// boundary. Shared UI may import only `api_failure.dart` from `core/api/`,
/// for the generic error mapping. [uiRoot] is a parameter so the guard can
/// be shown to fail.
List<String> findUiBoundaryImports(Directory uiRoot) {
  final violations = <String>[];
  if (!uiRoot.existsSync()) {
    return violations;
  }
  for (final entity in uiRoot.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith(".dart")) {
      continue;
    }
    for (final match in _directive.allMatches(entity.readAsStringSync())) {
      final target = match.group(2)!;
      final path = _libPath(entity.uri, target);
      final forbidden =
          _uiForbiddenPackages.any(target.startsWith) ||
          (path != null &&
              (_uiForbiddenPaths.any(path.startsWith) ||
                  (path.startsWith("core/api/") &&
                      path != "core/api/api_failure.dart")));
      if (forbidden) {
        violations.add("${entity.path}: $target");
      }
    }
  }
  return violations;
}

/// Every file under [libRoot], outside `showcase/`, that imports a showcase
/// file. The showcase is a separate entry point, so app code must not reach
/// it. [libRoot] is a parameter so the guard can be shown to fail.
List<String> findShowcaseImportsOutsideShowcase(Directory libRoot) {
  final violations = <String>[];
  if (!libRoot.existsSync()) {
    return violations;
  }
  for (final entity in libRoot.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith(".dart")) {
      continue;
    }
    final relative = entity.path.substring(libRoot.path.length);
    if (relative.replaceAll(r"\", "/").startsWith("/showcase/")) {
      continue;
    }
    for (final match in _directive.allMatches(entity.readAsStringSync())) {
      final target = match.group(2)!;
      if (_libPath(entity.uri, target)?.startsWith("showcase/") ?? false) {
        violations.add("${entity.path}: $target");
      }
    }
  }
  return violations;
}

void main() {
  test("lib/core/ui stays business-agnostic", () {
    expect(
      findUiBoundaryImports(Directory("lib/core/ui").absolute),
      isEmpty,
      reason:
          "Shared UI makes no API calls and knows no Clerk, repository, "
          "navigation, or feature state.",
    );
  });

  group("the shared UI rule itself", () {
    const cases = <({String directive, bool flagged})>[
      (
        directive: 'import "package:tailtag_mobile/core/api/api_failure.dart";',
        flagged: false,
      ),
      (directive: 'import "../api/api_failure.dart";', flagged: false),
      (directive: 'import "package:flutter/material.dart";', flagged: false),
      (
        directive:
            'import "package:tailtag_mobile/core/api/api_transport.dart";',
        flagged: true,
      ),
      (
        directive: 'import "package:tailtag_mobile/core/auth/auth_state.dart";',
        flagged: true,
      ),
      (directive: 'import "../session/current_user.dart";', flagged: true),
      (directive: 'import "../../app/router.dart";', flagged: true),
      (directive: 'import "package:go_router/go_router.dart";', flagged: true),
      (
        directive: 'import "package:flutter_riverpod/flutter_riverpod.dart";',
        flagged: true,
      ),
    ];

    for (final c in cases) {
      test("${c.flagged ? "flags" : "allows"} ${c.directive}", () {
        final sandbox = Directory.systemTemp.createTempSync("ui_guard_");
        addTearDown(() => sandbox.deleteSync(recursive: true));
        final ui = Directory("${sandbox.path}/lib/core/ui")
          ..createSync(recursive: true);
        File("${ui.path}/sample.dart")
            .writeAsStringSync("${c.directive}\n\nvoid main() {}\n");

        expect(findUiBoundaryImports(ui), c.flagged ? hasLength(1) : isEmpty);
      });
    }
  });

  test("lib/features never reaches the HTTP client or generated API", () {
    expect(
      findForbiddenImports(Directory("lib/features").absolute),
      isEmpty,
      reason:
          "Features go through core repositories; only api_failure.dart and "
          "api_cancellation.dart of core/api are public.",
    );
  });

  test("only lib/core/auth imports the Clerk bridge package", () {
    expect(
      findClerkImportsOutsideAuth(Directory("lib").absolute),
      isEmpty,
      reason: "Clerk types stay behind AuthSession in lib/core/auth.",
    );
  });

  group("the guard itself", () {
    const cases = <({String directive, bool flagged})>[
      (directive: 'import "package:http/http.dart" as http;', flagged: true),
      (
        directive: "import 'package:tailtag_api/tailtag_api.dart';",
        flagged: true,
      ),
      (
        directive:
            'import "package:tailtag_mobile/core/api/api_transport.dart";',
        flagged: true,
      ),
      (
        directive: 'import "../core/api/tailtag_http_client.dart";',
        flagged: true,
      ),
      (
        directive: 'import "package:tailtag_mobile/core/api/api_failure.dart";',
        flagged: false,
      ),
      (
        directive: 'import "package:tailtag_clerk/tailtag_clerk.dart";',
        flagged: true,
      ),
      (
        directive: 'import "package:tailtag_mobile/core/auth/clerk_auth_session.dart";',
        flagged: true,
      ),
      (
        directive: 'import "../core/auth/clerk_auth_session.dart";',
        flagged: true,
      ),
      (
        directive:
            'import "package:tailtag_mobile/core/auth/auth_session.dart";',
        flagged: false,
      ),
      (directive: '// import "package:http/http.dart";', flagged: false),
    ];

    for (final c in cases) {
      test("${c.flagged ? "flags" : "allows"} ${c.directive}", () {
        final sandbox = Directory.systemTemp.createTempSync("import_guard_");
        addTearDown(() => sandbox.deleteSync(recursive: true));
        final features = Directory("${sandbox.path}/lib/features")
          ..createSync(recursive: true);
        File("${features.path}/sample.dart")
            .writeAsStringSync("${c.directive}\n\nvoid main() {}\n");

        expect(
          findForbiddenImports(features),
          c.flagged ? hasLength(1) : isEmpty,
        );
      });
    }
  });

  test("lib/showcase keeps to the shared UI boundary", () {
    expect(
      findUiBoundaryImports(Directory("lib/showcase").absolute),
      isEmpty,
      reason:
          "The showcase needs no configuration, API, Clerk session, "
          "navigation, or app state.",
    );
  });

  test("only lib/showcase imports the showcase", () {
    expect(
      findShowcaseImportsOutsideShowcase(Directory("lib").absolute),
      isEmpty,
      reason: "Store builds start at lib/main.dart and never reach it.",
    );
  });

  group("the showcase rule itself", () {
    const cases = <({String path, String directive, bool flagged})>[
      (
        path: "lib/app/router.dart",
        directive:
            'import "package:tailtag_mobile/showcase/showcase_app.dart";',
        flagged: true,
      ),
      (
        path: "lib/main.dart",
        directive: 'import "showcase/main.dart";',
        flagged: true,
      ),
      (
        path: "lib/showcase/main.dart",
        directive: 'import "showcase_app.dart";',
        flagged: false,
      ),
    ];

    for (final c in cases) {
      test("${c.flagged ? "flags" : "allows"} ${c.path}: ${c.directive}", () {
        final sandbox = Directory.systemTemp.createTempSync("showcase_guard_");
        addTearDown(() => sandbox.deleteSync(recursive: true));
        File("${sandbox.path}/${c.path}")
          ..createSync(recursive: true)
          ..writeAsStringSync("${c.directive}\n");

        expect(
          findShowcaseImportsOutsideShowcase(Directory("${sandbox.path}/lib")),
          c.flagged ? hasLength(1) : isEmpty,
        );
      });
    }
  });

  group("the Clerk bridge rule itself", () {
    const cases = <({String path, bool flagged})>[
      (path: "lib/core/auth/clerk_auth_session.dart", flagged: false),
      (path: "lib/main.dart", flagged: true),
    ];

    for (final c in cases) {
      test("${c.flagged ? "flags" : "allows"} ${c.path}", () {
        final sandbox = Directory.systemTemp.createTempSync("clerk_guard_");
        addTearDown(() => sandbox.deleteSync(recursive: true));
        File("${sandbox.path}/${c.path}")
          ..createSync(recursive: true)
          ..writeAsStringSync(
            'import "package:tailtag_clerk/tailtag_clerk.dart";\n',
          );

        expect(
          findClerkImportsOutsideAuth(Directory("${sandbox.path}/lib")),
          c.flagged ? hasLength(1) : isEmpty,
        );
      });
    }
  });
}
