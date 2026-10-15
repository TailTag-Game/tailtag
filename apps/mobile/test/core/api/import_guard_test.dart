import "dart:io";

import "package:flutter_test/flutter_test.dart";

/// The only `core/api/` files a feature may import: the error model it
/// handles and the cancellation handle it ties to provider disposal.
const _publicApiFiles = {"api_failure.dart", "api_cancellation.dart"};

final _directive = RegExp(
  r'''^\s*(?:import|export|part)\s+(['"])(.+?)\1''',
  multiLine: true,
);

bool _isForbidden(Uri file, String target) {
  if (target.startsWith("dart:")) {
    return false;
  }
  if (target.startsWith("package:http/") ||
      target.startsWith("package:tailtag_api/")) {
    return true;
  }
  const apiPackagePrefix = "package:tailtag_mobile/core/api/";
  final String? apiFile;
  if (target.startsWith(apiPackagePrefix)) {
    apiFile = target.substring(apiPackagePrefix.length);
  } else if (!target.contains(":")) {
    final resolved = file.resolve(target).path;
    const marker = "/lib/core/api/";
    final at = resolved.indexOf(marker);
    apiFile = at < 0 ? null : resolved.substring(at + marker.length);
  } else {
    apiFile = null;
  }
  return apiFile != null && !_publicApiFiles.contains(apiFile);
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
}
