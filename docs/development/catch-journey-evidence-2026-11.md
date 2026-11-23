# Mobile catch journey evidence, November 2026

Issue: [#513](https://github.com/TailTag-Game/tailtag/issues/513). Checklist: [catch-journey-checklist.md](catch-journey-checklist.md). Spec: [refinement comment](https://github.com/TailTag-Game/tailtag/issues/513#issuecomment-6967708958).

Status: the pass is complete. Every row passed. T-04 is Pass by owner override and did not run on a device.

## Pass details

| Item | Value |
| --- | --- |
| Frozen application commit | `8840cdd37b7dce6ec8b2f35b13c1cfe114d2596a` |
| Environment | Render Development |
| Development API commit | `9aba916322f9c37d43ff2fbc41b94e23738d38a3`. The `services/api` path diff to the frozen commit is empty. |
| Catch request gate | On. An unauthenticated `POST /api/catches/preview/` returned 401 on 11-19-2026. |
| Android device and OS | Pixel 11, Android 17 (API 37) |
| iOS device and OS | iPhone 17 Pro, iOS 27.2.1 |
| Build mode | Flutter profile on physical devices |
| Readiness note | [Posted on 11-19-2026](https://github.com/TailTag-Game/tailtag/issues/513#issuecomment-7018768861) |
| Tester | The owner, FinnThePanther |
| Pass dates | 11-19-2026, with Z-05 read on 11-23-2026 |

## Fixtures at the start

| Label | Convention | Status | Dates | Time zone |
| --- | --- | --- | --- | --- |
| C1 | QA Con A | Active | 11-01-2026 to 12-31-2026 | America/Los_Angeles |
| C2 | QA Con B | Active | 11-01-2026 to 12-31-2026 | America/Los_Angeles |
| C3 | QA Con C | Active | 11-17-2026 to 12-31-2026 | America/Los_Angeles |

## Blockers

None yet.

## Follow-ups

| Source row | Follow-up | Blocks #513 |
| --- | --- | --- |
| V-01 | "This request changed. This is its current state." stayed on Review catches through pull to refresh and Try again. A successful read clears only the service, eligibility, and access banners (`review_controller.dart:197`, `requests_controller.dart:152`). The same thing happened once on Requests after N-04. | No, by owner decision on 11-19-2026 |
| N-05 | The suit detail screen does not scroll to its error banner. A player who changes the approval switch lower on the screen can miss the banner. | No, by owner decision on 11-19-2026 |

## Validation on the frozen commit

| Command | Host | Result |
| --- | --- | --- |
| `task api-check` | macOS | Passed on 11-19-2026. 3553 backend tests passed, and 18 were skipped. Semgrep, migrations, schema, and gunicorn checks passed. |
| `task mobile-check` | macOS | Passed on 11-19-2026. The API snapshot check passed. `flutter analyze` found no issues, and 679 tests passed. |
| `fvm flutter build apk --profile --dart-define-from-file=config/development.json` | macOS | Passed on 11-19-2026. |
| `fvm flutter build ios --profile --no-codesign --dart-define-from-file=config/development.json` | macOS | Passed on 11-19-2026. A signed build ran in the pass. |
| `git diff --check 8840cdd^ 8840cdd` | macOS | Passed on 11-19-2026. |
| CI on the frozen commit | GitHub Actions | Passed: TailTag API, Windows parity, and Mobile App Build Test |

The focused integration checks are the catch request API and race tests inside `task api-test`, and the gate probe.

## Live results

Each result is Pass, Fail with a defect link, Blocked with a reason, or Not run. N/A means that the row does not run on that platform.

| Row | Android | iOS | Notes |
| --- | --- | --- | --- |
| S-01 | Pass | Pass | The account screen opened on each phone. The Development request log showed no `/api/` request in the 10 minutes after both installs. |
| R-01 | Pass | N/A | The Pixel account. Clerk Development gained one user. The log showed 1 `PUT /api/profile/` 200 and 3 enrollment `POST`s 201. Django admin shows enrollments at C1, C2, and C3, with C3 selected. |
| R-02 | N/A | Pass | The iPhone account. Clerk Development gained one more user, 3 in all with the smoke user. The log showed 1 more `PUT /api/profile/` 200 and 3 more enrollment `POST`s 201. Django admin shows enrollments at C1, C2, and C3, with C3 selected. |
| K-01 | Pass | Pass | |
| J-01 to J-07, journey 1 | J-01 to J-03, J-06, and J-07 Pass | J-04 and J-05 Pass | Owner P on Android, player I on iOS. Suit S-P1. The log showed 1 `POST /api/fursuits/` 201, 1 activation `PUT` 200, 1 catch session `PUT` 200, and 1 tag `GET` 200. Django admin shows one current tag at version 1 and one active session. The J-05 double tap sent 1 `POST /api/catches/requests/` 201, and Django admin shows one pending request at C3, sent at 19:03Z on 11-19-2026. J-07 ended the S-P1 session at 19:28Z with the reason Owner, and the request stayed pending. |
| J-01 to J-07, journey 2 | J-04 Pass | J-01 to J-03, J-06, and J-07 Pass | Owner I on iOS, player P on Android. Suit S-I1, with a HEIC camera photo. The log showed a second suit, activation, catch session, and tag read. Django admin shows a second active session at C3. J-07 ended the S-I1 session at 19:29Z with the reason Owner, and the request stayed pending. |
| N-01 | Pass | N/A | Window N1 |
| N-02 and N-03 | N/A | Pass | Windows N2 and N3. N-03 showed the red no-connection banner, because the read after the failed action also failed offline. The owner accepted this banner as the expected result on 11-19-2026. |
| N-04 | Pass | N/A | Window N4. The red no-connection banner showed, which the owner accepted. |
| N-05 and N-06 | N/A | Pass | Windows N5 and N6. N-05 showed the red no-connection banner. The suit screen did not scroll up to the banner, so a player can miss it. The owner called N-05 a pass and listed the scroll as a follow-up. N-06 showed "We couldn't check your tag." with Try again, then "Tag 1" after the network returned. |
| N-07 | N/A | Pass | Ran inside T-02 with Network Link Conditioner on Very Bad Network. The server created one request. |
| C-00 | Pass | Pass | S-P2 and S-I2. The log showed 2 suits created, 2 activations, 2 catch sessions, and 2 tag reads. Django admin shows 4 active sessions at C3. |
| C-01 | N/A | Pass | I to S-P2 at C3, pending. |
| C-02 | Pass | Pass | P to S-I2 at C3, declined without a block. The log showed 2 previews, 2 requests created, and 1 decline 200 for C-01 and C-02. |
| B-01 | Pass | Pass | On Android, the first restart left the app process running. The tester ended the app again, and the second start passed. |
| E-01 | Pass | Pass | Admin row. At 11:33 on 11-19-2026 Los Angeles time, C3 became Completed with end date 11-18-2026. The start date stayed 11-17-2026. The stored deadline moved to 11-21-2026 08:00Z, and the window stayed Open. |
| E-02 to E-04 | Pass | Pass | E-03: both journey requests are Approved. Django admin shows `caught_at` equal to `requested_at` at the minute it displays: 19:03Z for S-P1 and 19:07Z for S-I1. Both `approved_at` values are 19:34Z, 31 and 27 minutes later. The C-01 request stayed pending, and C-02 stayed declined. E-04: each phone's Catches showed the other phone's first suit at the request time, 11:03 and 11:07 Los Angeles time, not the approval time. |
| T-01 and T-03 | Pass | N/A | T-01: S-P1 activation and session at C2 with the same tag, version 1. T-03: 1 `POST fursuits/{id}/tag/replace/` 200. Django admin shows tag version 1 revoked at 19:38Z with the reason Owner replacement, and version 2 current. The session kept running. |
| T-02, T-04, and T-05 | N/A | Pass | T-02: 1 preview and 1 `POST catches/requests/` 201. Django admin shows one pending request for S-P1 at C2. T-04 is Pass by owner override on 11-19-2026. It did not run on a device, because the old print was lost. Django admin shows the old tag revoked. T-05: the new tag previewed S-P1, and the send returned 200 with the existing request, so no duplicate exists. |
| T-06 | Pass | Pass | Each phone still showed the earlier C3 catch and requests, and the C2 request. |
| V-01 | Pass | Pass | Withdraw won: 1 `POST catches/requests/{id}/withdraw/` 200 and 1 `POST catches/incoming-requests/{id}/approve/` 409. Django admin shows the C2 request Withdrawn and no catch. |
| O-01 to O-06, Q-01 | Pass | Pass | Owner P on Android, S-P2 at C1. O-01: 1 request 201, 1 decline 200, 1 undo 200. Django admin shows the request pending. O-02: 1 decline 200 and 1 restore 200. Django admin shows the request pending with no counted decline. O-03: 1 `PATCH fursuits/{id}/` 200 at 19:50:46Z, and the request stayed pending. O-04: the send at 19:51:14Z returned 200 with the existing request, so no new request exists. O-05: 1 withdraw 200 at 19:52:26Z. Q-01: the laptop screenshot of the S-P2 tag led to 1 `POST catches/requests/` 201 at 19:53:05Z. Django admin shows that request Approved, with `requested_at` and `approved_at` both 19:53Z. The server accepted a copied code, because V0 does not prove physical proximity. O-06: the next send returned 200 with the existing result, so no duplicate exists. |
| O-07 to O-13 | Pass | Pass | Owner I on iOS, S-I2 at C1. O-07: 1 request 201 at 20:52:59Z, 1 decline 200, and 1 undo 200. Django admin shows the request pending. O-08: decline 200 at 20:54:52Z, then the send 2 seconds later returned 429 and the Pixel showed the countdown. O-09: request 201 at 20:56:04Z, decline with block 200, then the scan preview returned 404 and the Pixel showed "This TailTag can't be caught right now." O-10: block removal 204 at 20:56:35Z, then the send returned 429 with a wait of about 10 minutes. Django admin shows no catch block left. O-11: S-I1 activation and session at C1, then 1 request 201 at 20:58:16Z, pending. O-12: the operator invalidated that request in Django admin at 21:06Z. Both phones showed "No longer available". O-13: S-I1 back at C1 with a session, automatic approval on with 1 `PATCH` 200, then 1 request 201 at 21:08:14Z. Django admin shows one new catch for S-I1 at C1 at 21:08Z. |
| F-01 and F-02 | Pass | Pass | F-01: the operator set C1 to Paused, and Django admin shows all C1 sessions ended with the reason Eligibility lost. The iPhone showed "You can't approve this right now." at once. The Pixel showed the closed-catching text after a refresh. The operator set C1 back to Active. F-02: the operator disabled the P profile. The iPhone showed "You can't approve this right now." on the request from P, and the Pixel showed the account-unavailable screen. After the operator enabled the profile, Refresh returned the Pixel to the C1 home. |
| F-03 and F-04 | N/A | Pass | F-03: the operator turned off `is_enabled` on S-I1. The iPhone showed "You can't approve this right now." on the O-11 request and "TailTag staff disabled this suit." on the suit. The operator turned it back on. F-04: I turned off participation at C1 for S-I1, with 1 activation `PUT` 200 at 21:06:23Z. Review catches still offered Approve with no paused text, and Django admin shows the O-11 request pending. |
| Z-01 to Z-03 | Pass | Pass | Z-01: the operator moved the C3 end date from 11-18 to 11-19-2026 while the window was open. The stored deadline moved to 11-22-2026 08:00Z, and both phones showed the last review day as Sat, Nov 21. Before Z-02, the tester restored the C-02 request by mistake at 21:10:21Z and declined it again at 21:11Z. Z-02: at 21:12Z the operator set the C3 start and end date to 11-16-2026. The stored deadline became 11-19-2026 08:00Z, and Django admin showed the window as Closed. The Pixel showed no C3 group in Requests after a refresh. Z-03: the stale Restore on the iPhone returned 409 at 21:12:46Z. The app showed "This request is no longer available." and removed the C3 group. After Z-03, a restore and a decline on a C1 request also ran, at 21:12:52Z and 21:13:04Z. They left that request declined. |
| Z-04 and Z-05 | Pass | Pass | Admin rows. Z-04: the operator set the closed C3 end date to 12-31-2026. Django admin saved the date, but the stored deadline stayed 11-19-2026 08:00Z, and the window stayed Closed. Z-05: the `tailtag-cleanup-dev` run at 10:01Z on 11-20-2026 logged "Deleted 4 catch requests and 0 blocks." The outcome events counted 2 approved, 1 expired, and 1 declined, which matches C3. On 11-23-2026 a read-only query showed 0 requests and 0 blocks for C3. The 2 C3 catches stay in the collections, as the contract requires. The runs on 11-21 and 11-22-2026 deleted nothing. |
| I-01 and I-02 | Pass | Pass | Android: after sign-out, Back kept the account screen. I signed in on the Pixel at 21:17:17Z, and Catches, Requests, Suits, and Review catches loaded for I with no P content. A first attempt opened only Suits, so the tester repeated it. P signed back in at 21:17:55Z. iOS: P signed in on the iPhone at 21:18:49Z, and Catches, Requests, Suits, and Review catches loaded for P with no I content. I signed back in at 21:19:24Z. |
| X-01 and X-03 | N/A | Pass | Review catches, the decline sheet, and the undo snackbar passed with VoiceOver and at AX3 after O-11. The decline and undo from these rows left the O-11 request pending with no counted decline. The other screens passed with VoiceOver and at AX3 on 11-19-2026. |
| X-02 and X-04 | Pass | N/A | Review catches, the decline sheet, and the undo snackbar passed with TalkBack and at 200% after O-02. The 2 declines and 2 undos from these rows left the request pending with no counted decline. The other screens passed with TalkBack and at 200% on 11-19-2026. The scanner check sent 1 preview and no catch request. |
| D-01 | Pass | Pass | Admin row, before Z-02. Django admin holds 11 requests across 8 trios and 4 catches. Each trio has at most one pending request and at most one approved request. Each catch belongs to a different trio. |

## Log windows

| Window | Row | UTC on 11-19-2026 | Writes | Control reads |
| --- | --- | --- | --- | --- |
| N1 | N-01 | 19:05:59Z to 19:07:44Z | 1 `POST catches/requests/` 201, from "Check again". The airplane-mode send did not reach the server. Django admin shows one pending request for S-I1. | 2 reads, both 200 |
| N2 | N-02 | 19:08:06Z to 19:10:26Z | None. The decline did not reach the server. | 19 reads, all 200 |
| N3 | N-03 | 19:10:43Z to 19:12:01Z | None. The approve did not reach the server. Django admin shows the request still pending and no catch. | 3 reads, all 200 |
| N4 | N-04 | 19:15:22Z to 19:16:46Z | None. The withdrawal did not reach the server. | 5 reads, all 200 |
| N5 | N-05 | 19:17:02Z to 19:18:55Z | None. No suit change reached the server. | 14 reads, all 200 |
| N6 | N-06 | 19:19:21Z to 19:22:02Z | None. No replacement reached the server. Django admin shows one tag for S-I1, version 1, not revoked. | 7 reads, all 200 |

## Reused and automated evidence

| Row | Source | Commit and path diff |
| --- | --- | --- |
| U-01 | `services/api/tests/test_catch_request_concurrency.py`, including `test_two_submissions_for_one_trio_give_one_result`, `test_approve_and_withdraw_give_one_result`, `test_two_approvals_create_one_catch`, and `test_operator_invalidation_and_approval_give_one_result` | Passed inside `task api-check` on `8840cdd`, the frozen commit. No path diff. |
| U-02 | `services/api/tests/test_catch_request_api.py` (`test_a_retry_after_a_target_change_returns_the_unchanged_result`), `services/api/tests/test_catch_request_review_api.py` (`test_a_retry_returns_the_existing_request_despite_a_block`), and the widget tests `scan_flow_test.dart:542`, `tag_flow_test.dart:435`, `review_flow_test.dart:233`, and `requests_flow_test.dart:136` under `apps/mobile/test/features/` | Passed inside `task api-check` and `task mobile-check` on `8840cdd`. No path diff. A lost response after the server commits is not proven on a device. |
| U-03 | `apps/mobile/test/features/reviews/review_flow_test.dart:322`, "a 403 reads the home state again" | Passed inside `task mobile-check` on `8840cdd`. No path diff. |

## Map to #513 acceptance criteria

| #513 | Rows | State |
| --- | --- | --- |
| AC1 | R-01, R-02, J-01 to J-06 | Live passed |
| AC2 | J-07, E-01 to E-04 | Live passed |
| AC3 | T-01 to T-06 | Passed. T-04 is Pass by owner override and did not run on a device. |
| AC4 | O-01 to O-13, Q-01 | Live passed |
| AC5 | Z-01 to Z-05, F-01 to F-04, V-01, D-01, N-01 to N-06, U-01 to U-03 | Live passed |
| AC6 | K-01, J-04, B-01, I-01, I-02, X-01 to X-04, N-01 to N-07 | Live passed |
| AC7 | Q-01 | Live passed. The record does not claim proof of physical proximity. |
| AC8 | Pass details, the scan before commit | Passed. The scripted scan found no match on 11-19-2026. |
| AC9 | Validation on the frozen commit | Passed |

#501 AC11 maps to this whole record.

## End state

On 11-23-2026, a read-only query on Render Development showed this state:

- QA Con A and QA Con B are Active. QA Con C is Completed, and its review window is closed for good.
- Both player profiles and all 4 suits are enabled.
- No catch block exists.

The pass created only the Pixel account and the iPhone account. Both accounts stay. No task-started process remains.
