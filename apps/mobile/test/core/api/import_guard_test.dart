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
/// its state and failure model, and the providers that expose them.
const _publicAuthFiles = {
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

void main() {
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
