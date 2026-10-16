"""The PROOF9 evidence report (#1472): ``cf proof export --format pdf|html|json``.

A presentation layer over what the ledger already stores, made to be printed
and handed to someone who has never seen CodeFRAME. ``export_document`` builds
the JSON source; ``render_html`` renders it (Jinja2 with autoescaping, so user
text can never become markup); ``render_pdf`` prints that HTML with a headless
Chrome or Chromium. Nothing here upgrades a status: evidence is re-verified,
and evidence that fails verification is reported as failing.
"""

import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from jinja2 import Environment

from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import EvidenceTamperError, verify_evidence
from codeframe.core.proof.models import ReqStatus
from codeframe.core.proof.serialize import evidence_to_dict, requirement_to_dict, run_summary
from codeframe.core.workspace import Workspace

# The browsers whose --print-to-pdf renders the HTML; no PDF dependency is added.
_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")


def _state(req) -> str:
    """What the report calls a requirement: its status, with a lapsed waiver named."""
    if req.waiver and ledger.waiver_expired(req) and req.status != ReqStatus.SATISFIED:
        return "waiver expired"
    return req.status.value


def _commit(repo_path: Path) -> str | None:
    return _git(repo_path, "rev-parse", "HEAD")


def _git(repo_path: Path, *args: str) -> str | None:
    try:
        ran = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return ran.stdout.strip() if ran.returncode == 0 else None


def _repository(repo_path: Path) -> str:
    """How a shared report names the repo: its origin URL, else its folder (#1518).

    A local absolute path means nothing to the reader and leaks the sender's
    username and layout. Credentials embedded in the URL are dropped.
    """
    url = _git(repo_path, "remote", "get-url", "origin")
    if not url:
        return repo_path.name
    parts = urlsplit(url)
    if parts.username or parts.password:
        url = urlunsplit(parts._replace(netloc=parts.hostname + (f":{parts.port}" if parts.port else "")))
    return url


def _shareable_path(artifact_path: str, repo_path: Path) -> str:
    """Repo-relative when inside the repo; otherwise the file name alone (#1518)."""
    path = Path(artifact_path)
    try:
        return path.relative_to(repo_path).as_posix()
    except ValueError:
        return path.name


def _verified(evidence) -> bool:
    try:
        verify_evidence(evidence)
    except EvidenceTamperError:
        return False
    return True


def export_document(workspace: Workspace) -> dict:
    """The report as plain data: the JSON format, and what HTML and PDF render."""
    from codeframe import __version__

    requirements = []
    for req in ledger.list_requirements(workspace):
        row = requirement_to_dict(req)
        row["state"] = _state(req)
        row["evidence"] = [
            {
                **evidence_to_dict(ev),
                "artifact_path": _shareable_path(ev.artifact_path, Path(workspace.repo_path)),
                "verified": _verified(ev),
            }
            for ev in ledger.list_evidence(workspace, req.id)
        ]
        requirements.append(row)
    return {
        "provenance": {
            "repository": _repository(Path(workspace.repo_path)),
            "commit": _commit(Path(workspace.repo_path)),
            "tool_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "requirements": requirements,
        # The whole history: -1 is SQLite's "no limit", so the cover's count is the truth.
        "runs": [run_summary(r) for r in ledger.list_runs(workspace, limit=-1)],
        "merge_overrides": ledger.list_merge_overrides(workspace),
    }


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>PROOF9 evidence report</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;color:#111}
h1{font-size:1.6rem}h2{border-bottom:1px solid #999;margin-top:2rem}
table{border-collapse:collapse;width:100%;font-size:.85rem}
td,th{border:1px solid #bbb;padding:.3rem .45rem;text-align:left;vertical-align:top}
.cover{page-break-after:always}.tag{font-weight:700;padding:0 .3rem;border:1px solid}
.satisfied{color:#176b2c}.open{color:#8a5a00}.waived{color:#555}.expired,.fail{color:#a11}
.vacuous{color:#7a6400}code{font-size:.8rem;word-break:break-all}
</style></head><body>
<section class="cover">
<h1>PROOF9 evidence report</h1>
<table>
<tr><th>Repository</th><td>{{ doc.provenance.repository }}</td></tr>
<tr><th>Commit</th><td><code>{{ doc.provenance.commit or "not a git commit" }}</code></td></tr>
<tr><th>Tool</th><td>codeframe-ai {{ doc.provenance.tool_version }}</td></tr>
<tr><th>Generated</th><td>{{ doc.provenance.generated_at }}</td></tr>
<tr><th>Requirements</th><td>{{ doc.requirements|length }}</td></tr>
<tr><th>Runs</th><td>{{ doc.runs|length }}</td></tr>
</table>
<p>Each requirement is a defect or behaviour that was captured and is enforced by named tests.
Evidence is re-verified against its checksum, bound to the run and gate that produced it,
when this report is made. A run that verified nothing is marked VACUOUS.</p>
</section>

<h2>Requirements</h2>
{% if not doc.requirements %}<p>No requirements in the ledger.</p>{% endif %}
{% for r in doc.requirements %}
<h3>{{ r.id }}: {{ r.title }}
<span class="tag {{ {'satisfied':'satisfied','open':'open','waived':'waived','waiver expired':'expired'}.get(r.state, '') }}">{{ r.state|upper }}</span></h3>
<table>
<tr><th>Source</th><td>{{ r.source }}{% if r.source_issue %} ({{ r.source_issue }}){% endif %}</td></tr>
<tr><th>Severity</th><td>{{ r.severity }}</td></tr>
<tr><th>Scope</th><td>{% for k, v in r.scope.items() if v %}{{ k }}: {{ v|join(", ") }}<br>{% else %}none{% endfor %}</td></tr>
<tr><th>Obligations</th><td>{% for o in r.obligations %}{{ o.gate }}: {{ o.status }}{% if not loop.last %}, {% endif %}{% endfor %}</td></tr>
{% if r.waiver %}<tr><th>Waiver</th><td>{% if r.waiver.expired %}<span class="tag expired">WAIVER EXPIRED</span> {% endif %}{{ r.waiver.reason }}
 · approved by {{ r.waiver.approved_by or "unknown" }}{% if r.waiver.waived_at %} on {{ r.waiver.waived_at }}{% endif %}
{% if r.waiver.expires %} · expires {{ r.waiver.expires }}{% endif %}</td></tr>{% endif %}
</table>
{% if r.evidence %}
<table><tr><th>Gate</th><th>Result</th><th>Checksum</th><th>Run</th><th>Recorded</th></tr>
{% for e in r.evidence %}<tr>
<td>{{ e.gate }}</td>
<td>{% if not e.verified %}<span class="tag fail">FAILS VERIFICATION</span>{% else %}{{ e.status|upper }}{% endif %}</td>
<td><code>{{ e.artifact_checksum }}</code></td><td><code>{{ e.run_id }}</code></td><td>{{ e.timestamp }}</td>
</tr>{% endfor %}</table>
{% else %}<p>No evidence recorded.</p>{% endif %}
{% endfor %}

<h2>Run history</h2>
{% if not doc.runs %}<p>No runs recorded.</p>{% else %}
<table><tr><th>Started</th><th>Result</th><th>Duration</th><th>Run</th></tr>
{% for run in doc.runs %}<tr>
<td>{{ run.started_at }}</td>
<td>{% if run.vacuous %}<span class="tag vacuous">VACUOUS</span> passed with nothing verified{% elif run.passed %}PASSED{% else %}<span class="tag fail">FAILED</span>{% endif %}</td>
<td>{{ "%d ms"|format(run.duration_ms) if run.duration_ms is not none else "—" }}</td><td><code>{{ run.run_id }}</code></td>
</tr>{% endfor %}</table>{% endif %}

<h2>Merge overrides</h2>
{% if not doc.merge_overrides %}<p>No merge overrides recorded.</p>{% else %}
<table><tr><th></th><th>PR</th><th>By</th><th>When</th><th>Reason</th><th>Requirements bypassed</th></tr>
{% for o in doc.merge_overrides %}<tr>
<td><span class="tag fail">MERGE OVERRIDE</span></td><td>#{{ o.pr_number }}</td><td>{{ o.actor }}</td>
<td>{{ o.overridden_at }}</td><td>{{ o.reason }}</td>
<td>{% for b in o.bypassed %}{{ b.id }} {{ b.title }}{% if not loop.last %}; {% endif %}{% endfor %}</td>
</tr>{% endfor %}</table>{% endif %}
</body></html>
"""


def render_html(doc: dict) -> str:
    """The report as one self-contained page (no external resources)."""
    return Environment(autoescape=True).from_string(_TEMPLATE).render(doc=doc)


def render_pdf(html: str, out: Path) -> None:
    """Print ``html`` to ``out`` with a headless Chrome or Chromium."""
    browser = next((path for name in _BROWSERS if (path := shutil.which(name))), None)
    if browser is None:
        raise RuntimeError(
            "PDF export prints the HTML report with Chrome or Chromium, and none was found "
            "on PATH. Use --format html and print it from any browser."
        )
    # A stale file must not pass for a print that failed.
    Path(out).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        ran = subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={Path(tmp) / 'profile'}",
             f"--print-to-pdf={Path(out).resolve()}", page.as_uri()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    if ran.returncode != 0 or not Path(out).exists():
        raise RuntimeError(f"{browser} could not print the report: {ran.stderr.strip()[-500:]}")
