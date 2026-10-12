import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/config/app_config.dart";

const _validUrl = "https://dev.tailtag.app";
const _validKey = "pk_test_abc123";

/// A rejected value and the distinctive fragment that must never be echoed.
typedef _Rejection = ({String label, String value, String? secret});

AppConfigException _rejected(Map<String, String> values) {
  try {
    AppConfig.parse(values);
  } on AppConfigException catch (error) {
    return error;
  }
  fail("expected AppConfigException for $values");
}

void _expectNoEcho(AppConfigException error, String value, String? secret) {
  final texts = [error.toString(), ...error.problems.map((p) => p.message)];
  for (final text in texts) {
    if (value.isNotEmpty) {
      expect(text, isNot(contains(value)));
    }
    if (secret != null) {
      expect(text, isNot(contains(secret)));
    }
  }
}

void main() {
  group("API base URL", () {
    const accepted = <String, String>{
      "https://dev.tailtag.app": "https://dev.tailtag.app",
      "https://dev.tailtag.app/": "https://dev.tailtag.app",
      "https://dev.tailtag.app:8443": "https://dev.tailtag.app:8443",
      "http://127.0.0.1:8000": "http://127.0.0.1:8000",
      "http://127.0.0.1:8000/": "http://127.0.0.1:8000",
      "http://localhost:8000": "http://localhost:8000",
    };

    accepted.forEach((input, normalized) {
      test("accepts $input as $normalized", () {
        final config = AppConfig.parse({
          apiBaseUrlKey: input,
          clerkPublishableKeyKey: _validKey,
        });

        expect(config.apiBaseUrl.toString(), normalized);
        expect(config.clerkPublishableKey, _validKey);
      });
    });

    const rejected = <_Rejection>[
      (label: "empty", value: "", secret: null),
      (
        label: "http to a LAN host",
        value: "http://192.168.7.50:8000",
        secret: "192.168.7.50",
      ),
      (
        label: "http to a public host",
        value: "http://lanhost.example",
        secret: "lanhost.example",
      ),
      (
        label: "loopback name as a prefix of another host",
        value: "http://localhost.badhost.example:8000",
        secret: "badhost.example",
      ),
      (
        label: "path",
        value: "https://dev.tailtag.app/pathsecret/v1",
        secret: "pathsecret",
      ),
      (
        label: "query",
        value: "https://dev.tailtag.app/?querysecret=1",
        secret: "querysecret",
      ),
      (
        label: "fragment",
        value: "https://dev.tailtag.app/#fragsecret",
        secret: "fragsecret",
      ),
      (
        label: "userinfo",
        value: "https://user:hunter2@dev.tailtag.app",
        secret: "hunter2",
      ),
      (
        label: "unsupported scheme",
        value: "ftp://files.example",
        secret: "files.example",
      ),
      (
        label: "missing scheme",
        value: "hostonly.example:8000",
        secret: "hostonly.example",
      ),
      (label: "missing host", value: "https://", secret: null),
      (
        label: "leading and trailing whitespace",
        value: " https://padded.example ",
        secret: "padded.example",
      ),
    ];

    for (final rejection in rejected) {
      test("rejects ${rejection.label} without echoing the value", () {
        final error = _rejected({
          apiBaseUrlKey: rejection.value,
          clerkPublishableKeyKey: _validKey,
        });

        expect(error.problems.map((p) => p.key), [apiBaseUrlKey]);
        _expectNoEcho(error, rejection.value, rejection.secret);
      });
    }
  });

  group("Clerk publishable key", () {
    const rejected = <_Rejection>[
      (label: "empty", value: "", secret: null),
      (
        label: "live key",
        value: "pk_live_livesecret123",
        secret: "livesecret123",
      ),
      (
        label: "secret key",
        value: "sk_test_secretsecret123",
        secret: "secretsecret123",
      ),
      (
        label: "unrecognized prefix",
        value: "notakey_prefixsecret",
        secret: "prefixsecret",
      ),
      (label: "bare test prefix", value: "pk_test_", secret: null),
    ];

    for (final rejection in rejected) {
      test("rejects ${rejection.label} without echoing the value", () {
        final error = _rejected({
          apiBaseUrlKey: _validUrl,
          clerkPublishableKeyKey: rejection.value,
        });

        expect(error.problems.map((p) => p.key), [clerkPublishableKeyKey]);
        _expectNoEcho(error, rejection.value, rejection.secret);
      });
    }
  });

  group("problem reporting", () {
    test("reports every problem in key order, one line each", () {
      final invalidValues = [
        {
          apiBaseUrlKey: "http://192.168.7.50:8000",
          clerkPublishableKeyKey: "sk_live_x",
        },
        // Missing keys are treated as empty.
        <String, String>{},
      ];

      for (final values in invalidValues) {
        final error = _rejected(values);

        expect(error.problems.map((p) => p.key), [
          apiBaseUrlKey,
          clerkPublishableKeyKey,
        ]);

        final lines = error.toString().trim().split("\n");
        expect(lines, hasLength(2));
        expect(lines[0], startsWith("$apiBaseUrlKey: "));
        expect(lines[1], startsWith("$clerkPublishableKeyKey: "));
      }
    });
  });

  group("parseDefinesJson", () {
    test("parses a define file and ignores extra keys", () {
      final config = AppConfig.parseDefinesJson(
        '{"$apiBaseUrlKey": "$_validUrl/", "$clerkPublishableKeyKey": '
        '"$_validKey", "UNRELATED": 42}',
      );

      expect(config.apiBaseUrl.toString(), _validUrl);
      expect(config.clerkPublishableKey, _validKey);
    });

    final shapeFailures = <String, String>{
      "malformed JSON": '{"$apiBaseUrlKey": "$_validUrl"',
      "an array": '["$_validUrl"]',
      "a string": '"$_validUrl"',
    };

    shapeFailures.forEach((label, text) {
      test("reports $label as a problem", () {
        expect(
          () => AppConfig.parseDefinesJson(text),
          throwsA(
            isA<AppConfigException>().having(
              (e) => e.problems,
              "problems",
              isNotEmpty,
            ),
          ),
        );
      });
    });

    test("does not leak file contents when the JSON is malformed", () {
      const text = '{"$clerkPublishableKeyKey": "pk_test_leakedtoken99"';

      try {
        AppConfig.parseDefinesJson(text);
        fail("expected AppConfigException");
      } on AppConfigException catch (error) {
        _expectNoEcho(error, text, "leakedtoken99");
      }
    });

    test("names the key when a required value is not a string", () {
      try {
        AppConfig.parseDefinesJson(
          '{"$apiBaseUrlKey": 8000, "$clerkPublishableKeyKey": "$_validKey"}',
        );
        fail("expected AppConfigException");
      } on AppConfigException catch (error) {
        expect(error.toString(), contains(apiBaseUrlKey));
      }
    });

    test("applies the same value rules as parse", () {
      try {
        AppConfig.parseDefinesJson(
          '{"$apiBaseUrlKey": "https://dev.tailtag.app/pathsecret", '
          '"$clerkPublishableKeyKey": "sk_live_filesecret"}',
        );
        fail("expected AppConfigException");
      } on AppConfigException catch (error) {
        expect(error.problems.map((p) => p.key), [
          apiBaseUrlKey,
          clerkPublishableKeyKey,
        ]);
        _expectNoEcho(error, "sk_live_filesecret", "pathsecret");
      }
    });
  });
}
