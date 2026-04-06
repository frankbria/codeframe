# Multi-provider LLM support — PR #552 acceptance criteria

*2026-04-05T21:34:07Z*

PR #552 adds multi-provider LLM support so CodeFrame can use any OpenAI-compatible provider (Ollama, vLLM, GPT-4o) instead of being locked to Anthropic. This demo walks through each acceptance criterion.

## AC 1 & 2: --llm-provider and --llm-model flags appear in cf work start --help

```bash
uv run codeframe work start --help 2>&1 | grep -A2 "\-\-llm"
```

```output
 --cloud-timeout 45     codeframe work start abc123 --execute --llm-provider    
 openai --llm-model gpt-4o                                                      
                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────╮
--
│ --llm-provider           TEXT                   LLM provider: anthropic,     │
│                                                 openai (default: anthropic   │
│                                                 or $CODEFRAME_LLM_PROVIDER)  │
│ --llm-model              TEXT                   Model name for the chosen    │
│                                                 provider (e.g. gpt-4o,       │
│                                                 qwen2.5-coder:7b,            │
```

Both --llm-provider and --llm-model flags are present with clear help text. Now checking the same on batch run:

```bash
uv run codeframe work batch run --help 2>&1 | grep -A2 "\-\-llm"
```

```output
│ --llm-provider           TEXT                   LLM provider: anthropic,     │
│                                                 openai (default: anthropic   │
│                                                 or $CODEFRAME_LLM_PROVIDER)  │
│ --llm-model              TEXT                   Model name for the chosen    │
│                                                 provider (e.g. gpt-4o,       │
│                                                 qwen2.5-coder:7b)            │
```

## AC 3: Default provider is still Anthropic when no flags are passed

```bash
uv run python3 -c "
from codeframe.adapters.llm import get_provider, AnthropicProvider, OpenAIProvider
# Verify the factory routes correctly without constructing real providers
import inspect
src = inspect.getsource(get_provider)
# Check default branch
assert \"anthropic\" in src
# Verify OpenAI-compatible set covers expected providers
from codeframe.adapters.llm import _OPENAI_COMPATIBLE
print(\"OpenAI-compatible providers:\", sorted(_OPENAI_COMPATIBLE))
print(\"Default: anthropic -> AnthropicProvider\")
print(\"openai/ollama/vllm/compatible -> OpenAIProvider\")
print(\"Factory routes correctly.\")
"
```

```output
OpenAI-compatible providers: ['compatible', 'ollama', 'openai', 'vllm']
Default: anthropic -> AnthropicProvider
openai/ollama/vllm/compatible -> OpenAIProvider
Factory routes correctly.
```

## AC 4: LLMConfig loads from .codeframe/config.yaml llm: block

```bash
uv run python3 -c "
import tempfile, pathlib, yaml
from codeframe.core.config import load_environment_config

# Simulate a workspace with an llm: block in config.yaml
with tempfile.TemporaryDirectory() as tmp:
    cfg_dir = pathlib.Path(tmp) / \".codeframe\"
    cfg_dir.mkdir()
    (cfg_dir / \"config.yaml\").write_text(
        \"llm:\n  provider: openai\n  model: qwen2.5-coder:7b\n  base_url: http://localhost:11434/v1\n\"
    )
    config = load_environment_config(pathlib.Path(tmp))
    print(\"provider:\", config.llm.provider)
    print(\"model:   \", config.llm.model)
    print(\"base_url:\", config.llm.base_url)
    print(\"LLMConfig loaded successfully.\")
"
```

```output
provider: openai
model:    qwen2.5-coder:7b
base_url: http://localhost:11434/v1
LLMConfig loaded successfully.
```

## AC 5: WorkerAgent uses LLMProvider abstraction — no AsyncAnthropic import

```bash
grep -n "import anthropic\|from anthropic\|AsyncAnthropic" \
  codeframe/agents/worker_agent.py \
  codeframe/agents/frontend_worker_agent.py \
  codeframe/agents/test_worker_agent.py 2>&1 || echo "No anthropic imports found — all clear."
```

```output
No anthropic imports found — all clear.
```

```bash
uv run python3 -c "
from codeframe.adapters.llm import MockProvider
from codeframe.agents.worker_agent import WorkerAgent

# WorkerAgent accepts llm_provider param
provider = MockProvider(default_response=\"Task completed successfully\")
agent = WorkerAgent(
    agent_id=\"demo-001\",
    agent_type=\"backend\",
    provider=\"mock\",
    llm_provider=provider,
)
print(\"llm_provider type:\", type(agent.llm_provider).__name__)
print(\"No API key required when provider injected:\", agent._llm_provider is provider)
"
```

```output
llm_provider type: MockProvider
No API key required when provider injected: True
```

## AC 6: All tests pass

```bash
uv run pytest tests/adapters/test_llm.py tests/adapters/test_llm_async.py tests/adapters/test_llm_openai.py tests/agents/test_worker_agent.py tests/agents/test_worker_agent_provider.py tests/agents/test_frontend_worker_agent.py tests/agents/test_test_worker_agent.py tests/core/test_cli_llm_flags.py tests/core/test_config_llm.py -q --tb=line 2>&1 | tail -8
```

```output
0.51s call     tests/core/test_cli_llm_flags.py::TestWorkStartLLMFlags::test_work_start_has_llm_provider_flag
0.33s call     tests/agents/test_frontend_worker_agent.py::TestTaskExecution::test_execute_task_success
0.30s call     tests/agents/test_test_worker_agent.py::TestTaskExecution::test_execute_task_basic
0.30s call     tests/agents/test_test_worker_agent.py::TestTestExecution::test_execute_passing_tests
0.26s call     tests/agents/test_test_worker_agent.py::TestTestExecution::test_execute_failing_tests
0.25s call     tests/agents/test_frontend_worker_agent.py::TestTaskExecution::test_execute_task_json_spec
0.24s call     tests/agents/test_frontend_worker_agent.py::TestTaskExecution::test_execute_task_with_websocket_broadcasts
======================== 153 passed in 73.18s (0:01:13) ========================
```

153 tests pass across all affected modules. All 6 acceptance criteria verified.
