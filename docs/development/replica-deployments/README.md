# Hybrid replica release receipts

Each file in this directory is the sanitized receipt of one replica release or recovery run. The [release runbook](../hybrid-replica-release.md) says how to make one.

- Name each file `<candidate_revision>.json`.
- Commit receipts in a docs PR. The release workflow has no write access to the repository.
- A recovery needs a `PROMOTED` receipt for its target revision in this directory.
- Receipts hold no project ID, project number, host or credential.

The schema is `tailtag-replica-release-v1`. Its fields are the source SHA, image digest, CI run, workflow run, previous and candidate revisions, compatibility reference, migration result, gate results, serving revision, job digest state, drill flag, outcome and UTC times.
