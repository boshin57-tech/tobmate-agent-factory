# TOBMATE Agent Factory AF-Core MVP Release Readiness Record

## 1. Release Identification

- Product: TOBMATE Agent Factory
- Component: AF-Core MVP
- Release classification: MVP Release Candidate
- Feature completion commit: `0ef007c`
- Feature completion tag: `checkpoint-17-af-core-mvp-v1`
- Final audit commit: `80a7f52`
- Final audit tag: `checkpoint-17-af-core-mvp-audit-v1`
- Final audited regression: `750 passed in 12.87s`
- Audited worktree: clean

This record determines whether the audited AF-Core MVP is ready to enter release packaging and remote publication.

## 2. Release Scope

The AF-Core MVP release includes:

- repository analysis and workspace coordination;
- context construction and task planning;
- agent runtime and restricted tool execution;
- validation, review and completion assurance;
- knowledge promotion and delivery services;
- project orchestration and E2E execution;
- runtime policy enforcement;
- capability and authority control;
- multi-agent and multi-team coordination;
- workflow dependency and trigger execution;
- workflow recovery and observability;
- persistent project-run lifecycle;
- dependency-aware autonomous task execution;
- explicit retry and restart recovery;
- cross-team artifact handoff;
- completion audit and validation;
- atomic delivery manifest and report generation.

## 3. Release Evidence Set

The required release evidence consists of:

1. source implementation;
2. complete automated test suite;
3. annotated feature tag;
4. annotated final-audit tag;
5. architecture document;
6. final audit record;
7. operator runbook;
8. release-readiness record;
9. full regression output;
10. clean Git worktree verification.

## 4. Final Documentation Set

### 4.1 Architecture

File:

`docs/final/AF_CORE_MVP_ARCHITECTURE.md`

Purpose:

- describes the final runtime architecture;
- records lifecycle and dependency behavior;
- records team authority and handoff controls;
- records validation and delivery architecture;
- defines architectural invariants;
- fixes the completed MVP boundary.

### 4.2 Audit Record

File:

`docs/final/AF_CORE_MVP_AUDIT_RECORD.md`

Purpose:

- records final audit scope;
- records executable security evidence;
- records recovery and delivery-integrity evidence;
- records residual risks;
- records final audit disposition.

### 4.3 Operator Runbook

File:

`docs/final/AF_CORE_MVP_OPERATOR_RUNBOOK.md`

Purpose:

- defines repository initialization;
- defines verification commands;
- defines restart and SSH recovery;
- defines retry and handoff operations;
- defines release stop conditions;
- defines backup and evidence retention.

### 4.4 Release Readiness

File:

`docs/final/AF_CORE_MVP_RELEASE_READINESS.md`

Purpose:

- consolidates all release gates;
- records accepted and deferred risks;
- defines the release candidate boundary;
- defines publication and rollback requirements.

## 5. Functional Completion Gate

Verified completion areas:

- AF-Core foundation: PASS
- repository analyzer: PASS
- workspace coordination: PASS
- context builder: PASS
- planning engine: PASS
- agent runtime: PASS
- tool registry: PASS
- assurance pipeline: PASS
- knowledge engine: PASS
- delivery service: PASS
- project orchestrator: PASS
- runtime policy: PASS
- capability and authority: PASS
- multi-agent coordination: PASS
- workflow orchestration: PASS
- workflow runtime recovery: PASS
- persistent project execution: PASS
- multi-team handoff control: PASS
- validation and completion audit: PASS
- final delivery lifecycle: PASS

Functional completion disposition: PASS

## 6. Architecture Gate

Verified architecture requirements:

- immutable project and task state;
- unique project-run identity;
- persistent event history;
- optimistic concurrency;
- atomic state persistence;
- dependency-cycle rejection;
- deterministic ready-task selection;
- explicit retry control;
- unique team ownership;
- capability-aware task assignment;
- target-controlled handoff;
- controlled terminal state;
- restart-safe recovery;
- deterministic final audit;
- atomic delivery generation.

Architecture gate disposition: PASS

## 7. Security and Authority Gate

Verified controls:

- unauthorized assignment is denied;
- authority denial is audited;
- stale state overwrite is denied;
- cyclic execution is denied;
- terminal-state reopening is denied;
- terminal-state resume is denied;
- source-team handoff acceptance is denied;
- pending handoff bypass is denied;
- unresolved blocker execution is denied;
- unresolved conflict execution is denied;
- partial delivery completion claim is denied.

Security and authority gate disposition: PASS

## 8. Recovery Gate

Verified recovery behavior:

- project state survives repository reload;
- active projects enter controlled recovery;
- recovery creates an immutable event;
- recovered state survives subsequent reload;
- terminal state remains terminal;
- recovery does not erase previous history;
- interrupted document generation can be safely cleaned without resetting audited source.

Recovery gate disposition: PASS

## 9. Delivery Gate

Verified delivery behavior:

- manifest generation: PASS
- completion-audit JSON generation: PASS
- human-readable report generation: PASS
- atomic writing: PASS
- temporary-file cleanup: PASS
- repeated write consistency: PASS
- completed decision consistency: PASS
- partial decision consistency: PASS
- task-status consistency: PASS
- artifact-reference consistency: PASS

Delivery gate disposition: PASS

## 10. Test Gate

Final audited regression:

```text
750 passed in 12.87s
```

Focused final verification:

```text
Final audit tests: 9 passed
Autonomous delivery E2E tests: 2 passed
```

No failed or errored test is accepted for release.

Test gate disposition: PASS

## 11. Git Integrity Gate

Required conditions:

- feature commit exists;
- feature tag points to the feature commit;
- audit commit exists;
- audit tag points to the audit commit;
- documentation changes are isolated;
- staged diff passes whitespace validation;
- final worktree is clean after commit;
- release tag points to the intended release commit.

Current pre-documentation checkpoint:

```text
80a7f52 checkpoint-17-af-core-mvp-audit-v1
```

Git integrity gate before documentation commit: PASS

## 12. Release Candidate Acceptance Criteria

AF-Core MVP may be declared a Release Candidate only when:

1. all four final documents exist;
2. all document consistency checks pass;
3. final audit tests pass;
4. autonomous-delivery E2E tests pass;
5. full regression passes;
6. documentation is committed;
7. the documentation tag points to the documentation commit;
8. the release tag points to the final release commit;
9. local worktree is clean;
10. remote commit and tags are verified after push.

## 13. Release Stop Conditions

Stop release when:

- any test fails or errors;
- documentation contradicts implementation;
- unexpected files appear in the worktree;
- a tag points to an incorrect commit;
- Git diff validation fails;
- generated delivery evidence is inconsistent;
- a required final document is absent;
- remote push fails;
- remote tag verification fails;
- the release branch differs from the intended branch;
- secrets or credentials are detected.

## 14. Accepted MVP Limitations

The following limitations are accepted for this MVP release candidate:

- JSON file persistence rather than a production database;
- local-process coordination rather than distributed locking;
- injected executor adapters rather than a production worker fleet;
- local delivery storage rather than remote artifact storage;
- repository-level identity rather than production identity-provider integration;
- automated repository audit rather than external penetration testing;
- functional regression rather than production-scale load testing.

These limitations do not invalidate the implemented MVP requirements.

## 15. Deferred Post-MVP Work

Deferred work includes:

- production database adapters;
- distributed queue and worker infrastructure;
- multi-process and multi-host locking;
- production secret management;
- external identity and authentication;
- remote artifact storage;
- production observability export;
- performance and capacity benchmarking;
- disaster-recovery exercises;
- infrastructure penetration testing;
- deployment automation;
- formal release artifact signing.

## 16. Rollback Requirements

Before remote publication, retain:

- feature tag `checkpoint-17-af-core-mvp-v1`;
- audit tag `checkpoint-17-af-core-mvp-audit-v1`;
- documentation commit hash;
- documentation tag;
- release commit hash;
- release tag;
- full regression output.

If publication validation fails:

1. do not delete existing audited tags;
2. do not rewrite published history;
3. identify whether failure is local or remote;
4. correct the release metadata in a new commit;
5. create a new versioned release tag;
6. rerun the complete release verification.

## 17. Remote Publication Requirements

Remote publication must include:

- the final main branch commit;
- the feature-completion tag;
- the final-audit tag;
- the documentation tag;
- the final release-candidate tag.

After push, verify:

- remote main branch commit;
- remote annotated tags;
- local and remote commit equality;
- clean local worktree.

## 18. Evidence Retention

Retain the following release evidence:

- `/tmp` regression output when available;
- test collection count;
- commit log output;
- tag target verification;
- final documentation files;
- release publication output;
- remote verification output.

Long-term evidence should be copied from temporary paths into the project release archive.

## 19. Release Readiness Decision

Current findings:

- feature implementation: COMPLETE
- architecture audit: PASS
- security audit: PASS
- recovery audit: PASS
- delivery-integrity audit: PASS
- operator documentation: COMPLETE
- release documentation: COMPLETE
- audited regression: PASS

The AF-Core MVP is ready to proceed to documentation commit, final full regression and Release Candidate publication verification.

Release readiness disposition: **READY**
