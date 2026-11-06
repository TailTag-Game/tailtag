# Features

Product features own their Views, ViewModels, Repositories, and Services.
A feature may depend on approved shared/core boundaries but must not import a
sibling feature. The app layer (`lib/app/`) composes features and wires their
navigation through callbacks, so a feature never imports `lib/app/`.

| Feature | Owns |
| --- | --- |
| `account_access` | Email, Google, and Apple account access screens, the Google and Apple buttons, and the in-memory access flow (#477, #478, #479) |
