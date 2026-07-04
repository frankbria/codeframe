# Changelog

All notable changes to CodeFRAME are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Server-side PROOF9 merge gate (#731): `POST /api/v2/pr/{n}/merge` now blocks while open (non-waived) requirements exist. An explicit `override: true` + `override_reason` bypasses the gate and records an audit entry (actor, reason, bypassed requirements, timestamp), surfaced as `merge_override` in `GET /api/v2/pr/history`. A proof-ledger failure blocks the merge (explicit 500) rather than silently allowing it.
- The same gate applies to `cf pr merge`: open requirements in the cwd workspace block the merge unless `--override --reason "..."` is given, which persists the same audit record.

## [0.9.1] - 2026-06-13

### Added
- `cf --version` / `cf -V` prints the installed version. (Note: with `uv tool install`, check the version via `uv tool list` or `cf --version` — the package is isolated, so a system Python's `importlib.metadata` will not see it.)
- `TRADEMARKS.md` — trademark policy clarifying that the AGPL covers the code, while the CodeFRAME name and logo are reserved trademarks (a fork may use the code but must rename).

### Fixed
- The default-`AUTH_SECRET` warning no longer prints on every `cf` command. It was emitted at import time and leaked onto the CLI (which never uses auth); the check now lives only in server startup validation, which still warns in self-hosted mode and fails hard in hosted mode.

### Changed
- README marks the CodeFRAME™ trademark and links the new policy; `LICENSING.md` notes the code/brand boundary.

## [0.9.0] - 2026-06-12

First public beta and the first release published to PyPI as
[`codeframe-ai`](https://pypi.org/project/codeframe-ai/). The `codeframe` name
on PyPI is taken by an unrelated package; a [PEP 541](https://peps.python.org/pep-0541/)
name claim is being pursued in parallel. The CLI entry point remains `cf`.

### Added
- **PyPI distribution.** Install with `uv tool install codeframe-ai`, `uvx codeframe-ai`, or `pipx install codeframe-ai`. Both `cf` and `codeframe` console scripts are provided.
- **Release automation.** Tag-triggered workflow builds with `uv build` and publishes to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no long-lived tokens). All actions are SHA-pinned.
- **Launch documentation.** `SECURITY.md` (private vulnerability reporting), `LICENSING.md` (plain-language AGPL-3.0 + commercial path), beta issue templates, and a refreshed `CONTRIBUTING.md`.
- This `CHANGELOG.md`.

### Fixed
- **Packaging was incomplete.** The wheel previously shipped only the top-level `codeframe` package (2 files), so an installed `cf` failed on import. Builds now include all subpackages and the `templates/` runtime data via setuptools auto-discovery.
- **Incorrect license metadata.** Package metadata declared MIT; the project is and always has been AGPL-3.0. Metadata now matches the `LICENSE` file.

### Changed
- Version bumped from a placeholder `0.1.0` to an honest beta `0.9.0`; development status classifier moved to `4 - Beta`.
- README installation section now leads with `uv tool install` instead of git-clone; status badge updated to **beta** with a stability statement.

[Unreleased]: https://github.com/frankbria/codeframe/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/frankbria/codeframe/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/frankbria/codeframe/releases/tag/v0.9.0
