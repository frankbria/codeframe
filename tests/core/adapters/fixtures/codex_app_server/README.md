# Codex app-server protocol fixture

Checked-in JSON Schemas for the `codex app-server` stdio protocol, used by
`tests/core/adapters/test_codex.py` to validate every message `CodexAdapter`
writes to the subprocess (issue #914).

Generated with **codex-cli 0.141.0**:

```bash
codex app-server generate-json-schema --out /tmp/codex-schema
cp /tmp/codex-schema/{ClientRequest,ClientNotification,\
CommandExecutionRequestApprovalResponse,FileChangeRequestApprovalResponse}.json \
   tests/core/adapters/fixtures/codex_app_server/
```

Only the four schemas the adapter actually emits are kept. Refresh them when
bumping the supported Codex CLI version; a contract-test failure after a refresh
means the adapter's outbound messages drifted from the protocol.
