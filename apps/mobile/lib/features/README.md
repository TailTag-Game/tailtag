# Features

Product features own their Views and ViewModels. ADR 0006 also gives them their
Repositories and Services. For the #475 milestone, shared data repositories stay
in `lib/core/`. Profile data lives in `lib/core/session/`. The import guard does
not change.

A feature may depend on approved shared/core boundaries but must not import a
sibling feature. The app layer (`lib/app/`) composes features and wires their
navigation through callbacks, so a feature never imports `lib/app/`.

| Feature | Owns |
| --- | --- |
| `account_access` | Email, Google, and Apple account access screens, the Google and Apple buttons, and the in-memory access flow (#477, #478, #479) |
| `onboarding` | The handle and display name form, its save, and read-first recovery (#481) |
