# Demo PR #888 — honor base_url on the Anthropic provider path (#780)

*2026-07-24T00:14:34Z by Showboat 0.6.1*
<!-- showboat-id: 96a4f409-5a95-4701-93fe-6a00e88b6cd4 -->

Criterion 1: get_provider('anthropic', base_url=...) must reach the Anthropic SDK client — previously it was silently dropped. Evidence: the constructed client's base_url is the override, not api.anthropic.com.

```bash
uv run python - <<'EOF'
import os
os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-demo-key'
from codeframe.adapters.llm import get_provider

p = get_provider('anthropic', base_url='http://litellm-proxy:4000')
print('provider.base_url =', p.base_url)
print('SDK client.base_url =', p.client.base_url)

default = get_provider('anthropic')
print('no override -> SDK default =', default.client.base_url)
EOF
```

```output
provider.base_url = http://litellm-proxy:4000
SDK client.base_url = http://litellm-proxy:4000
no override -> SDK default = https://api.anthropic.com
```

Criterion 2: an ambient OPENAI_BASE_URL (e.g. set for occasional ollama use) must NOT redirect Anthropic traffic — the env fallback is gated to OpenAI-compatible providers. Explicit config llm.base_url still applies to anthropic (proxy deployments).

```bash
uv run python - <<'EOF'
import os, tempfile
from pathlib import Path
from codeframe.core.llm_resolution import resolve_llm_settings

os.environ['OPENAI_BASE_URL'] = 'http://ollama-box:11434/v1'
repo = Path(tempfile.mkdtemp())

s = resolve_llm_settings(repo)
print('anthropic + ambient OPENAI_BASE_URL -> base_url =', s.base_url)

s = resolve_llm_settings(repo, provider_flag='ollama')
print('ollama    + ambient OPENAI_BASE_URL -> base_url =', s.base_url)

(repo / '.codeframe').mkdir()
(repo / '.codeframe' / 'config.yaml').write_text('llm:\n  provider: anthropic\n  base_url: http://corp-gateway:8080\n')
s = resolve_llm_settings(repo)
print('anthropic + explicit config llm.base_url -> base_url =', s.base_url)
EOF
```

```output
anthropic + ambient OPENAI_BASE_URL -> base_url = None
ollama    + ambient OPENAI_BASE_URL -> base_url = http://ollama-box:11434/v1
anthropic + explicit config llm.base_url -> base_url = http://corp-gateway:8080
```

Criterion 3: regression tests lock the behavior in (silent re-drop would fail the suite).

```bash
uv run pytest tests/core/test_llm_resolution.py -q 2>&1 | tail -2
```

```output
(8 durations < 0.005s hidden.  Use -vv to show these durations.)
============================== 22 passed in 1.36s ==============================
```
