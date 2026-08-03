# TOBMATE Agent Factory AF-Core MVP Operator Runbook

## 1. Runbook Status

- Product: TOBMATE Agent Factory
- Component: AF-Core MVP
- Audited commit: `80a7f52`
- Audited tag: `checkpoint-17-af-core-mvp-audit-v1`
- Final regression: `750 passed in 12.87s`
- Intended audience: operator, maintainer and release engineer

This runbook defines the minimum operational procedures for the audited AF-Core MVP repository.

## 2. Repository Location

Expected repository:

```text
~/tobmate-agent-factory
```

Expected virtual environment:

```text
.venv-af-core
```

## 3. Session Initialization

Run the following at the beginning of every maintenance session:

```bash
cd ~/tobmate-agent-factory
source .venv-af-core/bin/activate
set -euo pipefail
```

Confirm the active Python environment:

```bash
which python
python --version
pytest --version
```

## 4. Audited Baseline Verification

Verify the current audited checkpoint:

```bash
git log -1 --oneline --decorate
git describe --tags --exact-match HEAD
git status --short
```

Expected audited baseline before documentation commit:

```text
Commit: 80a7f52
Tag: checkpoint-17-af-core-mvp-audit-v1
```

An empty `git status --short` output means the worktree is clean.

## 5. Standard Verification Sequence

Run checks in this order:

1. syntax and import checks;
2. focused audit tests;
3. autonomous project E2E tests;
4. full test collection;
5. complete regression;
6. Git diff and worktree checks.

### 5.1 Syntax check

```bash
python -m compileall -q src/af_core tests
```

### 5.2 Final audit suite

```bash
pytest -q tests/audit
```

Expected result:

```text
9 passed
```

### 5.3 Autonomous delivery E2E

```bash
pytest -q tests/unit/test_project_autonomous_delivery_e2e.py
```

Expected result:

```text
2 passed
```

### 5.4 Complete regression

```bash
pytest -q
```

Final audited result:

```text
750 passed in 12.87s
```

Test duration may vary, but no failed or errored test is acceptable for release.

## 6. Project Run Persistence

AF-Core project runs are stored through `JsonProjectRunRepository`.

Operational requirements:

- repository directories must be writable;
- state files must not be manually edited;
- temporary files must not be treated as final state;
- project versions must not be bypassed;
- backups must preserve state and event files together.

## 7. Recovery Procedure

After an interrupted process or host restart:

1. reconnect to the host;
2. enter the repository;
3. activate `.venv-af-core`;
4. inspect the Git worktree;
5. inspect persistent project-run state;
6. use the project resume service;
7. verify the resulting `RUN_RESUMED` event;
8. rerun focused recovery tests before continuing.

Recovery verification command:

```bash
pytest -q tests/audit/test_af_core_mvp_recovery_delivery_audit.py
```

Do not attempt to resume a terminal project run.

## 8. Failed Task Handling

Failed tasks require an explicit retry.

Before retrying, verify:

- all dependencies succeeded;
- the project run is active or recovering;
- the original error was reviewed;
- the owning team remains authorized;
- no unresolved blocker remains;
- no unresolved conflict remains.

Automatic uncontrolled retries are outside the MVP operating policy.

## 9. Multi-Team Handoff Operations

Cross-team artifact handoffs follow:

```text
PENDING -> ACCEPTED -> COMPLETED
```

Operational rules:

- only the target team accepts the handoff;
- acceptance alone does not finish the handoff;
- downstream execution waits for completion;
- unresolved blockers continue to prevent execution;
- same-team dependencies bypass cross-team handoff creation.

## 10. Blocker and Conflict Operations

Before executing a task, confirm that it has:

- an authorized owner;
- all required capabilities;
- no unresolved blocker;
- no unresolved conflict;
- all required completed handoffs.

Blockers and conflicts must be resolved through their lifecycle APIs rather than deleted from stored state.

## 11. Validation and Finalization

A running project must enter `VALIDATING` before final delivery.

Finalization requires validation evidence for every task that is expected to support a completed decision.

Possible final project states:

- `COMPLETED`
- `PARTIAL`
- `FAILED`

Operators must not manually change a partial or failed decision to completed.

## 12. Delivery Evidence

The delivery writer generates:

- `delivery-manifest.json`
- `completion-audit.json`
- `delivery-report.txt`

Verify that:

- all three files exist;
- run IDs agree;
- final decisions agree;
- task statuses agree;
- expected artifact references are present;
- no temporary files remain.

## 13. Git Safety Rules

Before committing:

```bash
git diff --check
git status --short
```

After staging:

```bash
git diff --cached --check
git diff --cached --stat
```

Never commit:

- virtual environments;
- test cache directories;
- runtime temporary files;
- local secrets;
- generated credentials;
- unrelated worktree changes.

## 14. SSH Interruption Recovery

When SSH disconnects during file generation:

1. reconnect;
2. inspect `git status --short`;
3. inspect the affected file;
4. remove only the interrupted untracked artifact;
5. verify the audited commit and tag;
6. restart the interrupted step.

Do not reset or clean the entire repository unless every uncommitted change has been reviewed.

## 15. Release Stop Conditions

Stop the release process when any of the following occurs:

- a failed or errored test;
- an unexpected worktree change;
- an unknown untracked file;
- a tag that points to the wrong commit;
- a stale-version persistence error;
- a dependency-cycle acceptance;
- an unauthorized team assignment;
- a pending handoff bypass;
- inconsistent delivery decisions;
- temporary-file residue after atomic writing.

## 16. Backup and Evidence Retention

Preserve the following together:

- Git commit hash;
- annotated release tag;
- full regression output;
- test collection count;
- architecture document;
- final audit record;
- operator runbook;
- release-readiness record.

## 17. Escalation Boundary

Escalate rather than bypass controls when:

- project state cannot be loaded;
- optimistic concurrency repeatedly fails;
- terminal state must allegedly be reopened;
- authority requirements appear incorrect;
- handoff ownership is disputed;
- delivery evidence is inconsistent;
- production infrastructure differs from the audited assumptions.

## 18. Operational Conclusion

The AF-Core MVP is operationally acceptable only when the audited tests pass, the required evidence exists and the Git worktree contains no unexpected changes.
