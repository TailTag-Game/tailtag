# Mobile account-to-convention journey checklist

Use this checklist to prove the player journey on physical Android and iOS devices against Render Development. Issue [#483](https://github.com/TailTag-Game/tailtag/issues/483) owns this checklist. Each pass writes its results in a dated evidence file beside this one.

The first record is [mobile-journey-evidence-2026-11.md](mobile-journey-evidence-2026-11.md).

## Terms

- A pass is one full run of this checklist on one frozen commit.
- The frozen commit is the application commit that every live row in a pass uses.
- A row is one checklist item with steps, an expected result, and an evidence type.
- A marker is the selected convention that identifies one proof account.
- A write is `PUT /api/profile/`, `POST /api/conventions/enrollments/`, or `PUT /api/conventions/active/`.
- A log window is a recorded UTC start and end time around one or more rows.
- A path diff is `git diff` between two commits, limited to the code that a row exercises.
- A readiness note is an owner comment on the issue that confirms the live prerequisites.

Proof accounts are synthetic. The evidence names them only by these labels:

| Label | Account | Marker |
| --- | --- | --- |
| E1 | Email account for the new-player journey. Each platform uses its own address. | C1 |
| E2 | Second email account for isolation runs. Each platform uses its own address. | C2 |
| G | Google account with no added email method | C2 |
| A | Apple account with Hide My Email, iOS only | C3 |
| D | Email account for the disabled-profile run, with a completed profile | None |

C1, C2, and C3 are active synthetic conventions on Render Development. E2 and G share C2, because no row compares them.

Never write an address, a handle, a code, a token, a credential ID, a Clerk identifier, or the Frontend API host in the evidence.

## Prepare the pass

The owner does steps 1 to 4.

1. Post a readiness note on the issue. Confirm that each of these items is ready:
   - One physical Android phone on API 28 or later, and one physical iPhone on iOS 17 or later.
   - The proof accounts in the [Terms](#terms) table.
   - The Clerk Development settings for email codes, Google, Apple, and passkeys.
   - The items in [Live Apple proof](mobile.md#live-apple-proof) and [Live passkey proof](mobile.md#live-passkey-proof).
   - Django admin access for the [Development operator](backend-delivery-operations.md#django-admin-and-development-operator).
   - A Bluetooth or USB keyboard for each phone.
2. In Django admin, make sure that C1, C2, and C3 exist and have the status Active. Create a missing convention with a synthetic name.
3. Choose the frozen commit. It must be a commit on `main`. Record its full hash.
4. On the build host, check out the frozen commit with no local application changes.

Do not add a temporary patch to the frozen commit. A patched build is a different commit.

## Build the app

A profile build starts from the Home Screen with no host attached. A debug build on an iPhone cannot do this. A profile build has no `/debug/auth` route, so this checklist does not use that route.

Run this command from `apps/mobile/` on the Mac, once for each phone. Get `<device id>` from `fvm flutter devices`.

```bash
fvm flutter run --profile --no-resident -d <device id> --dart-define-from-file=config/development.json
```

The `--no-resident` flag ends the command after the app opens. An iPhone build needs `ios/Flutter/Signing.local.xcconfig`, as [Signing for Apple](mobile.md#signing-for-apple) and [Signing for passkeys](mobile.md#signing-for-passkeys) describe. An Android profile build uses the debug key, so the registered fingerprint still applies.

## Count requests

Render Development logs show each HTTP request but no user. One tester must use Development during a log window, or the counts mean nothing.

Before the first step of a row that names a window, record the UTC time. After the last step, wait 10 seconds and record the UTC time again. Request logs became readable about 3 seconds after each request in the 2026-11-09 test. Then run this command on the Mac. Get `$SERVICE_ID` from the `srv-` part of the `tailtag-api-dev` dashboard URL.

```bash
render logs -r "$SERVICE_ID" --start "$START" --end "$END" --type request --limit 1000 -o json | python3 -c '
import collections, json, sys
raw = sys.stdin.read().strip()
decoder, index, rows = json.JSONDecoder(), 0, []
while index < len(raw):
    item, index = decoder.raw_decode(raw, index)
    rows.extend(item if isinstance(item, list) else [item])
    while index < len(raw) and raw[index].isspace():
        index += 1
counts = collections.Counter()
for row in rows:
    labels = {label["name"]: label["value"] for label in row["labels"]}
    if labels["path"].startswith("/api/"):
        counts[labels["method"], labels["path"], labels["statusCode"]] += 1
print("rows", len(rows))
for key, count in sorted(counts.items()):
    print(count, *key)
'
```

Each window needs a positive control. The control is a read that the same steps must send, such as `GET /api/profile/`. A window with no control line proves nothing. If `rows` equals 1000, split the window and run the command again.

Record only the counts by route. The raw log lines hold client IP addresses, so do not save them.

## Run order

Run every row on Android first, then run every row on iOS. Google needs this order, because the owner deletes the Google user between platforms. Within a platform, run the tables from top to bottom.

## Rows

The Issue column names the acceptance criterion in the [refinement comment](https://github.com/TailTag-Game/tailtag/issues/483#issuecomment-6746970794).

### Start

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| S-01 | Both | None | Force-stop the app. Disconnect the host. Open the app from the Home Screen or the launcher. | The account screen opens. | AC4 |

### Email journey

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| J-01 | Both | E1 | Choose Create account. Enter a new `+clerk_test` address and the test code. | The onboarding form opens. | AC8 |
| J-02 | Both | E1 | Enter the handle `admin` and a display name. Tap Continue. | A server error shows under Handle. Both values stay. | #475 AC7 |
| J-03 | Both | E1 | Open window W1. Enter a new handle. Tap Continue. | The picker opens with no selected convention. | AC18 |
| J-04 | Both | E1 | Tap "Join and enter" on C1. Close W1. | The home shows the real name, dates, and status of C1, with no gameplay control. W1 shows one `PUT /api/profile/` 200 and one enrollment `POST` 201. | AC18 |
| J-05 | Both | E1 | Open window W2. Force-stop the app. Open it from the Home Screen or the launcher. | The C1 home opens with no onboarding. | AC19 |
| J-06 | Both | E1 | Leave the app for 30 seconds. Return to it. Close W2. | The C1 home stays. W2 shows reads and no write. | AC20 |
| J-07 | Both | E1 | Tap Change convention. Tap "Join and enter" on C2. | The C2 home opens. | AC21 |
| J-08 | Both | E1 | Open window W3. Tap Change convention. C1 shows as joined. Tap "Enter convention" on C1. Close W3. | The C1 home opens. W3 shows one `PUT /api/conventions/active/` 200 and no enrollment `POST`. | AC21 |
| J-09 | Both | E1 | Tap Change convention. Close the picker. | C2 showed as joined. The earlier enrollment stayed. | AC21 |
| J-10 | Both | E1 | Sign out. Choose Sign in. Enter the E1 address and a wrong code. | An error shows. The address stays, and another attempt is allowed. | AC27 |
| J-11 | Both | E1 | Open window W4. Enter the correct code. Close W4. | The C1 home opens. W4 shows no write. | AC11 |

### Passkeys on an email account

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| P-01 | Both | E1 | From the home, open Manage passkeys. Add a passkey through the system sheet. | The list shows the new passkey. | AC13 |
| P-02 | Both | E1 | Open window W5. Start another addition. Dismiss the sheet. Close the passkey screen, which reloads the home. Close W5. | The list showed no new row. No failure banner showed. W5 shows reads and no write. | AC15 |
| P-03 | Both | E1 | Sign out. Open window W6. Sign in with the passkey. Close W6. | The C1 home opens. W6 shows no write. | AC11, AC13 |
| P-04 | Both | E1 | Open Manage passkeys. Remove the passkey and confirm. | The list no longer shows it. | AC13 |

### Session isolation

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| I-01 | Both | E1 | Sign out. Use the system Back action. | The account screen stays. No E1 content shows. | AC23 |
| I-02 | Both | E2 | Create E2 with a new address. Type a handle on the form and do not submit it. Sign out. | The form opened empty. | AC23 |
| I-03 | Both | E1 | Sign in with E1. Sign out. | The C1 home showed. No E2 text showed. | AC23 |
| I-04 | Both | E2 | Sign in with E2. | The form opens empty. | AC23 |
| I-05 | Both | E2 | Complete the form with a new handle. Tap "Join and enter" on C2. | C1 and C2 showed as new, not joined. The C2 home opens. | AC23 |

### Network loss

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| N-01 | Both | E2 | Turn on airplane mode. Tap Change convention. | The screen offers Try again. It does not show the empty state. | AC28 |
| N-02 | Both | E2 | Turn off airplane mode. Tap Try again. Turn on airplane mode. Tap "Join and enter" on C1. | The app reports no success and offers Try again. It does not open the C1 home. | AC28 |
| N-03 | Both | E2 | Open window W7. Turn off airplane mode. Tap Try again. Close W7. | The app shows the state from the server. W7 shows reads and no write. | AC28 |

If the write in N-02 reached the server, W7 still shows no write, and the app shows C1 as the server state. Record which outcome happened.

### Inactive convention and disabled profile

The owner changes each status in Django admin and restores it in the same row. Before F-02, create D with a new `+clerk_test` address and complete its form, if D does not exist. Make sure that D is enabled.

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| F-01 | Both | E2 | Return to the home of the selected convention. The owner pauses that convention. Tap Refresh. | The home shows the status Paused and Change convention. The owner restores Active. | AC26 |
| F-02 | Both | D | Sign in with D and stop on the picker. The owner disables D. Leave the app for 5 seconds and return to it. A pull on the picker reloads only the lists. | The account-unavailable screen opens. Refresh and Sign out work. No participation action shows. | AC25 |
| F-03 | Both | D | The owner enables D. Tap Refresh. Sign out. | The app returns to the correct stage for D. | AC25 |

### Google

Before G-01 on each platform, the owner deletes the Clerk Development user for G, if one exists. Delete only that synthetic user. The orphan TailTag row stays and keeps its handle, so each fresh run needs a new handle.

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| G-01 | Both | G | Tap "Continue with Google". Choose G. | The onboarding form opens. | AC9 |
| G-02 | Both | G | Complete the form with a new handle. | The picker opens with no selected convention. | AC9 |
| G-03 | Android | G | From the picker, add a passkey. Sign out. Sign in with the passkey. | The picker opens with no selected convention. | #475 AC3 |
| G-04 | Android | G | Open Manage passkeys. Remove the last passkey and confirm. | The removal succeeds. | AC14 |
| G-05 | Both | G | Tap "Join and enter" on C2. | The C2 home opens. | AC11 |
| G-06 | Both | G | Sign out. Open window W8. Tap "Continue with Google". Choose G. Close W8. | The C2 home opens with no onboarding. W8 shows no write. | AC11 |
| G-07 | Both | G | Sign out. Open window W9. Tap "Continue with Google". Dismiss the sheet. Tap "Continue with Google" again and choose G. Close W9. | After the dismissal, the account screen stayed usable with no failure banner. The C2 home opens. W9 shows reads and no write. | AC15 |

### Apple

Before A-02, the owner deletes the Clerk Development user for A, if one exists. The owner then stops using the Apple Account with TailTag, as [Live Apple proof](mobile.md#live-apple-proof) step 4 describes.

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| A-01 | Android | None | Open the account screen. | No Apple control shows. | AC10 |
| A-02 | iOS | A | Tap the Apple button. Choose Hide My Email. | The onboarding form opens. Apple asks for no name. TailTag asks for no other email address. | AC10 |
| A-03 | iOS | A | Complete the form with a new handle. From the picker, add a passkey. Sign out. Sign in with the passkey. | The picker opens with no selected convention. | #475 AC3 |
| A-04 | iOS | A | Open Manage passkeys. Remove the last passkey and confirm. | The removal succeeds. | AC14 |
| A-05 | iOS | A | Tap "Join and enter" on C3. | The C3 home opens. | AC11 |
| A-06 | iOS | A | Sign out. Open window W10. Tap the Apple button. Close W10. | The C3 home opens with no onboarding. W10 shows no write. | AC11 |
| A-07 | iOS | A | Sign out. Open window W11. Tap the Apple button. Dismiss the sheet. Tap the Apple button again and continue. Close W11. | After the dismissal, the account screen stayed usable with no failure banner. The C3 home opens. W11 shows reads and no write. | AC15 |

### Identity in Django admin

| Row | Platform | Account | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- | --- |
| D-01 | Both | All | Search Player profiles for each handle that this pass created. | Each handle shows one profile. Record only the result. | AC12 |

### Accessibility

Run these rows on each of these screens: account access, email entry, code entry, onboarding, account unavailable, picker, home, and passkeys. Use E2 or a new `+clerk_test` address to reach onboarding, and use D for account unavailable.

| Row | Platform | Steps | Expected result | Issue |
| --- | --- | --- | --- | --- |
| X-01 | iOS | Turn on VoiceOver. Move through each control. Activate the main action. | Every control is reached and announces its label. The main action works. | AC31 |
| X-02 | Android | Turn on TalkBack. Move through each control. Activate the main action. | Every control is reached and announces its label. The main action works. | AC31 |
| X-03 | iOS | Set Larger Text to the size AX3. Open each screen. | No text clips. The main action stays reachable. | AC32 |
| X-04 | Android | Set Font size to 200%. Open each screen. | No text clips. The main action stays reachable. | AC32 |
| X-05 | Both | Connect a keyboard. Move with Tab through each control. | Focus reaches every control, and no control traps focus. A visible focus ring is not required. | AC33 |

## Reused and automated evidence

These rows do not run on the physical build. A row can reuse child evidence only when it cannot run on the frozen physical build. The evidence file names the source run, its commit, and the path diff to the frozen commit.

| Row | Evidence | Why it is not a physical row | Issue |
| --- | --- | --- | --- |
| U-01 | #480 AC39, an API 27 emulator run, and the unavailable widget tests | Android passkeys need API 28 or later, and no older phone is available. Every supported iOS version offers passkeys, so iOS has no natural unavailable state. | AC16 |
| U-02 | Automated tests for late responses | A person cannot time a late response by hand. | AC24 |
| U-03 | The #494 simulator proxy run | The proxy needs a temporary patch that sends the token over HTTP. A patched build is not the frozen commit. | AC29 |
| U-04 | Automated guideline tests for contrast and target size | The tests measure these rules. A person cannot. | AC34 |
| U-05 | #480 AC12 branch tests for the last-passkey rule | A live run cannot show which branch of the rule allowed a removal. | AC14 |

## After a fix

If a pass finds a defect, open a new Bug issue under #475 that names the owning child issue. Move the issue that owns this pass to Blocked in the TailTag Rebuild Project.

After the fix merges, choose a new frozen commit and rebuild both apps. Repeat each row whose path diff changed. Then repeat one full smoke journey on each platform: J-01, J-03, J-04, and J-05.

## After the pass

1. The owner sets C1, C2, and C3 to the status that the evidence records as the end state.
2. The owner makes sure that D is enabled.
3. Stop only the processes and emulators that this pass started.
4. Keep the proof accounts. A pass never deletes reachable player progress.

## Scan the evidence before commit

Run this search from the repository root before you commit either file. A clean file prints nothing from the last command. The `printf` line is the positive control, so it must print one line.

```bash
PATTERN='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|eyJ[A-Za-z0-9_-]{10,}|[ps]k_(test|live)_[A-Za-z0-9]+|(user|sess|sia|sua|idn|eac|client)_[A-Za-z0-9]{20,}|[a-z0-9-]+\.clerk\.accounts\.dev|([0-9A-F]{2}:){31}[0-9A-F]{2}'
printf 'name%sexample.test\n' '@' | grep -E "$PATTERN"
grep -nE "$PATTERN" docs/development/mobile-journey-checklist.md docs/development/mobile-journey-evidence-*.md
```

The search cannot find a handle, a verification code, or a credential ID that has no fixed shape. Read the evidence file once for those values.
