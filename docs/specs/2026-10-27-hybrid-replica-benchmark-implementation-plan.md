# Hybrid replica benchmark implementation plan (#359)

Issue: [#359](https://github.com/TailTag-Game/tailtag/issues/359), child 7 of [#352](https://github.com/TailTag-Game/tailtag/issues/352). Spec: the [approved refinement](https://github.com/TailTag-Game/tailtag/issues/359#issuecomment-6452985418) (AC11 to AC23) and the issue criteria AC1 to AC10. Contract: [hybrid replica contract](2026-10-22-hybrid-replica-contract.md), gate G-2.

[ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) stays in force. This plan changes no Railway, Development or Staging resource.

## Units

The work lands in four code pull requests, one per unit. Each says "Part of #359". A live phase and a proof pull request follow. Every live step needs its own owner approval.

| Unit | Content | Criteria |
| --- | --- | --- |
| U1 | Replica readiness accepts the ordered Clerk party pair. Terraform adds the `tt-simrelay` service account, its job and log view grants, and the token minter binding. Every job gets a fixed command, and the job runner refuses appended arguments and extra tasks. | AC11 (infrastructure), AC17 (server) |
| U2 | Replica relays for the pool, fixture and inspect channels, with a token file, a 150-second deadline and a 32,768-byte limit | AC3, AC11 (token use), AC16 |
| U3 | The simulator `replica` target, Clerk settings for each target, the `replica-burst` tier, the replica host session and evaluation keys | AC2, AC12, AC13, AC15, AC17 (client), AC23 |
| U4 | A cold probe in the simulator release, an idle state and cost reader for the owner workstation, and a replica section in the simulation host runbook | AC4, AC5, AC14, AC20, AC21, AC22 |
| Live | The step ladder R0 to R5 and the cold probes, then a proof document with receipts | AC1, AC6 to AC10, AC18, AC19 |

U2 needs the U1 apply before its first live use. U3 uses the U2 task names. U4 does not depend on U3 except for the runbook.

## U1 live steps

The owner does these steps after U1 merges, in order:

1. Add `simrelay_token_minter` to the foundation `terraform.tfvars`.
2. Pin the service traffic to the serving revision, as step 1 of the release runbook one-time setup says.
3. Run the foundation plan, read it, then apply it.
4. Run a release through the release workflow, so that the service runs the new readiness rule with the new party pair. Sync the other job images with `task replica-jobs-sync`.
5. Run the IAM readback for `tt-simrelay` from the trust runbook.

The apply also changes the command of all six jobs to `python -E -s -u manage.py <command>`. The old job images accept that command, because the arguments are the same.

The apply also makes one revision of the old image with the new party pair. That revision gets no traffic, and its readiness fails because the old image accepts only one party. It is never released.

## Facts to read during the U1 live steps

- The Logging API accepts the flexible log view filter on `resource.labels.job_name`. If it refuses it, the fallback filter keeps `resource.type` and `LOG_ID` only, and the proof records the wider view.
- Job executions inherit the job-level `roles/run.viewer`, so `run.executions.get` works.
- Running a job with overrides needs no `actAs` on `tt-runtime`.
- `entries.list` accepts the view resource name.
- Cloud Run sets `CLOUD_RUN_TASK_COUNT` to `1` and `CLOUD_RUN_TASK_INDEX` to `0` in each job task, so the runner admits a normal run.
- Cloud Run refuses an override that sets `CLOUD_RUN_TASK_COUNT` or `CLOUD_RUN_TASK_INDEX`. The owner tries one such override on the pool job and records the answer. If Cloud Run accepts it, the task check needs another source before the relays go live.
