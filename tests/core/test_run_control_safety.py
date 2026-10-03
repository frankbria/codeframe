"""`terminate_tree` must never signal a group it has not proven is ours (#1279).

A bare `MagicMock()` handed to `terminate_tree` coerced its `pid` to 1, and
`os.killpg(1, sig)` is `kill(-1, sig)`: every process the user owns. Running the
#1279 tests killed every terminal and agent session on the machine that way.

Every test here replaces `os.killpg` and `os.kill` with recording stubs, so a
broken guard records a call instead of sending a signal. The real-signal kill
paths are covered by test_stop_does_stop_1279.py, with real children.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from codeframe.core import run_control

pytestmark = [
    pytest.mark.v2,
    pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX"),
    pytest.mark.timeout(30),
]

_real_kill = os.kill


@pytest.fixture
def signals(monkeypatch):
    """Record every killpg/kill instead of sending it."""
    sent: list[tuple[str, object, int]] = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append(("killpg", pgid, sig)))
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append(("kill", pid, sig)))
    return sent


def _fake(pid):
    return SimpleNamespace(
        pid=pid, returncode=None, poll=lambda: None, wait=lambda timeout=None: 0,
        terminate=lambda: None, kill=lambda: None,
    )


class TestNothingUnprovenIsSignalled:
    def test_a_mock_process(self, signals):
        run_control.terminate_tree(MagicMock(), grace_s=0.1)
        assert signals == []

    @pytest.mark.parametrize("pid", [0, 1, -1, None, True])
    def test_a_pid_that_is_not_a_child_we_can_name(self, signals, pid):
        run_control.terminate_tree(_fake(pid), grace_s=0.1)
        assert signals == []

    def test_our_own_process_group(self, signals):
        """`killpg(getpgrp())` would take down the caller and everything with it."""
        run_control.terminate_tree(_fake(os.getpgrp()), grace_s=0.1)
        assert not [s for s in signals if s[0] == "killpg"]

    def test_a_process_that_is_not_our_child(self, signals):
        run_control.terminate_tree(_fake(os.getppid()), grace_s=0.1)
        assert signals == []

    def test_a_child_that_does_not_lead_its_own_group(self, signals):
        """Started without new_session_kwargs(), its group is ours."""
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            assert os.getpgid(child.pid) == os.getpgrp()
            run_control.terminate_tree(child, grace_s=0.1)
            assert not [s for s in signals if s[0] == "killpg"], "signalled our own group"
            # Falling back to the direct child alone is fine: it is ours and unreaped.
            assert all(target == child.pid for _, target, _ in signals)
        finally:
            _real_kill(child.pid, 9)
            child.wait()

    def test_a_group_leader_that_is_not_our_child(self, signals):
        """A grandchild in its own session leads a group, but it is not ours to
        verify: its pid could be recycled without us ever knowing."""
        parent = subprocess.Popen(
            [sys.executable, "-c",
             "import subprocess,sys,time;"
             "c=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
             "start_new_session=True);print(c.pid,flush=True);time.sleep(30)"],
            stdout=subprocess.PIPE, text=True,
        )
        grandchild = int(parent.stdout.readline())
        try:
            assert os.getpgid(grandchild) == grandchild  # a leader, just not our child
            run_control.terminate_tree(_fake(grandchild), grace_s=0.1)
            assert signals == []
        finally:
            _real_kill(grandchild, 9)
            _real_kill(parent.pid, 9)
            parent.wait()

    def test_a_child_inside_another_childs_group(self, signals):
        """Ours and unreaped, in a group that is not ours, but it does not lead
        that group, so signalling 'its' group would hit its leader's."""
        # Its own group in our session: setpgid cannot join a group across sessions.
        leader = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"], process_group=0
        )
        member = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"], process_group=leader.pid
        )
        try:
            assert os.getpgid(member.pid) == leader.pid != member.pid
            run_control.terminate_tree(member, grace_s=0.1)
            assert not [s for s in signals if s[0] == "killpg"]
        finally:
            for p in (member, leader):
                _real_kill(p.pid, 9)
                p.wait()

    def test_a_child_that_was_already_reaped(self, signals):
        """Its pid may already belong to a stranger; nothing may be sent."""
        child = subprocess.Popen(
            [sys.executable, "-c", "pass"], **run_control.new_session_kwargs()
        )
        child.wait()
        run_control.terminate_tree(child, grace_s=0.1)
        assert signals == []


class TestAVerifiedGroupIsStillSignalled:
    def test_a_live_group_leader_gets_term_then_kill_on_its_own_pgid(self, signals):
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            **run_control.new_session_kwargs(),
        )
        try:
            run_control.terminate_tree(child, grace_s=0.2)
            assert signals, "a verified group was not signalled at all"
            assert {target for _, target, _ in signals} == {child.pid}
            assert all(kind == "killpg" for kind, _, _ in signals)
        finally:
            _real_kill(child.pid, 9)
            child.wait()
