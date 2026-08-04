# AF-Core Production Release Runbook

## 1. Purpose

This runbook defines the controlled production lifecycle for AF-Core:

- release preflight;
- reproducible deployment packaging;
- package integrity verification;
- installation and configuration;
- process startup and readiness verification;
- graceful shutdown;
- upgrade and rollback;
- backup and recovery;
- immutable release evidence collection.

This document accompanies the deployment and process-supervision components
implemented in Checkpoint 18-F.

## 2. Current Package Facts

- Distribution name: `af-core`
- Current project version: `1.0.0`
- Required Python version: `>=3.11`
- Build backend: `hatchling.build`
- Shell command evaluation is prohibited.
- Release commands use explicit argument vectors.
- AF-Core currently has no console-script or module entrypoint.
- Every deployment must declare and review its exact `ExecStart` arguments.

A release must not depend on an undocumented command such as
`python -m af_core`.

## 3. Deployment Safety Principles

1. Build from a clean and approved Git commit.
2. Use an immutable release ID.
3. Hash every payload file with SHA-256.
4. Verify the manifest and payload before installation.
5. Reject traversal paths, symlinks and unexpected files.
6. Publish release directories atomically.
7. Keep configuration and secrets outside release payloads.
8. Acquire exclusive PID ownership before startup.
9. Require startup and readiness health gates.
10. Use bounded graceful shutdown after `SIGTERM`.
11. Apply bounded restart and backoff policies.
12. Create a consistent backup before every upgrade.
13. Maintain an approved previous release for rollback.
14. Publish credential-free release evidence.
15. Never place credentials or private keys in reports.

## 4. Recommended Filesystem Layout

Recommended production paths:

- `/opt/tobmate/af-core/releases/`
- `/opt/tobmate/af-core/temporary/`
- `/opt/tobmate/af-core/current-release`
- `/opt/tobmate/af-core/venv/`
- `/opt/tobmate/af-core/reports/`
- `/etc/tobmate/af-core/af-core.env`
- `/var/lib/tobmate/af-core/database/`
- `/var/lib/tobmate/af-core/artifacts/`
- `/var/lib/tobmate/af-core/backups/`
- `/var/lib/tobmate/af-core/recovery/`
- `/run/tobmate/af-core/af-core.pid`
- `/etc/systemd/system/af-core.service`

Recommended permissions:

| Path type | Mode |
|---|---:|
| Release and operational directories | `0750` |
| Payload files | `0640` |
| Executable payload files | `0750` |
| PID ownership record | `0640` |
| Release evidence report | `0640` |
| Generated systemd unit | `0644` |
| Secret environment file | `0600` or stricter |

The service account may write only to required runtime paths.
Immutable releases and prior evidence must not be modified in place.

## 5. Required Release Inputs

Record these values before execution:

- approved Git branch and commit;
- approved package version;
- immutable release ID;
- explicit payload file list;
- exact service argument vector;
- absolute working directory;
- PID file path;
- environment file path;
- database and artifact paths;
- backup and recovery paths;
- previous known-good release ID;
- service user and group;
- startup, readiness and shutdown timeouts;
- restart policy, backoff, window and limit;
- release evidence report path.

Release ID format:

`release-<32 lowercase hexadecimal characters>`

## 6. Preflight Gate

Run preflight before building or installing a release:

```bash
cd ~/tobmate-agent-factory
source .venv-af-core/bin/activate

git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --pretty=%s

python --version
python -m pip check
python -m pytest --collect-only -q
python -m pytest -q
git diff --check
```

Preflight passes only when:

- the approved branch and commit are checked out;
- the worktree state is reviewed;
- Python satisfies `>=3.11`;
- dependency validation passes;
- test collection succeeds;
- the full regression suite passes;
- `git diff --check` passes;
- backup and recovery capability is available;
- operational paths are absolute and symlink-safe.

Do not continue after a failed required preflight step.

## 7. Build and Package

Build the Python distribution from the approved source state:

```bash
cd ~/tobmate-agent-factory
source .venv-af-core/bin/activate

rm -rf dist build
python -m build
```

Record the exact wheel and source archive filenames.
Production automation must not select release files by wildcard.
Every package path must be resolved and reviewed before execution.

The deployment package may contain only approved release files:

- the exact built wheel;
- reviewed configuration examples;
- the generated systemd unit;
- this production release runbook;
- an approved service launcher, when one exists;
- the release manifest and its SHA-256 digest.

The package must be created through the AF-Core deployment API using:

- `ReleaseIdentity`;
- `DeploymentPackagePlan`;
- explicit `ReleasePackageInput` records;
- an approved absolute destination root;
- optional atomic current-release activation.

Do not package secrets, runtime databases, PID files or prior reports.
Do not reference a service launcher that is absent from the payload.

## 8. Package Integrity Gate

Before installation, verify all of the following:

1. Load `release-manifest.json`.
2. Verify the manifest SHA-256 digest.
3. Verify the immutable release identity.
4. Verify the exact top-level inventory.
5. Verify the exact payload inventory.
6. Verify every payload file size.
7. Verify every payload SHA-256 digest.
8. Verify executable-mode declarations.
9. Reject symlinks and non-regular files.
10. Reject traversal paths and unexpected entries.
11. Reject duplicate published release IDs.

Installation is prohibited when any integrity check fails.
Do not repair or replace files inside a published release directory.
Publish a new immutable release instead.

## 9. Installation

Create or reuse the controlled production virtual environment:

```bash
python -m venv /opt/tobmate/af-core/venv
/opt/tobmate/af-core/venv/bin/python -m pip install --upgrade pip
```

Install only the exact wheel verified by the package integrity gate:

```bash
/opt/tobmate/af-core/venv/bin/python -m pip install \
  /opt/tobmate/af-core/releases/<release-id>/payload/packages/<approved-wheel>.whl
```

Wildcard package selection is prohibited in production automation.
The installed wheel path must match the verified release manifest.

After installation, verify the environment:

```bash
/opt/tobmate/af-core/venv/bin/python -m pip check
/opt/tobmate/af-core/venv/bin/python -c "import af_core; print(af_core.__file__)"
```

Installation succeeds only when:

- dependency validation passes;
- `af_core` imports from the approved virtual environment;
- the installed distribution version matches the release manifest;
- no unapproved package was installed;
- the immutable release payload remains unchanged.

Installation does not authorize service startup.
Configuration, process policy, systemd publication and health gates must pass first.

## 10. Configuration

Runtime configuration must remain outside immutable release directories.

Recommended environment file:

`/etc/tobmate/af-core/af-core.env`

Configuration requirements:

- use an approved owner and group;
- apply mode `0600` or stricter;
- never store secrets in Git;
- never place secrets in release manifests;
- never embed secrets in systemd unit text;
- never include secrets in release evidence;
- pass only approved environment keys to the service.

Before startup, validate configuration through the AF-Core production APIs.

Required checks:

- every configured filesystem path is absolute;
- required directories exist with approved ownership and permissions;
- symlink components are rejected;
- required environment keys are present;
- unknown or prohibited keys are rejected;
- secret values are never written to logs or reports;
- the process and systemd environment-file paths match;
- the configured service user and group match deployment policy.

Configuration validation failure blocks service startup.

## 11. Service Startup and Readiness

Service startup is permitted only after installation and configuration pass.

Before launching the process:

- verify the exact approved argument vector;
- verify the absolute working directory;
- verify the environment-file path;
- verify the service user and group;
- verify that the release payload is unchanged;
- acquire exclusive PID ownership;
- reject a live PID owned by another service instance;
- replace only a verified stale PID record;
- record the immutable release ID for the process.

AF-Core has no implicit `python -m af_core` entrypoint.
The approved launcher must exist in the verified release payload.
Shell command evaluation and command-string execution are prohibited.

After process creation, apply startup and readiness gates:

- confirm the process remains alive during the startup window;
- confirm PID ownership matches the launched process;
- execute the approved readiness probe;
- require readiness success before traffic or work assignment;
- record startup and readiness durations;
- stop the process when a required health gate fails;
- publish credential-free failure evidence.

Publish the reviewed systemd unit atomically, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable af-core.service
sudo systemctl start af-core.service
sudo systemctl status af-core.service --no-pager
```

Promotion succeeds only when the service is active and readiness passes.

## 12. Graceful Shutdown

Use controlled shutdown for normal stop, upgrade and rollback operations.

Shutdown sequence:

1. Stop accepting new work.
2. Mark the service unavailable for new assignments.
3. Send `SIGTERM` to the verified owned process.
4. Allow the configured graceful-shutdown timeout.
5. Confirm the process has exited.
6. Remove only the matching PID ownership record.
7. Record shutdown duration and final status.
8. Use forced termination only after the timeout expires.

Never signal a PID unless ownership and process identity are verified.
A stale or mismatched PID record must not authorize process termination.

Forced termination is permitted only when graceful shutdown times out.

Forced-stop requirements:

- verify process identity again before escalation;
- record that the graceful timeout expired;
- send the configured forced-termination signal;
- confirm process exit before PID record removal;
- record the escalation as release evidence;
- investigate repeated forced shutdowns before the next release.

Restart policy requirements:

- restart only failures permitted by the approved policy;
- apply bounded backoff between attempts;
- enforce a restart-count limit within a fixed window;
- stop automatic restart when the limit is exceeded;
- preserve the last failure reason;
- require operator review after restart exhaustion.

## 13. Upgrade Procedure

Before beginning an upgrade:

1. Complete the full preflight gate.
2. Verify the new immutable deployment package.
3. Record the currently active release ID.
4. Confirm the previous release remains available.
5. Create and verify a consistent backup.
6. Confirm the rollback plan and commands.
7. Confirm sufficient disk capacity.
8. Confirm approved maintenance timing.
9. Stop new work assignment before shutdown.

Do not start an upgrade without a verified rollback target.
The current release, backup and evidence must remain unchanged.

Upgrade execution order:

1. Publish the verified new release directory.
2. Stop the current service gracefully.
3. Confirm the previous process has exited.
4. Install the exact verified distribution.
5. Apply reviewed external configuration.
6. Publish the reviewed systemd unit atomically.
7. Run `systemctl daemon-reload`.
8. Start the new release.
9. Require startup and readiness success.
10. Run post-upgrade health validation.
11. Record the active release identity.
12. Publish credential-free upgrade evidence.

Upgrade promotion is prohibited when a required step fails.
When rollback-on-failure is enabled, immediately enter the rollback plan.
Do not delete the prior release or backup after initial promotion.

## 14. Rollback Procedure

Trigger rollback when any required upgrade condition fails, including:

- installation failure;
- startup failure;
- readiness failure;
- post-upgrade health failure;
- configuration incompatibility;
- operational integrity failure;
- restart-policy exhaustion.

Before rollback execution:

1. Record the failed release ID and failing step.
2. Stop new work assignment.
3. Preserve failure evidence.
4. Verify the previous immutable release.
5. Verify the rollback configuration.
6. Verify the backup and recovery paths.
7. Confirm the rollback command argument vectors.

Do not modify the failed release in place.

Rollback execution order:

1. Stop the failed release gracefully.
2. Confirm the failed process has exited.
3. Restore the approved previous release.
4. Restore compatible external configuration.
5. Restore required operational state from backup when necessary.
6. Publish the previous systemd unit atomically.
7. Run `systemctl daemon-reload`.
8. Start the previous release.
9. Require startup and readiness success.
10. Run post-rollback health validation.
11. Record the restored active release ID.
12. Publish credential-free rollback evidence.

Rollback succeeds only when readiness and post-rollback health both pass.
A failed rollback must immediately enter the recovery procedure.
Do not delete the failed release, backup or evidence before investigation.

## 15. Backup and Recovery

Create a consistent backup before every production upgrade.

Backup procedure:

1. Record the active release ID.
2. Stop new state-changing work.
3. Flush pending durable writes.
4. Create database and artifact snapshots.
5. Copy approved external configuration.
6. Record package and schema versions.
7. Calculate SHA-256 digests for backup files.
8. Write a credential-free backup manifest.
9. verify the backup in a separate location.
10. record backup completion evidence.

A backup is not valid until its inventory and digests are verified.
Secrets must remain protected and must not appear in backup reports.

Recovery procedure:

1. Declare the service unavailable for new work.
2. Preserve failure and rollback evidence.
3. Verify the selected backup manifest and SHA-256 digests.
4. Stop any remaining owned service process.
5. Restore the approved release package.
6. Restore compatible configuration.
7. Restore database and artifact state.
8. Apply required schema or compatibility checks.
9. Publish the approved systemd unit atomically.
10. start the recovered release.
11. require startup and readiness success.
12. run recovery integrity and health validation.
13. publish credential-free recovery evidence.

Recovery succeeds only when restored state integrity and readiness pass.
Failed recovery requires operator escalation and no automatic promotion.
Preserve the failed state, backup and reports for investigation.

## 16. Release Evidence and Audit

Publish a release evidence report for every install, upgrade, rollback and recovery drill.

The report must record:

- immutable release identity;
- release operation mode;
- operation start and completion times;
- ordered step identifiers and phases;
- pass, failure, timeout and skipped status;
- process exit codes when available;
- step durations;
- the first failing step;
- whether rollback was triggered;
- final release-drill status;
- evidence report creation time.

Reports must not contain command arguments, environment values, credentials,
private keys, access tokens, database contents or secret filesystem paths.

Evidence publication requirements:

- create the report in the approved report directory;
- reject symlinked report paths and path components;
- write through a temporary regular file;
- flush report contents before publication;
- replace the destination atomically;
- apply report mode `0640`;
- flush the report directory after replacement;
- preserve previous release evidence according to retention policy;
- restrict report access to approved operators and auditors.

Evidence publication failure makes the release operation incomplete.
Do not report operational success until durable evidence exists.

## 17. Operational Completion Checklist

A release operation is complete only when all applicable items pass:

- approved commit and release identity recorded;
- full regression suite passed;
- deployment package and manifest verified;
- backup created and independently verified;
- exact install and service argument vectors reviewed;
- configuration and secret boundaries validated;
- process PID ownership established;
- startup and readiness gates passed;
- post-operation health validation passed;
- rollback or recovery result recorded when triggered;
- credential-free evidence published atomically;
- active release identity confirmed;
- operator and reviewer sign-off recorded.

Required sign-off fields:

- release ID;
- Git commit;
- operation mode;
- operator;
- reviewer;
- start and completion time;
- final status;
- evidence report path;
- active release ID after completion.

A failed required item blocks production completion and promotion.
