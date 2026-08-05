# AF-Core Prompt Template Catalog

## 1. Purpose

This catalog provides reusable production prompt templates for
TOBMATE Agent Factory AF-Core.

Each template must be completed with a verified baseline, explicit
authority, measurable validation, rollback expectations, and
evidence requirements before execution.

## 2. Template Usage Rules

Operators must:

- replace every bracketed placeholder;
- remove sections that do not apply;
- preserve explicit exclusions and protected assets;
- define approval gates for high-risk actions;
- avoid combining unrelated objectives;
- verify return codes and resulting state;
- define regression expectations;
- specify final evidence and Git state.

A template is a starting contract, not execution authority.

## 3. Repository Implementation Template

```text
TITLE:
Implement [feature or module]

OBJECTIVE:
Implement [measurable capability] in [repository or project].

SCOPE:
- Repository:
- Branch:
- Included paths:
- Excluded paths:
- Protected existing changes:

BASELINE:
- Commit or tag:
- Current focused tests:
- Current full regression:
- Known constraints:

AUTHORITY:
- Permitted edits:
- Permitted tools:
- Approval-required actions:
- Prohibited actions:

EXECUTION:
1. Inspect architecture and ownership boundaries.
2. Identify dependencies and compatibility risks.
3. Produce an implementation plan.
4. Implement within the approved scope.
5. Add or update focused tests.
6. Run compatibility and regression validation.
7. Record changed files and design decisions.

COMPLETION:
- Required tests:
- Required artifacts:
- Required documentation:
- Required Git state:

ROLLBACK:
- Rollback point:
- Rollback trigger:
- Recovery validation:
```

## 4. Defect Remediation Template

```text
TITLE:
Remediate [defect or incident identifier]

OBJECTIVE:
Identify and correct the root cause of [observed failure].

EVIDENCE:
- Error message or failed test:
- Logs and timestamps:
- Affected environment:
- Last known good state:

SCOPE:
- Affected modules or services:
- Protected files and data:
- Excluded areas:

AUTHORITY:
- Permitted diagnostic actions:
- Permitted changes:
- Approval-required actions:
- Prohibited actions:

EXECUTION:
1. Confirm or reproduce the failure.
2. Preserve failure evidence.
3. Identify the exact root cause.
4. Apply the smallest safe correction.
5. Run focused validation.
6. Run broader regression when required.
7. Verify recovery and resulting state.

COMPLETION:
- Root cause recorded:
- Focused validation passed:
- Required regression passed:
- Recovery state verified:
- Remaining risks disclosed:

ROLLBACK:
- Last known good point:
- Rollback trigger:
- Post-rollback validation:
```

## 5. Production Release and Deployment Template

```text
TITLE:
Release and deploy [package or service version]

OBJECTIVE:
Build, validate, promote, and deploy [version] to [environment].

BASELINE:
- Current stable version:
- Candidate version:
- Commit and release tag:
- Current deployment state:
- Last known good artifact:

AUTHORITY:
- Release approval authority:
- Deployment authority:
- Rollback authority:
- Prohibited environments or actions:

ARTIFACTS:
- Wheel, image, or package:
- Source distribution:
- Checksums:
- Evidence directory:

EXECUTION:
1. Verify repository and release baseline.
2. Run focused and full regression.
3. Build versioned release artifacts.
4. Validate hashes and package metadata.
5. Install in an isolated environment.
6. Start and verify service health.
7. Perform restart validation.
8. Promote only after approval.
9. Verify deployed version and readiness.
10. Preserve deployment evidence.

ROLLBACK:
- Rollback artifact:
- Rollback trigger:
- Rollback command or procedure:
- Post-rollback health validation:
- Recovery promotion validation:

COMPLETION:
- Regression passed:
- Artifact verification passed:
- Isolated installation passed:
- Start and restart passed:
- Rollback and recovery passed:
- Deployment approval recorded:
- Final version and service state verified:
```
