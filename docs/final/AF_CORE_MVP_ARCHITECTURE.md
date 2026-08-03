# TOBMATE Agent Factory AF-Core MVP Architecture

## 1. Document Status

- Product: TOBMATE Agent Factory
- Component: AF-Core
- Release class: MVP feature-complete
- Feature commit: `0ef007c`
- Feature tag: `checkpoint-17-af-core-mvp-v1`
- Final audit commit: `80a7f52`
- Final audit tag: `checkpoint-17-af-core-mvp-audit-v1`
- Final regression: `750 passed in 12.87s`
- Audited worktree: clean

This document describes the finalized AF-Core MVP architecture.

The implementation and automated tests remain the technical source of truth.

## 2. Purpose

AF-Core is the autonomous project execution foundation of the TOBMATE Agent Factory.

It converts project requirements into a persistent, controlled and auditable lifecycle:

1. Create a project run.
2. Enter planning.
3. Register project tasks.
4. Validate task dependencies.
5. Identify dependency-ready tasks.
6. Assign authorized agents or teams.
7. Execute tasks.
8. Record outputs and failures.
9. Explicitly retry recoverable failures.
10. Coordinate cross-team artifact handoffs.
11. Validate completed work.
12. Audit project completion.
13. Generate final delivery evidence.
14. Recover persistent runs after restart.

## 3. Final Runtime Flow

```text
Project Run Creation
        |
        v
Planning
        |
        v
Task Registration
        |
        v
Dependency Graph Validation
        |
        v
Ready Task Resolution
        |
        v
Agent / Team Assignment
        |
        v
Capability and Authority Gate
        |
        v
Autonomous Task Execution
        |
        +---- Failure ----> Explicit Retry / Recovery
        |
        v
Artifact Output Recording
        |
        v
Cross-Team Handoff
        |
        v
Validation
        |
        v
Completion Audit
        |
        v
Completed / Partial / Failed
        |
        v
Manifest + Audit JSON + Delivery Report
```

## 4. Project Run Lifecycle

Project runs use immutable state objects.

Supported states:

- `CREATED`
- `PLANNING`
- `READY`
- `RUNNING`
- `PAUSED`
- `RECOVERING`
- `VALIDATING`
- `COMPLETED`
- `PARTIAL`
- `FAILED`
- `CANCELLED`

Each state transition:

- validates the requested transition;
- updates lifecycle timestamps;
- increments the persistent version;
- creates a corresponding event;
- preserves previous history.

Terminal project runs cannot return to active execution.

## 5. Project Task Lifecycle

Supported task states:

- `PENDING`
- `READY`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `BLOCKED`
- `SKIPPED`
- `CANCELLED`

An execution attempt is counted when a task enters `RUNNING`.

Failed tasks do not automatically return to the ready queue.
They require an explicit retry operation.

This prevents uncontrolled retry loops.

## 6. Persistent Project State

Primary module:

`src/af_core/orchestrator/project_execution_repository.py`

Responsibilities:

- JSON project-run persistence;
- atomic file replacement;
- optimistic version checking;
- immutable event history;
- run enumeration;
- resumable-run discovery;
- restart recovery support.

### Optimistic concurrency

Every state update supplies an expected version.

The repository rejects a write when the expected version differs from the persisted version.

This prevents stale workers from overwriting newer project state.

### Atomic persistence

State is first written to a temporary file and committed through atomic replacement.

Temporary files are removed after success or failure.

## 7. Dependency-aware Execution

Primary module:

`src/af_core/orchestrator/project_execution_runtime.py`

Responsibilities:

- create project runs;
- enter planning;
- register tasks;
- validate dependencies;
- reject unknown dependencies;
- detect graph cycles;
- finalize plans;
- identify ready tasks;
- deterministically select tasks;
- record assignments;
- begin task execution;
- complete or fail tasks;
- explicitly retry failed tasks;
- execute until blocked.

A task becomes ready only when all declared dependencies have succeeded.

Cyclic dependency graphs are rejected before execution begins.

## 8. Autonomous Task Executor

Task executors receive:

- the current immutable project run;
- the current task runtime state.

Executors return:

- success or failure;
- an optional output reference;
- failure information;
- optional execution metadata.

Executor exceptions and unsupported return values become auditable task failures.

## 9. Multi-Team Coordination

Primary modules:

- `src/af_core/orchestrator/project_team_coordination.py`
- `src/af_core/orchestrator/project_team_execution.py`

Responsibilities:

- unique task ownership;
- team responsibility roles;
- required capability enforcement;
- authority conflict detection;
- blocker management;
- artifact handoff management;
- team-aware task eligibility.

A team cannot own a task unless it possesses every capability required by that task.

An authority rejection:

1. denies assignment;
2. creates no ownership record;
3. records an unresolved authority conflict.

## 10. Artifact Handoff Control

When one team produces an artifact consumed by another team, AF-Core creates a formal handoff.

Handoff lifecycle:

```text
PENDING -> ACCEPTED -> COMPLETED
```

Only the target team may accept the handoff.

A downstream task remains ineligible until:

- its required handoff is completed;
- all blockers are resolved;
- all conflicts are resolved;
- all capability requirements are satisfied.

Dependencies owned by the same team do not require a cross-team handoff.

## 11. Blocker and Conflict Control

Blocker severity levels:

- low;
- medium;
- high;
- critical.

Unresolved blockers prevent affected tasks from executing.

Conflict categories:

- task ownership;
- authority;
- dependency;
- artifact;
- handoff.

Unresolved conflicts also prevent affected tasks from executing.

Resolution information and timestamps remain recorded.

## 12. Restart Recovery

Persistent project runs can be reconstructed after a process or host restart.

Recovery behavior:

- ready runs can return to execution;
- running and paused runs resume through `RECOVERING`;
- validating runs follow the controlled recovery path;
- terminal runs cannot be resumed.

Successful recovery creates a `RUN_RESUMED` event.

## 13. Validation and Completion Audit

Primary module:

`src/af_core/orchestrator/project_completion_audit.py`

The completion audit evaluates:

- total tasks;
- succeeded tasks;
- failed tasks;
- skipped tasks;
- cancelled tasks;
- nonterminal tasks;
- passed validations;
- failed validations;
- partial validations;
- validations not run;
- output references.

Final decisions:

- `COMPLETED`
- `PARTIAL`
- `FAILED`

A completed decision requires:

- every task succeeded;
- no failed task;
- no skipped task;
- no cancelled task;
- no nonterminal task;
- every required validation passed;
- no failed, partial or missing validation.

## 14. Delivery Lifecycle

Primary module:

`src/af_core/orchestrator/project_delivery_lifecycle.py`

The delivery lifecycle:

1. moves a running project to `VALIDATING`;
2. executes the completion audit;
3. selects the final terminal status;
4. creates a delivery manifest;
5. generates final evidence files.

Generated files:

- `delivery-manifest.json`
- `completion-audit.json`
- `delivery-report.txt`

All delivery files are written atomically.

## 15. Delivery Manifest

The delivery manifest includes:

- delivery ID;
- project run ID;
- project ID;
- repository path;
- completion decision;
- creation time;
- task output artifacts;
- task statuses;
- audit reasons;
- release metadata.

The manifest, completion audit and delivery report must describe the same final project state.

## 16. Persistent Event History

Important project events include:

- run created;
- run transitioned;
- run resumed;
- task registered;
- task transitioned;
- task assigned;
- task output recorded;
- checkpoint saved;
- delivery created.

Event history survives repository reload and restart recovery.

## 17. Main Implementation Files

| Area | File |
|---|---|
| Project models | `project_execution_models.py` |
| Persistence and recovery | `project_execution_repository.py` |
| Autonomous runtime | `project_execution_runtime.py` |
| Team registry | `project_team_coordination.py` |
| Team-aware execution | `project_team_execution.py` |
| Completion audit | `project_completion_audit.py` |
| Delivery lifecycle | `project_delivery_lifecycle.py` |
| Final E2E | `test_project_autonomous_delivery_e2e.py` |
| Security audit | `test_af_core_mvp_architecture_security_audit.py` |
| Recovery audit | `test_af_core_mvp_recovery_delivery_audit.py` |

## 18. Architectural Invariants

AF-Core MVP preserves the following invariants:

1. Every project run has a unique run ID.
2. Task IDs are unique within a project run.
3. Project state writes are version controlled.
4. Terminal project runs cannot reopen.
5. Terminal project runs cannot resume.
6. Unknown task dependencies are rejected.
7. Dependency cycles cannot enter execution.
8. Failed tasks require explicit retry.
9. Task ownership is unique per project run.
10. Required capabilities are checked before ownership.
11. Only target teams can accept handoffs.
12. Pending handoffs block downstream execution.
13. Unresolved blockers block execution.
14. Unresolved conflicts block execution.
15. Delivery status must match audit status.
16. Partial delivery cannot claim completion.
17. Persistent state survives repository restart.
18. State and delivery files are written atomically.

## 19. MVP Boundary

Checkpoint 17 completed AF-Core MVP feature implementation.

No additional MVP feature checkpoint should be added after:

- `checkpoint-17-af-core-mvp-v1`
- `checkpoint-17-af-core-mvp-audit-v1`

Subsequent work belongs to:

- documentation;
- operational deployment;
- release management;
- performance benchmarking;
- production infrastructure;
- post-MVP capability development.
