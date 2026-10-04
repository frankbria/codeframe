"""No public IP address is committed in docs or deploy config (#1304).

A legacy nginx doc carried the live VPS address for months. Private,
loopback and documentation ranges are fine; a routable address is not.
"""

import ipaddress
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ["*.md", "*.sh", "*.yml", "*.yaml", "*.example", "*.conf", "Caddyfile*"]
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


def test_no_routable_ipv4_in_tracked_docs_or_config():
    files = subprocess.run(
        ["git", "ls-files", *PATTERNS], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    found = []
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        for match in IPV4.finditer(text):
            try:
                if ipaddress.ip_address(match.group(1)).is_global:
                    found.append(f"{name}: {match.group(1)}")
            except ValueError:
                continue
    assert not found, found
