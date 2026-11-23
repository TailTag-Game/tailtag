# Mobile catch journey checklist

Use this checklist to prove the reusable TailTag and catch review journey on physical Android and iOS devices against Render Development. Issue [#513](https://github.com/TailTag-Game/tailtag/issues/513) owns this checklist. Its spec is the [refinement comment](https://github.com/TailTag-Game/tailtag/issues/513#issuecomment-6967708958). Each pass writes its results in a dated evidence file beside this one.

The first record is [catch-journey-evidence-2026-11.md](catch-journey-evidence-2026-11.md). The account-to-convention journey has its own [checklist](mobile-journey-checklist.md).

## Terms

- A pass is one full run of this checklist on one frozen commit.
- The frozen commit is the `main` commit that every live row in a pass uses.
- A row is one checklist item with steps, an expected result, and an evidence type.
- A journey is one owner and one player who run the full flow together on two phones.
- A trio is one player, one suit, and one convention. A trio has at most one pending request and one catch.
- A log window is a recorded UTC start and end time around one or more rows.
- A path diff is `git diff` between two commits, limited to the code that a row exercises.
- An unknown outcome is a write that ended in a connectivity failure, a timeout, or a 5xx error.
- The operator is the Development operator in Django admin. The owner does every operator step.

Proof accounts, suits, and conventions are synthetic. The evidence names them only by these labels:

| Label | Meaning |
| --- | --- |
| P | The Pixel account. It owns S-P1 and S-P2 and catches the iPhone account's suits. |
| I | The iPhone account. It owns S-I1 and S-I2 and catches the Pixel account's suits. |
| S-P1, S-P2 | The first and second suits of P |
| S-I1, S-I2 | The first and second suits of I |
| C1 | QA Con A. Outcome and disabled-state rows run here. |
| C2 | QA Con B. Tag reuse and replacement rows run here. |
| C3 | QA Con C. The journeys, the after-convention review, and closure run here. C3 is disposable. |

Never write an address, a handle, a code, a token, a QR payload, a request ID, a Clerk identifier, or the Frontend API host in the evidence. A photo must never show a readable QR code.

The fixed test code and the `+clerk_test` rule are in [Debug proof route and test user](mobile.md#debug-proof-route-and-test-user).

## Prepare the pass

1. The owner posts a readiness note on the issue. It confirms the phones and OS versions, the Development gate, the Development API commit, operator access, a printer, and the fixtures.
2. In Django admin, make sure that C1, C2, and C3 are Active and have a time zone. C3 must have an end date in the future.
3. Choose the frozen commit on `main` and record its full hash.
4. Read the Development API commit from `https://tailtag-api-development.onrender.com/health/identity`. Run `git diff --stat <API commit> <frozen commit> -- services/api`. If the diff is not empty, the owner deploys the frozen commit to Development before the pass.
5. Make sure that the gate is on. An unauthenticated `POST /api/catches/preview/` must return 401. A 404 means that the gate is off, and the pass is blocked.
6. On the build host, check out the frozen commit with no local application changes. Do not add a temporary patch. A patched build is a different commit.
7. Uninstall TailTag from both phones, so that K-01 starts from a fresh install.

## Build the app

Run this command from `apps/mobile/` on the Mac, once for each phone. Get `<device id>` from `fvm flutter devices`.

```bash
fvm flutter run --profile --no-resident -d <device id> --dart-define-from-file=config/development.json
```

A profile build starts from the Home Screen with no host attached. The `--no-resident` flag ends the command after the app opens. An iPhone build needs `ios/Flutter/Signing.local.xcconfig`, as [Signing for Apple](mobile.md#signing-for-apple) describes. On the Pixel, the app runs as Android user 10. Use `--user 10` with `adb shell run-as` if you need to inspect app files.

## Count requests

Only the N rows use log windows. A log window shows whether a failed write reached the server. Duplicate checks use Django admin row counts instead (D-01).

Use the request-count command in the [account journey checklist](mobile-journey-checklist.md#count-requests). It prints counts by method, path, and status. Paths that hold a request ID or a suit ID are private. Record them only as route templates, such as `POST catches/incoming-requests/{id}/approve/`.

Each window needs a positive control. The control is a read that the same steps must send, such as `GET /api/catches/requests/`. One tester must use Development during a window.

## Run order

The two phones work together. The Pixel uses only P, and the iPhone uses only I. Each account is an owner and a player. Neither phone changes accounts until the [session isolation](#session-isolation) rows.

| Step | Section |
| --- | --- |
| 1 | [Start](#start) and [registration](#registration) |
| 2 | [Journeys](#journeys), journey 1 |
| 3 | Journey 2 with the [network rows](#network-loss) |
| 4 | [More requests at C3](#more-requests-at-c3), then J-07 for each journey |
| 5 | [Restart](#restart) and [after-convention review](#after-convention-review) |
| 6 | [Tag reuse and replacement](#tag-reuse-and-replacement) |
| 7 | [Outcomes, pair 1](#outcomes-pair-1) |
| 8 | [Outcomes, pair 2](#outcomes-pair-2) and [disabled states](#disabled-states) |
| 9 | [Django admin checks](#django-admin-checks), then [closure and deletion](#closure-and-deletion) |
| 10 | [Session isolation](#session-isolation) and [accessibility](#accessibility) |

Run steps 5 to 9 on the same day. The C3 window closes by itself two days after E-01.

Every date that the operator types is a date in America/Los_Angeles. The "Today" link in Django admin uses UTC, which is up to 8 hours ahead. Type each date by hand. A wrong date in E-01 can close C3 for good.

A catch session lasts 12 hours. If a suit session timed out before a row needs it, turn on "Out for catching" again.

Each account sees its own suits in Review catches and its own catches in Requests and Catches. When a row names a request, act only on that request.

## Rows

The Issue column names the acceptance criterion in the refinement comment. Every row in this section is live evidence. [Reused and automated evidence](#reused-and-automated-evidence) lists the other types.

### Start

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| S-01 | Both | Force-stop the app. Disconnect the host. Open the app from the Home Screen or the launcher. | The account screen opens. | AC3 |

### Registration

Each account uses a new `+clerk_test` address and a new handle.

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| R-01 | Android | P | Create the account with the email code. Complete onboarding. Tap "Join and enter" on C1. Change convention and "Join and enter" C2. Change convention and "Join and enter" C3. | The C3 home opens with the bar: Home, Catches, Requests, and Suits. | AC9 |
| R-02 | iOS | I | Same steps as R-01. | Same result as R-01. | AC9 |

### Camera permission

Run K-01 on each phone right before its first scan. The iPhone runs it before J-04 of journey 1. The Pixel runs it before J-04 of journey 2.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| K-01 | Both | Tap "Scan a TailTag". Tap "Turn on camera". Refuse in the system prompt. Tap "Open settings", allow the camera, and return to TailTag. | Before the system prompt, the intro text and "Turn on camera" show. After the refusal, "TailTag needs camera access to scan tags. Turn it on in Settings." and "Open settings" stay. After the return, "Point your camera at a TailTag." shows and the camera runs. | AC46 |

### Journeys

Journey 1 uses P as the owner on the Pixel and I as the player on the iPhone. Its suit is S-P1. Journey 2 uses I as the owner on the iPhone and P as the player on the Pixel. Its suit is S-I1. Run J-01 to J-06 for each journey. Run J-07 in step 4.

| Row | Role | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| J-01 | Owner | Open Suits. Tap "Register suit". Enter a synthetic name. In journey 1, tap "Choose photo" and pick a synthetic image, so that K-01 still starts with no camera permission on the Pixel. In journey 2, tap "Take photo". Save. | The suit shows in My suits with its photo. On the iPhone, the photo is a HEIC camera photo. | AC11 |
| J-02 | Owner | Open the suit. Turn on "Participating at C3". Turn on "Out for catching". | The row says "Out until" a time. The suit shows as catchable. | AC11 |
| J-03 | Owner | Tap "Show tag". Tap "Share tag image". Print it at actual size. | The share sheet opens. The printer prints the badge. | AC12 |
| J-04 | Player | Tap "Scan a TailTag". Point the camera at the print from arm's length, in normal indoor light. | A haptic tap. The preview shows the suit photo, the suit name, and C3. | AC13 |
| J-05 | Player | In journey 1, double-tap "Catch {name}". In journey 2, run N-01 instead. Tap "See my requests". | "Catch sent. {name}'s owner will review it by the end of {date}." Requests shows one row, "Waiting for review", under C3 with "Owners can review until the end of {date}". | AC13, AC38 |
| J-06 | Owner | Return to the home. Tap the review row. | The home row shows the pending count. Review catches shows the request as "Waiting for review" with the player name and handle. | AC13 |
| J-07 | Owner | Open the suit. Turn off "Out for catching". | The snackbar says "Catch session ended. Requests already sent stay for you to review." The request stays pending. | AC14 |

### Network loss

Run these rows in journey 2. I is the owner on the iPhone, and P is the player on the Pixel. Open one log window before N-01 and close it after N-06. Each row must leave the journey 2 request pending. While the phone is offline, the app reads the list again after the failed action. That read fails too, so the red no-connection banner can replace the unknown-outcome text. The server log is the proof that no write arrived.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| N-01 | Android | With the preview open, turn on airplane mode. Tap "Catch {name}". Turn off airplane mode. Tap "Check again". | First "We couldn't confirm your catch. Check your connection, then check again." Then "Catch sent." Requests shows one pending row for S-I1. The window shows the failed send did not reach the server. | AC42, AC43 |
| N-02 | iOS | Turn on airplane mode. In Review catches, tap Decline, then choose Decline. Turn off airplane mode. Pull to refresh. | A connection banner shows. The red "No internet connection. Check your connection, then try again." banner replaces the unknown-outcome text while the phone is offline. After the refresh, the row stays "Waiting for review". | AC42, AC43 |
| N-03 | iOS | Turn on airplane mode. Tap Approve. Turn off airplane mode. Pull to refresh. | The same connection banner. After the refresh, the row stays "Waiting for review". No catch exists. | AC42, AC43 |
| N-04 | Android | Turn on airplane mode. In Requests, tap Withdraw and confirm. Turn off airplane mode. Pull to refresh. | A connection banner shows, such as "We couldn't confirm the withdrawal. This is the current state." or the red no-connection banner. After the refresh, the row stays "Waiting for review". | AC42, AC43 |
| N-05 | iOS | Turn on airplane mode. On S-I1, turn on "Approve catches automatically". Turn off airplane mode. | A connection banner shows, such as "We could not confirm the change. Check the current state before you try again." or the red no-connection banner. After the network returns and the screen reads again, the switch is off. | AC42, AC43 |
| N-06 | iOS | Turn on airplane mode. On the S-I1 tag screen, tap "Replace tag" and confirm. Turn off airplane mode. | A connection banner shows, such as "We couldn't check your tag." The app does not send the replacement again. After the network returns and the tag reads again, the tag version is the same. | AC42, AC43 |

N-07 runs inside T-02.

### More requests at C3

These rows leave one pending request and one declined request at C3 for the closure rows. They use second suits, so the journey requests stay separate.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| C-00 | Both | P registers S-P2 on the Pixel, and I registers S-I2 on the iPhone. Each owner turns on "Participating at C3" and "Out for catching" for the new suit and opens its tag. | Each new suit says "Out until" a time. | AC28 |
| C-01 | iOS | I scans the S-P2 tag screen on the Pixel and taps "Catch {name}". | "Catch sent." I has a pending request for S-P2 at C3. P leaves it pending. | AC28 |
| C-02 | Both | P scans the S-I2 tag screen on the iPhone and sends the catch. I declines that request in Review catches and waits 15 seconds. | The row says "Declined" and offers Restore. | AC28 |

Then run J-07 for S-P1 on the Pixel and for S-I1 on the iPhone.

### Restart

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| B-01 | Both | Force-stop the app. Open it from the Home Screen or the launcher. Open Review catches, Requests, and Catches. | The C3 home opens with no sign-in. Each screen shows the same rows as before. | AC47 |

### After-convention review

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| E-01 | Admin | The operator sets the C3 end date to yesterday in America/Los_Angeles time and the status to Completed. If the start date is after the new end date, set it to the same day. | Django admin shows the review window as Open, with a new deadline. | AC14 |
| E-02 | Both | Pull to refresh on the home and on Review catches. | The home stays, with the inactive banner. The header says "You can review until the end of {date}", and the date is tomorrow. | AC15 |
| E-03 | Both | Wait until 5 minutes have passed since the journey request. P approves the journey 1 request for S-P1, not the C-01 request for S-P2. I approves the journey 2 request for S-I1. | "Catch approved." The row says "Approved". The C-01 request stays pending. | AC16 |
| E-04 | Both | Open Catches. The operator opens each journey request in Django admin. | P sees S-I1, and I sees S-P1, each at C3 with the request time. Django admin shows `caught_at` equal to `requested_at` and a later `approved_at`. Record "match" and the gap in minutes. | AC17 |

### Tag reuse and replacement

P is the owner on the Pixel, and I is the player on the iPhone. These rows use S-P1 and the journey 1 print.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| T-01 | Android | Change convention and enter C2. Open S-P1. Turn on "Participating at C2" and "Out for catching". Open the tag. | The session runs at C2. The tag version is the same as in J-03. | AC18 |
| T-02 | iOS | Change convention and enter C2. Run N-07: turn on Network Link Conditioner with the "Very Bad Network" profile. Scan the S-P1 print and tap "Catch {name}". If the result is the unknown outcome, tap "Check again" until a result shows. Turn off Network Link Conditioner. | "Catch sent." or an unknown outcome and then "Catch sent." Requests shows one pending row for S-P1 at C2. | AC18, AC44 |
| T-03 | Android | On the tag screen, tap "Replace tag" and confirm. | "Tag replaced. Print the new one." The tag version goes up by 1. The suit still says "Out until" a time. | AC19, AC20 |
| T-04 | iOS | Scan the old print. | "This TailTag can't be caught right now." | AC19 |
| T-05 | iOS | Scan the new tag on the Pixel screen. Tap "Catch {name}". | The preview shows S-P1 at C2. Then "You already sent a catch for {name}. It's waiting for review." | AC19, AC38 |
| T-06 | Both | Open Catches and Requests on the iPhone. Open Review catches on the Pixel. | I still has the S-P1 catch at C3 and the pending request at C2. P still sees its C3 and C2 requests. | AC20 |
| V-01 | Both | Count down out loud from 3. On 0, P taps Approve on the C2 request while I taps Withdraw and confirms. Pull to refresh on both phones. | Both phones show the same single state. Record which action won. One phone can show "This request changed. This is its current state." | AC39 |

### Outcomes, pair 1

P is the owner on the Pixel, and I is the player on the iPhone. Both select C1. P turns on "Participating at C1" and "Out for catching" for S-P2 and opens its tag. I scans that tag screen.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| O-01 | Both | I sends a catch for S-P2. P taps Decline, chooses Decline, and taps Undo within 10 seconds. | "Catch declined." with Undo, then the row says "Waiting for review" again. I sees "Waiting for review" after a refresh. | AC22 |
| O-02 | Both | P declines again and waits 15 seconds. P taps Restore. | The snackbar closes and no Undo shows. The row offered Restore. Then "Request restored." and "Waiting for review". | AC23 |
| O-03 | Android | P opens S-P2 and turns on "Approve catches automatically". | The switch stays on. The pending request stays "Waiting for review" on both phones. | AC21 |
| O-04 | iOS | I scans S-P2 and taps "Catch {name}". | "You already sent a catch for {name}. It's waiting for review." | AC38 |
| O-05 | Both | I withdraws the request in Requests and confirms. P pulls to refresh. | "Catch withdrawn." P sees "Withdrawn". | AC24 |
| Q-01 | Both | Take a screenshot of the S-P2 tag screen. Show it on a laptop screen. After 10 seconds, I scans the laptop and taps "Catch {name}". | "You caught {name}! It's in your collection." Catches shows S-P2 at once. The server accepts a copied code, because V0 does not prove physical proximity. | AC21, AC53 |
| O-06 | iOS | I scans S-P2 again and taps "Catch {name}". | "You already caught {name} at this convention." | AC38 |

Delete the screenshot from the phone and the laptop after Q-01.

### Outcomes, pair 2

I is the owner on the iPhone, and P is the player on the Pixel. Both select C1. I turns on "Participating at C1" and "Out for catching" for S-I2 and opens its tag. P scans that tag screen.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| O-07 | Both | P sends a catch for S-I2. I declines and taps Undo within 10 seconds. | The row says "Waiting for review" again. | AC22 |
| O-08 | Both | P scans the S-I2 tag screen and keeps the preview open. I opens Review catches and declines. Within 10 seconds, P taps "Catch {name}". | "You can try again in 0:0x." with a countdown. | AC25 |
| O-09 | Both | After the countdown, P sends the catch again. I taps Decline and chooses "Decline and block". P scans S-I2. | "Player blocked." The row says "Blocked". P sees "This TailTag can't be caught right now." | AC26 |
| O-10 | Both | I taps "Remove block". P scans S-I2 and taps "Catch {name}". | "Block removed." P sees a wait of about 10 minutes, such as "You can try again in 9:52." The pass does not wait it out. | AC25, AC26 |
| O-11 | Both | I opens S-I1 and turns on "Participating at C1" and "Out for catching". P scans the S-I1 tag screen and sends the catch. | "Catch sent." The request for S-I1 is pending. | AC33 |

### Disabled states

These rows use the O-11 request for S-I1. The operator restores each change in the same row.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| F-01 | Both | The operator sets C1 to Paused. Both phones pull to refresh. The operator sets C1 to Active. | P sees "Catching isn't open at QA Con A right now." I sees "You can't approve this right now." on the request. The pause ends the S-I1 session. | AC33 |
| F-02 | Both | The operator disables the P profile. Both phones pull to refresh. The operator enables it, and P taps Refresh. | I sees "You can't approve this right now." The Pixel shows the account-unavailable screen, then returns to the C1 home. | AC34 |
| F-03 | iOS | The operator turns off `is_enabled` on S-I1. I pulls to refresh. The operator turns it on. | I sees "You can't approve this right now." on the request. The suit says "TailTag staff disabled this suit." | AC35 |
| F-04 | iOS | I opens S-I1 and turns off "Participating at C1". I confirms Stop. I opens Review catches. | "Stop participating?" with the end-session reason. The request still offers Approve with no paused text. | AC36 |
| O-12 | Both | The operator opens the O-11 request in Catch requests, checks "Invalidate this pending or declined request", and saves. Both phones pull to refresh. | P and I see "No longer available". | AC27 |
| O-13 | Both | I turns on "Participating at C1", "Out for catching", and "Approve catches automatically" for S-I1. After 10 seconds, P scans S-I1 and sends the catch. | "You caught {name}! It's in your collection." | AC21 |

### Closure and deletion

These rows use C3. The C-01 request is pending, and the C-02 request is declined.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| Z-01 | Both | The operator moves the C3 end date one day later. Both phones pull to refresh on Requests and Review catches. | The C3 last review day moves one day later in both apps. | AC28 |
| Z-02 | Both | On the iPhone, open Review catches, so the C3 declined row shows. Do not refresh it. The operator sets the C3 end date 3 days before today, and the start date to the same day. On the Pixel, P pulls to refresh on Requests. | Django admin shows the review window as Closed. P sees no C3 group in Requests. | AC29 |
| Z-03 | iOS | Open Review catches from the screen in Z-02, and tap Restore on the C3 row without a refresh. | "This request is no longer available." The C3 group goes away. | AC30 |
| Z-04 | Admin | The operator moves the C3 end date again and saves. | The stored deadline does not change. The window stays Closed. | AC31 |
| Z-05 | Admin | After the next 10:00 UTC run of `tailtag-cleanup-dev`, read its log in the Render dashboard. The operator filters Catch requests by C3. | The log shows deleted counts by state. Catch requests and Catch blocks show no rows for C3. Record counts only. | AC32 |

### Session isolation

Each phone signs in the other phone's account once, then signs back in. No row creates another account.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| I-01 | Both | Sign out. Use the system Back action. On iOS, swipe in from the left edge. | The account screen stays. No content of the account that signed out shows. | AC48 |
| I-02 | Both | Sign in with the other phone's account and the email code. Open Suits, Review catches, Requests, and Catches. Sign out, and sign back in with this phone's account. | Only the content of the account that signed in shows. No suit, tag, review row, request, or catch of the other account shows. | AC48 |

### Accessibility

Run these rows on each of these screens: home, suits list, suit form, suit detail, tag, scanner, preview and result, Requests, Catches, and Review catches with its decline sheet and the undo snackbar.

The owner screens need a pending request. Run the rows for Review catches, the decline sheet, and the undo snackbar on Android after O-02, and on iOS after O-11. Decline, then tap Undo. If the snackbar closes first, tap Restore. Run the other screens in step 10.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| X-01 | iOS | Turn on VoiceOver. Move through each control. Activate the main action. | Every control is reached and announces its label. The main action works. | AC50 |
| X-02 | Android | Turn on TalkBack. Move through each control. Activate the main action. | Every control is reached and announces its label. The main action works. | AC50 |
| X-03 | iOS | Set Larger Text to the size AX3. Open each screen. | No text clips. The main action stays reachable. | AC51 |
| X-04 | Android | Set Font size to 200%. Open each screen. | No text clips. The main action stays reachable. | AC51 |

The pass runs no hardware keyboard rows. #472 and #473 own the focus rules.

### Django admin checks

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| D-01 | Admin | Before Z-02, the operator filters Catch requests by each of C1, C2, and C3, and lists catches for the pass suits. | Each trio has at most one pending request and at most one catch. Record counts only. | AC41 |

## Reused and automated evidence

These rows do not run on the physical build. The evidence file names the source test or run, its commit, and the path diff to the frozen commit. Test paths are under `apps/mobile/test/` or `services/api/`.

| Row | Evidence | Why it is not a physical row | Issue |
| --- | --- | --- | --- |
| U-01 | The #505 and #506 race tests in `services/api` | A person cannot interleave two transactions on purpose. | AC40 |
| U-02 | The #505 and #506 API tests for repeated submits and actions, and the #510 AC19, #511 AC18, and #512 AC25 widget tests | A lost response after the server commits needs a proxy patch, so it cannot run on the frozen build. | AC45 |
| U-03 | The #512 widget test for a 403 on review | A disabled owner sees the account-unavailable screen and cannot reach Review catches. | AC37 |

## After a fix

If a pass finds a defect, open a new Bug issue under #501 that names the owning child issue. Move #513 to Blocked in the TailTag Rebuild Project.

After the fix merges, choose a new frozen commit and rebuild both apps. Repeat each row whose path diff changed. Then repeat one full smoke journey in each direction: J-01 to J-06 with E-03.

## After the pass

1. C3 stays Completed and closed. C1 and C2 stay Active.
2. Make sure that the P profile and S-I1 are enabled.
3. Delete any tag screenshot and any photo of a tag.
4. Stop only the processes that this pass started.
5. Keep the proof accounts.

## Scan the evidence before commit

Run this search from the repository root before you commit either file. A clean file prints nothing from the last command. The `printf` line is the positive control, so it must print one line.

```bash
PATTERN='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|eyJ[A-Za-z0-9_-]{10,}|[ps]k_(test|live)_[A-Za-z0-9]+|(user|sess|sia|sua|idn|eac|client)_[A-Za-z0-9]{20,}|[a-z0-9-]+\.clerk\.accounts\.dev|tailtag\.app/t#'
printf 'tailtag.app/t%sZZZZ\n' '#' | grep -E "$PATTERN"
grep -nE "$PATTERN" docs/development/catch-journey-checklist.md docs/development/catch-journey-evidence-*.md
```

The search cannot find a handle, a request ID, or a QR payload without its prefix. Read the evidence file once for those values.
