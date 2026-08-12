# Use PostgreSQL as the primary database

**Status:** accepted

## Context and constraints

TailTag needs a relational primary store for user identity and gameplay data, with reliable constraints, transactions, and a production-compatible local and CI environment.

## Decision

Use PostgreSQL as the primary application database for V0, including local development, CI, and Railway environments.

## Alternatives considered

SQLite for local or test environments, another managed relational database, or a database abstraction that delays the choice.

## Consequences and risks

PostgreSQL adds setup and operational requirements, but reduces environment drift and supports the relational behavior expected by Django. Contributors need a documented local database workflow.

## Validation and rollback

Phase 0 must establish a reproducible PostgreSQL-backed contributor environment and migration checks. A database migration would require a reviewed migration plan, compatibility validation, and rollback strategy.
