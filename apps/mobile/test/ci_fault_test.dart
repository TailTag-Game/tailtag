// Throwaway #133 fault: failing test.
import "package:flutter_test/flutter_test.dart";

void main() {
  test("ci fault proof fails on purpose", () {
    expect(1 + 1, 3);
  });
}
