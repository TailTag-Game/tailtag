# TailTag domain language

This glossary records product language only. Technical design belongs in `docs/architecture.md` or an ADR. In particular, the accepted backend authentication and internal identity decisions do not define product terminology here.

## Established terms

### TailTag

The social convention game being rebuilt in this repository.

### Player

A person who participates in the game and attempts to discover and catch participating characters.

### Handle

A globally unique, mutable TailTag product identifier chosen for a player. Prefer “handle” over “username.”

### Display name

A mutable human-facing player name. It is not unique and is distinct from a handle.

### Participating character

A fursuit character enrolled in the game and available for players to discover and catch. Do not shorten this to “user”; a player and a participating character may have different product roles.

### Catch

The core game interaction in which a player discovers and catches a participating character. The exact eligibility, validation, and lifecycle rules are not yet defined.

### Convention

The real-world event context in which TailTag is played. Whether one convention can contain multiple game instances remains undecided.

## Unresolved language

Define these only when product decisions make them precise: account, attendee, game instance, enrollment, team, score, and organizer.
