You are an independent code reviewer from a different model family than the author. Review this branch diff adversarially against its acceptance criteria.

Issue #861: [P2.27] Route remaining direct provider constructions through the shared llm_resolution chain

Background:
- #768 (merged, PR #860) introduced codeframe/core/llm_resolution.py as the single source of truth for the provider chain: CLI flag → CODEFRAME_LLM_PROVIDER → .codeframe/config.yaml → "anthropic".
- Four code paths still construct providers directly, bypassing the chain. This PR routes all four through the chain.

Acceptance criteria (from issue):
- Each of the 4 sites resolves its provider via resolve_llm_settings/create_provider (OR explicitly documents why Anthropic-only).
- A regression test per site mirroring tests/ui/test_discovery_generate_tasks.py.

What was done:
- All 4 sites migrated to use create_provider(resolve_llm_settings(workspace.repo_path)):
  1. codeframe/core/conductor.py:SupervisorResolver.llm (was bare get_provider()).
  2. codeframe/core/dependency_analyzer.py:analyze_dependencies — dropped _get_default_provider() helper, inlined the chain at the call site when provider=None.
  3. codeframe/core/prd_discovery.py:PrdDiscoverySession.__post_init__ — kept api_key field as backward-compat (uses AnthropicProvider when set); uses the chain when api_key is unset. The missing-key check is generalized via LLMSettings.required_key_env so it now covers any keyed provider (was Anthropic-only).
  4. codeframe/core/adapters/streaming_chat.py:StreamingChatAdapter.__init__ fallback (when no provider given) — uses the chain. api_key param kept as backward-compat (now truly vestigial in fallback).
- New tests/core/test_provider_resolution_chain.py: 9 tests across 4 classes (one per site), mirroring the reference pattern (CODEFRAME_LLM_PROVIDER=ollama + delete ANTHROPIC_API_KEY + mock create_provider).

Verification:
- New tests: 9/9 pass.
- Existing tests: 84/84 pass (tests/core/test_supervisor_resolver.py + test_dependency_analyzer.py + test_prd_discovery.py + test_streaming_chat.py + tests/ui/test_discovery_generate_tasks.py).
- ruff: clean.

For each finding, output: severity (Critical / Major / Suggestion / Nitpick), file:line, one-sentence description, and the concrete failure scenario.
Focus on:
- Contract fulfillment vs acceptance criteria (4 sites + 4 tests)
- Correctness: any path where a hardcoded Anthropic assumption still leaks through?
- Backward-compat: does the api_key= backward-compat in PrdDiscoverySession / StreamingChatAdapter actually preserve the legacy contract?
- Test fidelity: do the regression tests prove the chain is used, or could they pass without it?
- Any production code path where the resolved provider would be wrong (e.g., threading workspace.repo_path incorrectly, missing model propagation in streaming_chat).

Skip style nitpicks unless objectively wrong. End with a one-line verdict: APPROVE or REQUEST_CHANGES.

DIFF attached as issue-861.diff.
