# Flutter contributor tooling — implementation plan

Contract: [2026-10-12-mobile-contributor-tooling.md](2026-10-12-mobile-contributor-tooling.md)
(issue #132). Work happens on `feat/132-mobile-contributor-tooling`.

## Global constraints

- Use only the repository-pinned toolchain through `fvm`; add no dependency
  and do not change `pubspec.yaml` or `pubspec.lock`.
- Keep the default `./scripts/doctor.sh` result unchanged (AC12).
- Never print the Clerk value or call `fvm api context`.
- Do not change CI workflows, backend code, Android manifests, or iOS plists.

## Unit order

1. **Tests first (independent test author):** U1 Dart tests and U2
   `scripts/test_doctor.sh` cases from the frozen test surface. Red evidence is
   expected: missing `AppConfig`, `runTailTagApp`, and `--mobile`.
2. **U1 implementation:** `AppConfig`, provider, `main.dart`,
   `tool/check_config.dart`, example config, `.gitignore`.
3. **U2 implementation:** Make targets, `scripts/mobile_run.sh`,
   `doctor.sh --mobile`.
4. **U3 documentation.**
5. **Review:** one reviewer for U1, one for U2+U3, then a whole-change review.
6. **Proof (AC22, AC24):** recorded manual Make/run evidence and the
   throwaway in-app `/health/live` probe on the iOS Simulator and an Android
   API 28+ emulator against Local and Railway Development. The probe is never
   committed.

## Verification

- `make mobile-check`
- `bash scripts/test_doctor.sh`
- `./scripts/doctor.sh` and `./scripts/doctor.sh --mobile`
- `git diff --check`
