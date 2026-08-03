# TOBMATE Agent Factory AF-Core MVP v1.0.0

## Release Status

- Product: TOBMATE Agent Factory
- Component: AF-Core
- Release: MVP v1.0.0
- Promotion source: `af-core-mvp-v1.0.0-rc2`
- RC2 source commit: `ffd1355`
- Stable package version: `1.0.0`
- RC2 regression baseline: `752 / 752 PASS`

## Release Scope

AF-Core MVP v1.0.0 includes the completed autonomous project execution lifecycle, authority-aware multi-agent coordination, workflow orchestration, recovery, validation, delivery evidence, MCP integration and distribution packaging.

## RC2 Correction

RC2 corrected the distribution metadata by declaring the required MCP runtime dependencies:

- `httpx>=0.27.1,<1`
- `mcp>=1.29,<2`

The correction is protected by packaging audit tests and was validated through clean installation, full regression, Wheel installation and runtime smoke testing.

## Validation Evidence

- Local regression: 752 / 752 PASS
- Clean detached-checkout regression: 752 / 752 PASS
- Fresh dependency installation: PASS
- MCP imports: PASS
- Wheel build: PASS
- Source distribution build: PASS
- Wheel metadata audit: PASS
- Artifact checksum verification: PASS
- Fresh Wheel installation: PASS
- Installed runtime smoke: PASS
- Remote RC2 commit and tags: VERIFIED

## Release Evidence Archive

```text
/home/boshin57/tobmate-releases/af-core-mvp-v1.0.0-rc2
```

The archive contains the RC2 Wheel, source distribution, SHA-256 checksums, clean validation record and publication record.

## Stable Promotion Requirements

Stable promotion requires:

1. package metadata version `1.0.0`;
2. complete regression from the release branch;
3. Wheel and source distribution named `1.0.0`;
4. clean Wheel installation;
5. checksum verification;
6. clean Git worktree;
7. stable commit and annotated tag;
8. remote branch and tag verification.

## Accepted MVP Limitations

- JSON persistence remains the MVP storage adapter.
- Distributed locking and worker infrastructure are post-MVP work.
- External penetration testing and production load testing remain separate production-readiness activities.
- Production identity, secret management and remote artifact storage remain deployment integrations.

## Promotion Decision

This record authorizes technical validation for promotion from RC2 to AF-Core MVP v1.0.0. Stable release is not final until the stable artifact and remote tag checks pass.

## Stable Validation Result

- Package version: `1.0.0`
- Test collection: `752`
- Full regression: `752 / 752 PASS`
- Stable Wheel build: PASS
- Stable source distribution build: PASS
- Wheel metadata audit: PASS
- Runtime dependency audit: PASS
- Artifact checksums: PASS
- Fresh Wheel installation: PASS
- MCP imports: PASS
- Runtime smoke: PASS
- Source worktree integrity: PASS

Stable technical validation disposition: **PASS**
