#!/usr/bin/env python3
"""Drive `cf prd generate` the way an attentive human would.

The #614 walkthrough has to answer one question: can a real user get through the
quickstart in 15 minutes? A fixed list of canned answers cannot tell us that —
the discovery loop asks AI-generated, sometimes multi-part questions, and one
rejection puts a canned list permanently out of sync with the questions.

So this reads each question as it appears and answers *that* question, from a
fixed project brief, using the same API key the walkthrough already needs. It is
a stand-in for an attentive user, not a way to make the step pass: every turn,
every rejection and the wall-clock cost are logged so the transcript shows what
a real person would have had to do.

Stdlib + the `anthropic` package that CodeFRAME already depends on.
"""

from __future__ import annotations

import os
import re
import selectors
import subprocess
import sys
import time

BRIEF = """\
I am building a small REST API for managing a personal todo list.

- Problem: I keep my todos in scattered notes and lose track of what is due; I
  want one self-hosted place to track them, and I got fed up enough with the
  scattered notes to finally build it.
- Users: individual developers and small teams who want a simple self-hosted
  todo backend and do not want another SaaS account.
- Features: create, read, update, delete a todo; filter by completed status.
  A todo has a title, optional description, priority (high/medium/low) and a
  completed flag.
- Stack: FastAPI, SQLite via SQLAlchemy, pytest for tests.
- Success: all CRUD and filter endpoints work and are covered by passing tests.
- Out of scope for the MVP: auth, multi-user accounts, sharing, reminders, web UI.
- Constraints: single uvicorn process on a laptop or small VPS; list of 1000
  todos returns in under 200ms; one JSON error shape for every failure.
- Timeline: first milestone is create + list working end to end with tests.
"""

SYSTEM = """\
You are role-playing a software developer being interviewed by an AI product
manager about a project you want to build. You will be shown one interview
question at a time.

Answer ONLY the question asked, directly and concretely, in 2-4 sentences,
grounded in the project brief. If the question has multiple parts, answer EVERY
part explicitly — a partial answer will be rejected. Never ask a question back.
Never mention that you are an AI or that this is a simulation. Output only the
answer text, no preamble and no markdown.
"""

PROMPT_MARKER = "Your answer"
MAX_TURNS = int(os.environ.get("RESPONDER_MAX_TURNS", "40"))
IDLE_FLUSH = 1.0  # seconds of silence before deciding the prompt is complete


def strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)


def latest_question(buf: str) -> str:
    """Pull the most recent question out of the Rich panel, best-effort."""
    text = strip_ansi(buf)
    # Rich draws the panel with box characters; take the lines inside the last
    # panel titled "Question".
    chunks = text.split("Question ")
    if len(chunks) < 2:
        return text[-600:]
    tail = chunks[-1]
    lines = []
    for raw in tail.splitlines():
        line = raw.strip().strip("│").strip()
        line = line.strip("─╭╮╰╯ ")
        if not line or line.startswith("Coverage") or set(line) <= {"░", "█"}:
            continue
        if line.startswith(PROMPT_MARKER):
            break
        lines.append(line)
    return " ".join(lines)[-1200:] or text[-600:]


def main() -> int:
    from anthropic import Anthropic

    client = Anthropic()
    model = os.environ.get("RESPONDER_MODEL", "claude-haiku-4-5")

    cmd = sys.argv[1:] or ["cf", "prd", "generate"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        env={**os.environ, "TERM": "dumb", "COLUMNS": "100"},
    )
    assert proc.stdout and proc.stdin

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    buf = ""          # everything seen since the last answer we sent
    turns = 0
    rejections = 0
    started = time.time()

    while True:
        if proc.poll() is not None:
            break
        events = sel.select(timeout=IDLE_FLUSH)
        if events:
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            text = chunk.decode("utf-8", "replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            buf += text
            continue

        # Idle. If the tail is an outstanding answer prompt, respond to it.
        if PROMPT_MARKER not in strip_ansi(buf):
            continue

        if turns >= MAX_TURNS:
            print(
                f"\n[responder] giving up after {MAX_TURNS} turns "
                f"({rejections} rejections) — the discovery loop never completed",
                flush=True,
            )
            proc.kill()
            return 3

        if "not accepted" in buf or "Let me ask differently" in buf:
            rejections += 1

        question = latest_question(buf)
        turns += 1
        print(f"\n[responder] turn {turns}: answering -> {question[:110]!r}", flush=True)

        try:
            resp = client.messages.create(
                model=model,
                max_tokens=350,
                system=SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"PROJECT BRIEF:\n{BRIEF}\n\n"
                            f"INTERVIEW QUESTION:\n{question}\n\n"
                            "Your answer:"
                        ),
                    }
                ],
            )
            answer = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001 - surface, do not mask
            print(f"\n[responder] LLM call failed: {exc}", flush=True)
            proc.kill()
            return 4

        answer = " ".join(answer.split()) or "Yes, that is correct."
        print(f"[responder] -> {answer[:160]}", flush=True)
        try:
            proc.stdin.write((answer + "\n").encode())
            proc.stdin.flush()
        except BrokenPipeError:
            break
        buf = ""

    rc = proc.wait()
    print(
        f"\n[responder] finished: exit={rc} turns={turns} rejections={rejections} "
        f"elapsed={time.time() - started:.0f}s",
        flush=True,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
