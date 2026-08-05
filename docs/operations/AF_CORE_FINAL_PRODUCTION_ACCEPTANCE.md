# AF-Core Final Production Acceptance

## 1. Purpose

This document records the final production acceptance basis for
TOBMATE Agent Factory AF-Core Checkpoint 19.

It consolidates the verified service host, operational entrypoint,
release lifecycle, rollback, recovery, prompt operations, and
execution-governance evidence required before final closure.

## 2. Release Identity

- Product: TOBMATE Agent Factory AF-Core
- Checkpoint: 19
- Candidate package version: `1.1.0`
- Previous stable package version: `1.0.0`
- Branch: `feature/post-mvp-production-readiness`
- Final closure tag: `checkpoint-19-af-core-final-closure-v1`

The final commit and remote tag are recorded during Part 5 after
the complete regression and release verification have passed.

## 3. Acceptance Scope

Production acceptance covers:

- production configuration and secret boundaries;
- durable persistence and migration control;
- health, readiness, startup, and liveness probes;
- metrics and service lifecycle integration;
- signal-aware process shutdown;
- official `af-core-service` console command;
- package installation and version promotion;
- service start and restart;
- rollback from `1.1.0` to `1.0.0`;
- recovery promotion from `1.0.0` to `1.1.0`;
- operational prompt and agent execution documentation;
- final regression, artifact, Git, and closure evidence.

## 4. Acceptance Principles

Acceptance requires observed and reproducible evidence.

Design completion, code generation, partial testing, or optimistic
reporting alone cannot establish production readiness.

All required checks must verify both command return codes and the
resulting repository, package, process, and service state.

## 5. Production Service Acceptance

The official production process boundary is provided by:

- `ProductionServiceHost`;
- `ServiceRuntime` lifecycle composition;
- health and readiness registries;
- metrics integration;
- `SignalShutdownController`;
- `ServiceProbeApplication`;
- the `af-core-service` console command;
- the module entrypoint;
  `python -m af_core.production.service_entrypoint`.

Verified service-host evidence:

- Service Host tests: 20 of 20 passed;
- Entrypoint tests: 7 of 7 passed;
- combined focused tests: 27 of 27 passed;
- TCP health and probe routing passed;
- malformed request rejection passed;
- probe socket release passed;
- signal installation and removal passed;
- SIGTERM graceful shutdown returned exit code zero;
- public configuration output excluded secrets.

## 6. Release Lifecycle Acceptance

The release lifecycle was validated in an isolated environment.

Verified lifecycle sequence:

1. built stable package version `1.0.0`;
2. built candidate package version `1.1.0`;
3. installed stable `1.0.0` in an isolated virtual environment;
4. upgraded the same environment to candidate `1.1.0`;
5. verified the official service command and configuration;
6. started, stopped, and restarted the candidate service;
7. rolled back from `1.1.0` to `1.0.0`;
8. verified package and dependency integrity after rollback;
9. promoted again from `1.0.0` to `1.1.0`;
10. restarted and revalidated the recovered service.

Both release Wheel artifacts were recorded with SHA-256 hashes.

## 7. Operational Documentation Acceptance

The following operational documents form part of acceptance:

- Agent Operation Prompt Manual;
- Agent Execution Guide;
- Prompt Template Catalog;
- Production Release Runbook;
- Final Production Acceptance record.

These documents define authority, execution, validation,
approval, evidence, rollback, recovery, and completion rules.

## 8. Final Acceptance Gates

Final closure requires all of these gates:

- production service and entrypoint tests pass;
- complete regression passes with zero failures;
- package version `1.1.0` builds successfully;
- isolated installation and dependency checks pass;
- service start, shutdown, and restart pass;
- rollback to `1.0.0` passes;
- recovery promotion to `1.1.0` passes;
- operational documentation contracts pass;
- artifact hashes and release evidence are preserved;
- Git diff and worktree state are verified;
- final commit and closure tag are created;
- branch and tag are pushed to the remote repository.

## 9. Evidence Locations

- Checkpoint audit directory: `/home/boshin57/tobmate-release-validation/af-core-checkpoint-19-20260804-120418`
- Service-host focused test records;
- Entrypoint process E2E records;
- Stable and candidate Wheel artifacts;
- Wheel SHA-256 evidence;
- Upgrade, restart, rollback, and recovery logs;
- Prompt Manual, Execution Guide, and Template Catalog;
- final regression and release verification records.

## 10. Acceptance Status

- Checkpoint 19 Part 1: passed;
- Checkpoint 19 Part 2: passed;
- Checkpoint 19 Part 3: passed;
- Checkpoint 19 Part 4 documentation: passed;
- Checkpoint 19 Part 5 final Git promotion: authorized.

Status: `ACCEPTED`

This acceptance becomes effective after the final commit, tag,
branch push, and remote verification pass.
