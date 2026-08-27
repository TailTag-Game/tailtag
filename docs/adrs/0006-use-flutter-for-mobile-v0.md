# Use Flutter for mobile framework in v0
**Status**: accepted

## Context and constraints
We have a small team, and we need a framework that is quick to write in and cross-platform, and forgiving enough when it comes to state management and the ease of development, and familiar.

## Decision
While Dart is not a common language, it is an amalgamation of a bunch of popular languages, so it should feel familar to most developers. Additionally, Flutter is fast to develop in, and state management is intuitive and non-difficult. The library ecosystem is also larger than Compose Multiplatform, and doesn't fall into the JavaScript traps of RN, that is, making it way too easy to write slow, state-hell code.

## Alternatives considered
Compose Multiplatform, React Native.

## Consequences and risks
We must pay attention to app "feel" and "vibes" and ensure the app stays responsive and doesn't feel "non-native."

## Validation and future migration
Flutter and Jetpack Compose use a very similar heirarchy system, so while the syntax and code isn't reusable, the general structure will be if we ever decide to move over to Compose.
