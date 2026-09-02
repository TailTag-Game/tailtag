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

### Fursuit TailTag identity

The immutable public identity of one participating character across
Conventions. It is distinct from an internal record identifier and from every
Convention-scoped catch credential.

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

### Catch credential

An opaque, revocable locator for one fursuit activation at one Convention. It
may survive catch-session boundaries but is neither a global fursuit identity
nor authorization to create a catch.

### Current catch credential

The sole unrevoked catch credential for a fursuit activation. A revoked catch
credential is historical and can never become current again.

### Catch credential payload

The versioned application-protocol value encoded by a client as a QR code and
submitted for resolution. It contains no player, fursuit, Convention, or
relationship identity beyond its opaque credential value.

### Catch credential resolution

A current preview that maps a catch credential payload to safe participating-
character information only while the target is catchable. Resolution is not
authorization to create a catch.

## Unresolved language

Define these only when product decisions make them precise: account, attendee,
game instance, team, score, and organizer.
