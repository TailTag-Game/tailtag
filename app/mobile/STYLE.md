# Style Guidelines
Code should generally follow the Flutter style guidelines. 

# TODO: Decisions
Obviously, strings should be largely localized. But for, say, debug code, should we use '' or ""? Both are valid in Flutter and neither are preferred.
Should we enable strict-casts? This prevents `dynamic` types from being cast without a type annotation. This prevents mistreatment of dynamic types.
Should we enable strict-inference? This prevents Dart from choosing `dynamic` as a type when inferring a type. This allows the developer to skip types while not accidentally making dynamic types when not intended.
Should we enable strict-raw-types? This prevents raw types (types with no hints). For example, List a = [1, 2, 3], results in the raw result of List<dynamic>, not List<int>, so this option reduces confusion.

Should we enable always-specify-types? (No `var`) I think strict-inference is probably enough.
