# AF-Core Agent Execution Guide

## 1. Purpose

This guide defines how an operator uses TOBMATE Agent Factory
AF-Core to execute repository, software, infrastructure, research,
documentation, and delivery work safely and repeatably.

It translates an approved operational prompt into an authority-aware,
dependency-aware, validated execution lifecycle.

## 2. Execution Roles

An AF-Core execution may involve these roles:

- Project Orchestrator: owns the project lifecycle and final state;
- Repository Analyzer: inspects code, structure, history, and risks;
- Context Builder: creates bounded execution context;
- Planning Engine: converts objectives into executable work;
- Team Builder: selects specialist roles and collaboration structure;
- Task Planner: defines tasks, dependencies, and completion criteria;
- Execution Coordinator: dispatches approved work;
- Validation Coordinator: runs required verification;
- Review Coordinator: examines quality, security, and compatibility;
- Completion Auditor: verifies final acceptance;
- Knowledge Promoter: preserves reusable implementation knowledge.

One agent may perform multiple roles only when authority and capability
requirements remain satisfied.

## 3. Pre-Execution Requirements

Before implementation begins, the operator must confirm:

- the objective is measurable;
- repository and workspace paths are correct;
- branch, commit, and tag are known;
- existing uncommitted work has been identified;
- protected files and data are listed;
- available tools and credentials are bounded;
- approval-required actions are defined;
- test and completion requirements are explicit;
- rollback and recovery expectations are recorded.

Production work must not begin from an unknown baseline.

## 4. Baseline Lock

The first execution step is to create a baseline record containing:

- repository name and absolute path;
- active branch and HEAD commit;
- relevant checkpoint or release tag;
- worktree status;
- current package and schema versions;
- current focused and full regression counts;
- running services and deployment state;
- known incidents or operational limitations;
- files and resources that must not be overwritten.

The baseline becomes the comparison point for all later validation,
rollback, recovery, and completion decisions.

## 5. Planning and Dependency Control

AF-Core must convert the approved objective into tasks that contain:

- one task identifier;
- one responsible role or team;
- explicit inputs and outputs;
- prerequisite tasks;
- required authority and capabilities;
- permitted tools;
- validation requirements;
- retry and timeout policy;
- completion and failure states.

Tasks must be scheduled only when their dependencies and authority
requirements are satisfied.

## 6. Authority-Aware Assignment

Before assigning a task, AF-Core must verify:

- the assigned role has the required capability;
- the authority is active and valid;
- delegated authority has not expired;
- the task remains inside the approved scope;
- prohibited or approval-gated actions are not bypassed;
- conflicting ownership or permissions have been resolved.

A task that fails authority evaluation must remain blocked, be
reassigned, or be escalated for approval.

## 7. Controlled Execution

During execution, the agent must:

1. inspect the target before editing;
2. preserve unrelated work;
3. modify only approved files and resources;
4. use explicit commands and argument vectors;
5. capture return codes and material output;
6. stop dependent work after a required failure;
7. avoid claiming success before validation;
8. record implementation decisions and changed files.

Destructive, irreversible, privileged, or production-facing actions
must pass their approval gate before execution.

## 8. Validation Flow

Validation should progress from narrow to broad:

1. syntax and import validation;
2. focused unit tests;
3. integration and compatibility tests;
4. security and policy checks;
5. full regression when impact requires it;
6. build and package verification;
7. isolated installation validation;
8. service health, restart, rollback, and recovery checks.

A failed validation result must retain its evidence and must not be
hidden by a later successful command.

## 9. Failure, Retry, and Recovery

When required execution or validation fails, AF-Core must:

- stop affected dependent tasks;
- preserve logs, return codes, and partial outputs;
- identify the exact failure boundary;
- determine whether persistent state changed;
- apply retry and backoff policy only when safe;
- avoid repeating irreversible operations blindly;
- roll back when an approved rollback condition is met;
- validate the restored or recovered state;
- record the failure, response, and final outcome.

Recovery is complete only after the required service, data, package,
workflow, or repository state has been revalidated.

## 10. Review and Completion Audit

Before completion, the Review Coordinator and Completion Auditor must
verify:

- the original objective was satisfied;
- all required tasks reached valid terminal states;
- authority and approval rules were followed;
- focused and required regression tests passed;
- security and compatibility requirements were met;
- artifacts and operational checks are complete;
- rollback and recovery evidence exists;
- unresolved risks and deferred work are disclosed;
- the final repository and deployment state are known.

A partial result must not be reported as full completion.

## 11. Evidence and Knowledge Preservation

The execution record should preserve:

- architecture and module purpose;
- changed files and implementation details;
- design decisions and their reasons;
- data structures, APIs, and event flows;
- security and performance considerations;
- commands, return codes, and test results;
- build, deployment, restart, rollback, and recovery evidence;
- Git commits, tags, branches, and checkpoints;
- reusable patterns, lessons learned, and known limitations.

Evidence locations must be explicit and reproducible.

## 12. Final Delivery

The final delivery report must contain:

- objective and achieved result;
- implementation scope;
- changed-file inventory;
- validation and regression results;
- package and artifact versions;
- service and deployment state;
- rollback and recovery instructions;
- evidence locations and hashes;
- unresolved risks and deferred work;
- Git commit, tag, and worktree status.

Completion may be declared only when the delivered report matches the
verified repository, package, and operational state.
