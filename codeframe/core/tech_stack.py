"""Tech-stack detection from a repository's files (#1381).

The one detector every surface uses: ``cf init --detect``, web workspace init
and the Settings auto-detect toggle. Two copies disagreed (the web UI's
reported uv for any pyproject mentioning uvicorn), and the agent reads this
text, so the same repo was described differently depending on where it was
detected. Headless and filesystem-only.
"""

import json
from pathlib import Path


def detect_tech_stack(repo_path: Path) -> str:
    """Auto-detect tech stack from project files and return a description.

    Returns a natural language description of the detected tech stack.
    """
    detected_parts = []

    # Python detection
    if (repo_path / "pyproject.toml").exists():
        pyproject = (repo_path / "pyproject.toml").read_text(encoding="utf-8", errors="replace")

        # Detect Python version
        python_version = None
        if (repo_path / ".python-version").exists():
            python_version = (repo_path / ".python-version").read_text(encoding="utf-8", errors="replace").strip()

        # Detect package manager
        if "[tool.poetry]" in pyproject:
            pkg_mgr = "poetry"
        elif "[tool.uv]" in pyproject or (repo_path / "uv.lock").exists():
            pkg_mgr = "uv"
        else:
            pkg_mgr = "pip"

        python_part = f"Python{' ' + python_version if python_version else ''} with {pkg_mgr}"

        # Detect test framework
        if "pytest" in pyproject:
            python_part += ", pytest"

        # Detect lint tools
        lint_parts = []
        if "[tool.ruff]" in pyproject:
            lint_parts.append("ruff")
        if "[tool.mypy]" in pyproject:
            lint_parts.append("mypy")
        if lint_parts:
            python_part += f", {'/'.join(lint_parts)} for linting"

        detected_parts.append(python_part)

    elif (repo_path / "requirements.txt").exists():
        python_version = None
        if (repo_path / ".python-version").exists():
            python_version = (repo_path / ".python-version").read_text(encoding="utf-8", errors="replace").strip()
        detected_parts.append(f"Python{' ' + python_version if python_version else ''} with pip")

    # Node.js/TypeScript detection
    if (repo_path / "package.json").exists():
        try:
            pkg_json_text = (repo_path / "package.json").read_text(encoding="utf-8", errors="replace")
            pkg_json = json.loads(pkg_json_text)
        except (json.JSONDecodeError, FileNotFoundError):
            pkg_json = {}
            pkg_json_text = ""

        # Detect Node version
        node_version = None
        if (repo_path / ".nvmrc").exists():
            node_version = (repo_path / ".nvmrc").read_text(encoding="utf-8", errors="replace").strip()
        elif (repo_path / ".node-version").exists():
            node_version = (repo_path / ".node-version").read_text(encoding="utf-8", errors="replace").strip()

        # Detect package manager
        if (repo_path / "pnpm-lock.yaml").exists():
            pkg_mgr = "pnpm"
        elif (repo_path / "yarn.lock").exists():
            pkg_mgr = "yarn"
        else:
            pkg_mgr = "npm"

        # Detect if TypeScript
        is_ts = (repo_path / "tsconfig.json").exists() or "typescript" in pkg_json_text

        lang = "TypeScript" if is_ts else "JavaScript"
        node_part = f"{lang}{' (Node ' + node_version + ')' if node_version else ''} with {pkg_mgr}"

        # Detect framework
        deps = pkg_json.get("dependencies", {})
        dev_deps = pkg_json.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}

        if "next" in all_deps:
            node_part += ", Next.js"
        elif "react" in all_deps:
            node_part += ", React"
        elif "vue" in all_deps:
            node_part += ", Vue"
        elif "svelte" in all_deps:
            node_part += ", Svelte"

        # Detect test framework
        if "jest" in all_deps:
            node_part += ", jest"
        elif "vitest" in all_deps:
            node_part += ", vitest"
        elif "mocha" in all_deps:
            node_part += ", mocha"

        detected_parts.append(node_part)

    # Rust detection
    if (repo_path / "Cargo.toml").exists():
        detected_parts.append("Rust with cargo")

    # Go detection
    if (repo_path / "go.mod").exists():
        detected_parts.append("Go")

    # Build the final description
    if not detected_parts:
        return ""

    if len(detected_parts) == 1:
        return detected_parts[0]

    # Multiple languages/stacks (monorepo)
    return "Monorepo: " + "; ".join(detected_parts)
