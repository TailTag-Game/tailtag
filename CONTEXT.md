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

A fursuit character registered in TailTag. Its Convention activation,
operational eligibility, and catch-session state are distinct; do not shorten
this term to “user.”

### Catch

The core game interaction in which a player discovers and catches a participating character. The exact eligibility, validation, and lifecycle rules are not yet defined.

### Convention

The real-world event context in which TailTag is played. Whether one convention can contain multiple game instances remains undecided.

### Enrollment

A player's durable participation relationship with a Convention. Enrollment is
distinct from selecting an active Convention and does not activate the player's
fursuits.

### Fursuit activation

An owner's durable selection of a specific fursuit to participate in a specific
Convention. Prefer “activation” over “registration” for this per-Convention
selection.

### Operational eligibility

The current upstream conditions that permit an activated fursuit to participate
at its Convention. Eligibility may change without rewriting the owner's durable
activation selection.

### Operational participation

The state in which a fursuit activation is active and currently operationally
eligible. This is distinct from the owner's durable activation selection alone.

### Catch session

A temporary period when an operationally participating fursuit is out and
catchable. A catch session is distinct from durable Convention activation.

## Unresolved language

Define these only when product decisions make them precise: account, attendee,
game instance, team, score, and organizer.
