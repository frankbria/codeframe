# Changelog

All notable changes to CodeFRAME are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/frankbria/codeframe/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/frankbria/codeframe/releases/tag/v0.9.0
