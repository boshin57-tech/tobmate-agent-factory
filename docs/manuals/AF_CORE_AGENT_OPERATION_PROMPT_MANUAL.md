# AF-Core Agent Operation Prompt Manual

## 1. Purpose

This manual defines the production prompt contract for operating
TOBMATE Agent Factory AF-Core agents.

An operational prompt is not an informal chat message. It is an
execution specification that must define objective, authority,
constraints, evidence, validation, and completion conditions.

AF-Core uses prompts together with repository analysis, context
construction, planning, team formation, authority evaluation,
workflow orchestration, runtime policy, tool governance, assurance,
knowledge promotion, and delivery reporting.

## 2. Core Operating Principle

Every production prompt must answer seven questions:

1. What must be achieved?
2. What repository, project, or workspace is in scope?
3. What authority does the agent possess?
4. What actions and tools are permitted?
5. What actions are prohibited or require approval?
6. How must the result be validated?
7. What evidence proves completion?

A prompt that does not answer these questions is incomplete and must
not be treated as production-ready.

## 3. Standard Prompt Contract

Every AF-Core operational prompt should contain these sections:

### Objective

State one measurable outcome. Avoid combining unrelated projects or
multiple independent releases in one execution request.

### Scope

Identify repositories, branches, directories, services, modules,
documents, environments, and external systems that may be accessed.

### Current Baseline

Record the current branch, commit, tag, test count, deployment state,
known incidents, protected files, and existing uncommitted changes.

### Authority

Define the agent role, granted capabilities, delegated authority,
approval boundaries, ownership boundaries, and escalation path.

### Constraints

Define technical, security, operational, legal, schedule, cost, and
compatibility restrictions.

### Execution Requirements

Specify analysis, planning, implementation, testing, review,
completion audit, evidence generation, and delivery requirements.

### Completion Criteria

Define the exact tests, commands, artifacts, reports, Git state, and
operational observations required before completion may be declared.

## 4. Authority Rules

An agent must operate with least privilege.

The prompt must distinguish:

- permitted actions;
- approval-required actions;
- prohibited actions;
- delegated actions;
- emergency actions;
- rollback authority.

An agent must not infer destructive authority from a broad objective.

Examples of actions requiring explicit authority include:

- deleting files or persistent data;
- rewriting Git history;
- pushing to protected branches;
- publishing packages or releases;
- changing production infrastructure;
- rotating secrets or credentials;
- modifying access-control policy;
- disabling validation or audit controls.

## 5. Repository Safety Rules

The operational prompt must require the agent to:

- inspect the repository before editing;
- preserve existing uncommitted work;
- avoid overwriting unrelated changes;
- use explicit file and directory boundaries;
- run syntax and diff checks;
- record changed files and design decisions;
- create a rollback point before high-risk changes;
- never declare success from command output alone;
- verify exit codes and resulting state.


## 6. Execution Lifecycle

A production prompt should direct the agent through this lifecycle:

1. inspect the repository and operational environment;
2. establish the protected baseline;
3. identify gaps, dependencies, and risks;
4. construct execution context;
5. produce an authority-aware plan;
6. form the required specialist team;
7. execute tasks in dependency order;
8. validate each material change;
9. review security, compatibility, and quality;
10. audit completion against the original objective;
11. preserve reusable knowledge and evidence;
12. deliver the result with rollback information.

No lifecycle stage may be silently skipped.

## 7. Validation and Evidence

Completion evidence should include, where applicable:

- commands executed and their return codes;
- focused and full regression results;
- syntax, type, lint, and diff checks;
- changed-file inventory;
- generated artifacts and cryptographic hashes;
- service health and readiness results;
- deployment, restart, rollback, and recovery results;
- approval and authority decisions;
- audit, compliance, and policy outcomes;
- Git branch, commit, tag, and worktree state.

A passing test count without the tested scope is insufficient evidence.

The agent must distinguish:

- observed facts;
- test-confirmed results;
- inferred conclusions;
- unresolved risks;
- deferred work.

## 8. Failure and Recovery Rules

When an operation fails, the agent must:

1. stop dependent actions;
2. preserve logs and partial evidence;
3. identify the exact failed boundary;
4. determine whether state changed;
5. avoid repeating destructive actions blindly;
6. restore or roll back when authorized;
7. rerun the smallest relevant validation;
8. rerun broader regression when impact requires it;
9. record the failure and recovery result.

The agent must never replace a failed result with an optimistic summary.

## 9. Approval Gates

The prompt must define approval gates before actions such as:

- production deployment;
- irreversible data migration;
- protected-branch merge or push;
- package publication;
- external communication or notification;
- financial or regulated action;
- privilege expansion;
- secret or identity operation;
- destructive cleanup;
- final release promotion.

An approval gate must identify:

- the approving authority;
- the approved action;
- the approved scope;
- the approval lifecycle or expiry;
- the required audit evidence.

## 10. Prompt Quality Checklist

Before execution, confirm that the prompt has:

- one clear objective;
- an explicit scope;
- a verified baseline;
- defined authority;
- protected assets and prohibited actions;
- required tools and environments;
- dependency-aware execution steps;
- measurable validation criteria;
- rollback and recovery expectations;
- required evidence;
- final delivery requirements.

If any critical item is missing, the agent must resolve the ambiguity
before performing high-risk work.

## 11. Standard Operational Prompt Skeleton

```text
TITLE:
[Short execution title]

OBJECTIVE:
[One measurable outcome]

SCOPE:
- Repository or project:
- Branch or worktree:
- Included modules and services:
- Excluded areas:

BASELINE:
- Commit or tag:
- Current test result:
- Deployment state:
- Existing changes:
- Protected files and data:

AUTHORITY:
- Agent role:
- Granted capabilities:
- Approval-required actions:
- Prohibited actions:
- Escalation authority:

CONSTRAINTS:
- Technical:
- Security:
- Compatibility:
- Cost and time:
- Operational:

EXECUTION:
1. Inspect and lock the baseline.
2. Analyze gaps and dependencies.
3. Produce and validate a plan.
4. Implement within approved scope.
5. Run focused validation.
6. Run required regression.
7. Review and audit completion.
8. Preserve evidence and knowledge.

COMPLETION CRITERIA:
- Required test results:
- Required artifacts:
- Required operational checks:
- Required Git state:
- Required reports:

ROLLBACK AND RECOVERY:
- Rollback point:
- Rollback trigger:
- Recovery validation:

DELIVERY:
- Result summary:
- Changed files:
- Evidence locations:
- Remaining risks:
```

## 12. Completion Declaration

An agent may declare completion only when:

- the objective is satisfied;
- all required validation has passed;
- required approvals exist;
- evidence is preserved;
- rollback information is available;
- unresolved risks are explicitly disclosed;
- repository and operational state are known.

The completion declaration must state the actual result and must not
claim production readiness from design, code generation, or partial
testing alone.
