# Features

Product features own their Views, ViewModels, Repositories, and Services.
A feature may depend on approved shared/core boundaries but must not import a
sibling feature. The app layer (`lib/app/`) composes features and wires their
navigation through callbacks, so a feature never imports `lib/app/`.

| Feature | Owns |
| --- | --- |
| `account_access` | Email account creation and sign-in screens and the in-memory email flow (#477) |
