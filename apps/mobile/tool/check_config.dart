// Command-line configuration check; printing is its output channel.
// ignore_for_file: avoid_print
import "dart:io";

import "package:tailtag_mobile/core/config/app_config.dart";

const _usageExit = 64;
const _problemsExit = 1;
const _missingExit = 2;

/// Validates a `--dart-define-from-file` JSON file.
///
/// Exit codes: 0 valid (prints the normalized API origin), 1 invalid
/// (problems on stderr), 2 missing file, 64 usage.
void main(List<String> arguments) {
  if (arguments.length != 1) {
    stderr.writeln("usage: dart run tool/check_config.dart <config.json>");
    exit(_usageExit);
  }

  final file = File(arguments.single);
  if (!file.existsSync()) {
    stderr.writeln("missing: ${arguments.single}");
    exit(_missingExit);
  }

  try {
    final config = AppConfig.parseDefinesJson(file.readAsStringSync());
    print(config.apiBaseUrl);
  } on AppConfigException catch (error) {
    stderr.writeln(error);
    exit(_problemsExit);
  }
}
