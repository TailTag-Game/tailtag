# Hybrid replica release receipts

Each file in this directory is the sanitized receipt of one replica release or recovery run. The [release runbook](../hybrid-replica-release.md) says how to make one.

- Name each file `<RUN_ID>-<RUN_ATTEMPT>.json`, from the workflow run.
- Commit every receipt in a docs PR, also for failed runs and drills. The release workflow has no write access to the repository.
- A recovery needs a `PROMOTED` receipt in this directory whose `candidate_revision` is its target revision.
- Receipts hold no project ID, project number, host or credential.

The schema is `tailtag-replica-release-v1`. Its fields are the source SHA, image digest, CI run, workflow run, previous and candidate revisions, compatibility reference, migration result, gate results, serving revision, job digest state, drill flag, outcome and UTC times.
