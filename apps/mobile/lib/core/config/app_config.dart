import "dart:convert";

/// Dart-define key holding the TailTag API base URL.
const String apiBaseUrlKey = "TAILTAG_API_BASE_URL";

/// Dart-define key holding the Clerk publishable key.
const String clerkPublishableKeyKey = "CLERK_PUBLISHABLE_KEY";

/// Key used for problems that concern the whole define file, not one value.
const String _fileKey = "file";

const String _clerkTestPrefix = "pk_test_";

/// Validated compile-time configuration for the TailTag mobile app.
///
/// This library is pure Dart so the same validation runs inside the app and
/// under `dart run` in the contributor tooling.
final class AppConfig {
  const new _({required this.apiBaseUrl, required this.clerkPublishableKey});

  /// Reads both keys with `String.fromEnvironment` and validates them.
  factory fromEnvironment() => AppConfig.parse({
    apiBaseUrlKey: const String.fromEnvironment(apiBaseUrlKey),
    clerkPublishableKeyKey: const String.fromEnvironment(
      clerkPublishableKeyKey,
    ),
  });

  /// Validates raw string values keyed by the two configuration key names.
  ///
  /// Missing keys are treated as empty strings. Throws [AppConfigException]
  /// listing every problem, API URL first and Clerk key second.
  factory parse(Map<String, String> values) {
    return _build(values, const {});
  }

  /// Parses the text of a `--dart-define-from-file` JSON object.
  ///
  /// Malformed JSON, a non-object document, or a non-string value for either
  /// required key is reported as a problem. Other keys are ignored.
  factory parseDefinesJson(String jsonText) {
    final Object? decoded;
    try {
      decoded = jsonDecode(jsonText);
    } on FormatException {
      throw const AppConfigException([
        AppConfigProblem(key: _fileKey, message: "is not valid JSON"),
      ]);
    }
    if (decoded is! Map<String, Object?>) {
      throw const AppConfigException([
        AppConfigProblem(key: _fileKey, message: "must be a JSON object"),
      ]);
    }

    final values = <String, String>{};
    final shapeProblems = <String, AppConfigProblem>{};
    for (final key in [apiBaseUrlKey, clerkPublishableKeyKey]) {
      final value = decoded[key];
      if (value == null) {
        continue;
      }
      if (value is String) {
        values[key] = value;
      } else {
        shapeProblems[key] = AppConfigProblem(
          key: key,
          message: "must be a JSON string",
        );
      }
    }
    return _build(values, shapeProblems);
  }

  /// The normalized API origin: `scheme://host[:port]` with no trailing slash.
  final Uri apiBaseUrl;

  /// The Clerk Development publishable key (`pk_test_...`).
  final String clerkPublishableKey;
}

AppConfig _build(
  Map<String, String> values,
  Map<String, AppConfigProblem> shapeProblems,
) {
  final problems = <AppConfigProblem>[];

  Uri? apiBaseUrl;
  final apiShapeProblem = shapeProblems[apiBaseUrlKey];
  if (apiShapeProblem != null) {
    problems.add(apiShapeProblem);
  } else {
    final result = _validateApiBaseUrl(values[apiBaseUrlKey] ?? "");
    apiBaseUrl = result.url;
    if (result.problem != null) {
      problems.add(
        AppConfigProblem(key: apiBaseUrlKey, message: result.problem!),
      );
    }
  }

  String? clerkKey;
  final clerkShapeProblem = shapeProblems[clerkPublishableKeyKey];
  if (clerkShapeProblem != null) {
    problems.add(clerkShapeProblem);
  } else {
    final value = values[clerkPublishableKeyKey] ?? "";
    final problem = _validateClerkKey(value);
    if (problem == null) {
      clerkKey = value;
    } else {
      problems.add(
        AppConfigProblem(key: clerkPublishableKeyKey, message: problem),
      );
    }
  }

  if (problems.isNotEmpty || apiBaseUrl == null || clerkKey == null) {
    throw AppConfigException(problems);
  }
  return AppConfig._(apiBaseUrl: apiBaseUrl, clerkPublishableKey: clerkKey);
}

({Uri? url, String? problem}) _validateApiBaseUrl(String value) {
  if (value.isEmpty) {
    return (url: null, problem: "is required");
  }
  if (value != value.trim()) {
    return (url: null, problem: "must not have leading or trailing whitespace");
  }

  const originProblem =
      "must be an absolute origin of the form scheme://host[:port] with no "
      "path, query, fragment, or userinfo";
  final uri = Uri.tryParse(value);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return (url: null, problem: originProblem);
  }
  if (uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != "/")) {
    return (url: null, problem: originProblem);
  }

  final host = uri.host.toLowerCase();
  final isLoopback = host == "127.0.0.1" || host == "localhost";
  final allowed = uri.scheme == "https" || (uri.scheme == "http" && isLoopback);
  if (!allowed) {
    return (
      url: null,
      problem:
          "must use https, or http only for the 127.0.0.1 or localhost host",
    );
  }

  return (
    url: Uri(
      scheme: uri.scheme,
      host: host,
      port: uri.hasPort ? uri.port : null,
    ),
    problem: null,
  );
}

String? _validateClerkKey(String value) {
  if (value.isEmpty) {
    return "is required";
  }
  if (value.startsWith("pk_live_") || value.startsWith("sk_")) {
    return "must be a Development publishable key; live and secret keys are "
        "forbidden in the app";
  }
  if (!value.startsWith(_clerkTestPrefix)) {
    return "must start with $_clerkTestPrefix";
  }
  if (value == _clerkTestPrefix) {
    return "is incomplete; paste the full Development publishable key";
  }
  return null;
}

/// One validation problem; [message] never contains the supplied value.
final class AppConfigProblem {
  /// Creates a problem for [key] described by [message].
  const new({required this.key, required this.message});

  /// The configuration key name, or `file` for a problem with the define file.
  final String key;

  /// What is wrong, without echoing the supplied value.
  final String message;
}

/// Thrown when configuration is missing or invalid; lists every problem.
final class AppConfigException implements Exception {
  /// Creates an exception for a non-empty list of [problems].
  const new(this.problems);

  /// Every problem found, in key order.
  final List<AppConfigProblem> problems;

  @override
  String toString() => problems
      .map((problem) => "${problem.key}: ${problem.message}")
      .join("\n");
}
