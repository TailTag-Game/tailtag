# Mobile journey evidence, November 2026

Issue: [#483](https://github.com/TailTag-Game/tailtag/issues/483). Checklist: [mobile-journey-checklist.md](mobile-journey-checklist.md). Spec: [refinement comment](https://github.com/TailTag-Game/tailtag/issues/483#issuecomment-6746970794).

Status on 2026-11-09: every live row passed on each phone that runs it. The pass found no defect. The automated checks and the profile builds passed on the frozen commit.

## Pass details

| Item | Value |
| --- | --- |
| Frozen application commit | `a8a9d307fe8228b83683d58f1865d6f41f6db9d4` |
| Environment | Render Development |
| Development API commit | `a8a9d307fe8228b83683d58f1865d6f41f6db9d4`, live on Render Development |
| Android device and OS | Pixel 11, Android 17 (API 37) |
| iOS device and OS | iPhone 17 Pro, iOS 27.2 |
| Build mode | Flutter profile on physical devices |
| Readiness note | [Posted on 2026-11-09](https://github.com/TailTag-Game/tailtag/issues/483#issuecomment-6747662837). It covers G and A. E1, E2, and D did not exist yet, because the pass created them in the app. |
| Tester | The owner, FinnThePanther |
| Pass dates | 2026-11-09 |

## Blockers

| ID | Blocker | Owner | Criteria held |
| --- | --- | --- | --- |
| B2 | Resolved on 2026-11-09. #475 now makes Apple iOS only. | FinnThePanther | AC41 |

## Validation on the frozen commit

| Command | Host | Result |
| --- | --- | --- |
| `task mobile-check` | macOS | Passed on 2026-11-09. `flutter analyze` found no issues, and 526 tests passed. |
| `fvm flutter build apk --profile --dart-define-from-file=config/development.json` | macOS | Passed on 2026-11-09. |
| `fvm flutter build ios --profile --no-codesign --dart-define-from-file=config/development.json` | macOS | Passed on 2026-11-09. A signed build ran in the pass. |
| `git diff --check a8a9d30^ a8a9d30` | macOS | Passed on 2026-11-09. |

`android/app/build.gradle.kts` keeps `minSdk = 26`. The iOS project keeps `IPHONEOS_DEPLOYMENT_TARGET = 17.0`. These values satisfy AC17 for the frozen commit.

## Live results

Each result is Pass, Fail with a defect link, or Blocked with a reason. N/A means that the row does not run on that platform.

| Row | Android | iOS | Log window counts |
| --- | --- | --- | --- |
| S-01 | Pass | Pass | None |
| J-01 | Pass | Pass | None |
| J-02 | Pass | Pass | None |
| J-03 and J-04 | Pass | Pass | Android W1, 18:10:46Z to 18:12:46Z on 2026-11-09: 1 `PUT /api/profile/` 200, 1 enrollment `POST` 201, and 3 control reads. iOS W1, 18:50:59Z to 18:52:12Z: the same counts. |
| J-05 and J-06 | Pass | Pass | Android W2, 18:12:55Z to 18:14:39Z on 2026-11-09: no write, and 5 control reads. iOS W2, 18:55:22Z to 18:57:21Z: no write, and 5 control reads. An earlier iOS W2 had no control reads, so the tester repeated the rows. |
| J-07 | Pass | Pass | None |
| J-08 | Pass | Pass | Android W3, 18:15:49Z to 18:17:49Z on 2026-11-09: 1 `PUT /api/conventions/active/` 200, no enrollment `POST`, and 2 control reads. iOS W3, 19:00:29Z to 19:01:06Z: the same counts. |
| J-09 | Pass | Pass | None |
| J-10 | Pass | Pass | None |
| J-11 | Pass | Pass | Android W4, 18:18:57Z to 18:20:40Z on 2026-11-09: no write, and 3 control reads. iOS W4, 19:03:02Z to 19:03:28Z: the same counts. |
| P-01 | Pass | Pass | None |
| P-02 | Pass | Pass | Android W5, 18:21:35Z to 18:23:21Z on 2026-11-09: no write, and 3 control reads. iOS W5, 19:04:18Z to 19:05:05Z: the same counts. |
| P-03 | Pass | Pass | Android W6, 18:26:11Z to 18:27:01Z on 2026-11-09: no write, and 3 control reads. iOS W6, 19:05:25Z to 19:05:56Z: the same counts. |
| P-04 | Pass | Pass | None |
| I-01 to I-05 | Pass | Pass | None |
| N-01 and N-02 | Pass | Pass | None |
| N-03 | Pass | Pass | Android W7, 18:32:25Z to 18:34:58Z on 2026-11-09: no write, and 2 control reads. The N-02 write did not reach the server. The app kept the selected convention and said that entry did not happen. iOS W7, 19:10:33Z to 19:11:15Z: the same counts and the same outcome. |
| F-01 | Pass | Pass | None |
| F-02 and F-03 | Pass | Pass | None |
| G-01 and G-02 | Pass | Pass | None |
| G-03 and G-04 | Pass | N/A | None |
| G-05 | Pass | Pass | None |
| G-06 | Pass | Pass | Android W8, 18:42:50Z to 18:43:46Z on 2026-11-09: no write, and 3 control reads. iOS W8, 19:15:16Z to 19:16:11Z: the same counts. |
| G-07 | Pass | Pass | Android W9, 18:44:31Z to 18:45:30Z on 2026-11-09: no write, and 3 control reads. iOS W9, 19:16:47Z to 19:17:46Z: the same counts. |
| A-01 | Pass | N/A | None |
| A-02 to A-05 | N/A | Pass | None |
| A-06 | N/A | Pass | W10, 19:19:06Z to 19:20:03Z on 2026-11-09: no write, and 3 control reads. |
| A-07 | N/A | Pass | W11, 19:20:20Z to 19:20:57Z on 2026-11-09: no write, and 3 control reads. |
| D-01 | Pass | Pass | None |

## Accessibility results

The owner ran these rows independently of the route in the checklist and reported these results. On 2026-11-09, the owner waived log and screenshot proof for these rows.

| Screen | Screen reader, Android | Screen reader, iOS | 200%, Android | AX3, iOS | Keyboard, Android | Keyboard, iOS |
| --- | --- | --- | --- | --- | --- | --- |
| Account access | Pass | Pass | Pass | Pass | Pass | Pass |
| Email entry | Pass | Pass | Pass | Pass | Pass | Pass |
| Code entry | Pass | Pass | Pass | Pass | Pass | Pass |
| Onboarding | Pass | Pass | Pass | Pass | Pass | Pass |
| Account unavailable | Pass | Pass | Pass | Pass | Pass | Pass |
| Picker | Pass | Pass | Pass | Pass | Pass | Pass |
| Home | Pass | Pass | Pass | Pass | Pass | Pass |
| Passkeys | Pass | Pass | Pass | Pass | Pass | Pass |

## Reused and automated evidence

The source commit and the path diff apply to each reused row.

| Row | Source | Commit and path diff |
| --- | --- | --- |
| U-01 | #480 AC39, `test/features/account_access/provider_access_test.dart:373`, and `test/features/passkeys/passkey_flow_test.dart:176` | #480 and #490 record no commit for the emulator run. The bounding range is `013e7e5` to `5878ee6`, and the owner accepted a range on 2026-11-09. `git diff 5878ee6 a8a9d30` is empty for `apps/mobile/packages`, `apps/mobile/ios`, `apps/mobile/android`, `lib/core/auth`, `lib/features/account_access`, and `lib/features/passkeys`. |
| U-02 | `test/app/entry_flow_test.dart:416` and `:617`, `test/features/conventions/convention_flow_test.dart:1507`, and `test/features/onboarding/onboarding_flow_test.dart:536` | These tests passed on `a8a9d30`. |
| U-03 | The iPhone 17 Pro simulator proxy run in [#494](https://github.com/TailTag-Game/tailtag/pull/494) | #494 records no commit for the build. The bounding range is `440b618` to `a8a9d30`, and the owner accepted a range on 2026-11-09. `git diff 440b618 a8a9d30 -- apps/mobile/lib` changes only `core/api/api_transport.dart` and `core/conventions/convention_repository.dart`. Those changes add a response-key check for one read, and writes pass no required keys. |
| U-04 | `test/app/entry_flow_test.dart:341` for onboarding, account unavailable, picker, and home. `test/features/account_access/account_access_flow_test.dart:341` for account access, email entry, and code entry. | These tests passed on `a8a9d30`. |
| U-05 | The removal cases in `test/core/auth/clerk_auth_session_test.dart`, which cover Google and Apple with the provider on and off | These tests passed on `a8a9d30`. A live run cannot show which branch of the rule allowed a removal. |

U-01 covers Android only. iOS has no natural unavailable state, because every supported iOS version offers passkeys.

The Passkeys screen has no contrast or target-size test. The owner accepted this gap on 2026-11-09.

## Map to #475 acceptance criteria

The test paths are under `apps/mobile/test/`. "Live passed" means that every listed live row passed on each platform that it covers.

| #475 | Live rows | Reused or automated evidence | State |
| --- | --- | --- | --- |
| AC1 | J-01, G-01, A-02 | None | Live passed. Apple is iOS only, as #475 now states. |
| AC2 | J-11, P-03, G-06, A-06 | None | Live passed |
| AC3 | G-03, G-04, A-03, A-04 | U-05 | Live passed |
| AC4 | P-02, G-07, A-07 | U-01 | Live passed. No live row dismisses the passkey sign-in sheet on the account screen. |
| AC5 | J-05 | `app/entry_flow_test.dart:36`, `:114`, and `:520` | Live passed |
| AC6 | J-03, J-04 | None | Live passed |
| AC7 | J-02 | `features/onboarding/onboarding_flow_test.dart:186` | Live passed |
| AC8 | F-02, F-03 | None | Live passed |
| AC9 | J-03, J-08, I-05 | `features/conventions/convention_flow_test.dart:316`, `:390`, and `:410` | Live passed |
| AC10 | J-04 | `features/conventions/convention_flow_test.dart:473` and `:483` | Live passed |
| AC11 | J-08, J-09 | None | Live passed |
| AC12 | J-04 | None | Live passed |
| AC13 | J-05, J-06 | None | Live passed |
| AC14 | F-01 | `features/conventions/convention_flow_test.dart:916`, for paused, completed, and cancelled | Live passed. F-01 covers paused only. |
| AC15 | N-01, N-02, N-03 | U-03, `features/conventions/convention_flow_test.dart:752`, and `features/onboarding/onboarding_flow_test.dart:310` | Live passed |
| AC16 | I-01 to I-05 | U-02, `app/entry_flow_test.dart:550`, and `features/conventions/convention_flow_test.dart:640` and `:1550` | Live passed |
| AC17 | X-01 to X-05 | U-04, and `features/conventions/convention_flow_test.dart:303` for Tab order on the home and the picker | Live passed. The Passkeys gap above applies. #473 tracks the focus order rule. |
| AC18 | Every live row | None | Live passed |

## End state

After the pass on 2026-11-09, the owner confirmed that C1, C2, and C3 have the status Active and that D is enabled. The pass deleted no reachable player progress. The owner deleted only the Google proof user that the Android rows created.
