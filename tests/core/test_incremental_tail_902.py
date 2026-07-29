"""``atail_run_output`` reads incrementally from a saved offset (#902 / P0.8).

It used to call ``readlines()`` on the whole file every poll — twice a second,
per connected client — so a multi-MB agent log burned O(size) CPU and IO per
tick on the event loop for every open tab.

The tests assert *how much is read*, not just what is yielded: a correct-output
assertion passes on the full-reread version too.
"""

import asyncio

import pytest

from codeframe.core.streaming import atail_run_output, get_run_output_path

pytestmark = pytest.mark.v2

RUN_ID = "run-902"


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    return create_or_load_workspace(ws_path)


@pytest.fixture
def log(workspace):
    path = get_run_output_path(workspace, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


async def _collect(workspace, *, since_line=0, max_wait=0.35, poll=0.05):
    return [
        line
        async for line in atail_run_output(
            workspace, RUN_ID, since_line=since_line,
            poll_interval=poll, max_wait=max_wait,
        )
    ]


class TestIncrementalReads:
    async def test_only_new_bytes_are_read_after_the_first_poll(
        self, workspace, log, monkeypatch
    ):
        """The point of the fix: bytes read per poll must not scale with file size.

        Measured by shadowing ``open`` in the streaming module only (Python
        resolves the name through module globals before builtins), so nothing
        else in the process is affected.
        """
        import builtins

        from codeframe.core import streaming as streaming_mod

        log.write_text("".join(f"line {i}\n" for i in range(500)))
        assert log.stat().st_size > 4000

        reads: list[int] = []
        real_open = builtins.open

        def tracking_open(path, *args, **kwargs):
            handle = real_open(path, *args, **kwargs)
            if str(path) != str(log):
                return handle

            class _Tracked:
                def __enter__(self_inner):
                    handle.__enter__()
                    return self_inner

                def __exit__(self_inner, *exc):
                    return handle.__exit__(*exc)

                def read(self_inner, *a, **kw):
                    data = handle.read(*a, **kw)
                    reads.append(len(data))
                    return data

                def __getattr__(self_inner, name):
                    return getattr(handle, name)

            return _Tracked()

        monkeypatch.setattr(streaming_mod, "open", tracking_open, raising=False)

        async def _appender():
            for i in range(3):
                await asyncio.sleep(0.08)
                with real_open(log, "a") as f:
                    f.write(f"appended {i}\n")

        appender = asyncio.create_task(_appender())
        lines = await _collect(workspace, max_wait=0.5, poll=0.05)
        await appender

        assert any(line.startswith("appended") for line in lines)
        assert reads, "the tailer never read the log"
        # First poll drains the backlog; every later read is only the append.
        assert reads[0] > 4000
        assert all(n < 200 for n in reads[1:]), (
            f"log re-read in full after the first poll: {reads}"
        )

    async def test_yields_appended_lines(self, workspace, log):
        log.write_text("a\nb\n")

        async def _appender():
            await asyncio.sleep(0.1)
            with log.open("a") as f:
                f.write("c\n")

        appender = asyncio.create_task(_appender())
        lines = await _collect(workspace, max_wait=0.35)
        await appender

        assert lines == ["a\n", "b\n", "c\n"]

    async def test_since_line_skips_the_backlog(self, workspace, log):
        log.write_text("a\nb\nc\n")

        lines = await _collect(workspace, since_line=2, max_wait=0.2)

        assert lines == ["c\n"]

    async def test_a_partial_line_is_held_until_its_newline_arrives(
        self, workspace, log
    ):
        """The old version could yield a half-written line and then never emit
        its remainder, because the line count had already advanced."""
        log.write_text("complete\npar")

        async def _finisher():
            await asyncio.sleep(0.1)
            with log.open("a") as f:
                f.write("tial\n")

        finisher = asyncio.create_task(_finisher())
        lines = await _collect(workspace, max_wait=0.35)
        await finisher

        assert lines == ["complete\n", "partial\n"]

    async def test_final_unterminated_line_is_flushed_at_close(self, workspace, log):
        log.write_text("done\nno trailing newline")

        lines = await _collect(workspace, max_wait=0.15)

        assert lines == ["done\n", "no trailing newline"]

    async def test_truncation_restarts_rather_than_stalling(self, workspace, log):
        """A rotated/truncated log must not leave the reader seeking past EOF."""
        log.write_text("old line 1\nold line 2\n")

        async def _truncate():
            await asyncio.sleep(0.12)
            log.write_text("fresh\n")

        truncator = asyncio.create_task(_truncate())
        lines = await _collect(workspace, max_wait=0.4)
        await truncator

        assert "fresh\n" in lines

    async def test_missing_file_is_not_an_error(self, workspace):
        lines = await _collect(workspace, max_wait=0.15)
        assert lines == []
