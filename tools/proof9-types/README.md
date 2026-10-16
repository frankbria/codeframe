# proof9 plugin API types (vendored)

`claude-code.d.ts` is the Claude Code plugin API's declarations. Only a running
Claude Code session writes them (into a loaded plugin's `.claude-plugin/types/`),
so CI cannot get them any other way. They live here, outside `proof9/`, so a
marketplace install does not ship them.

CI (`proof9-plugin` in `.github/workflows/test.yml`) installs exactly the Claude
Code version named on the file's first line and type-checks the plugin with
`tsc -p tools/proof9-types/tsconfig.json`. `tests/ci/test_proof9_distribution_1471.py`
fails if the two drift.

To move to a newer Claude Code: load the plugin once with that version
(`claude --plugin-dir ./proof9`), copy `proof9/.claude-plugin/types/claude-code/index.d.ts`
here as `claude-code.d.ts`, and bump the version in the workflow.
