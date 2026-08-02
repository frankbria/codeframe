"""Chat replay must load the NEWEST messages, not the oldest (#929).

`_load_history` called `get_messages(session_id)` with no limit; the repository
default is `ORDER BY created_at LIMIT 100`. Past 100 persisted messages every
turn replayed the *first* 100 — ancient context — and the model never saw the
conversation the user was actually having.
"""

import pytest

from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def repo():
    db = Database(":memory:")
    db.initialize()
    return db.interactive_sessions


def _seed(repo, count: int) -> str:
    session = repo.create(workspace_path="/tmp/ws-history")
    for i in range(count):
        repo.add_message(
            session["id"],
            role="user" if i % 2 == 0 else "assistant",
            content=f"msg {i:04d}",
        )
    return session["id"]


class TestGetRecentMessages:
    def test_returns_the_newest_window_in_chronological_order(self, repo):
        session_id = _seed(repo, 150)

        rows = repo.get_recent_messages(session_id, limit=100)

        assert len(rows) == 100
        assert rows[0]["content"] == "msg 0050"
        assert rows[-1]["content"] == "msg 0149"

    def test_returns_everything_when_under_the_limit(self, repo):
        session_id = _seed(repo, 5)

        rows = repo.get_recent_messages(session_id, limit=100)

        assert [r["content"] for r in rows] == [f"msg {i:04d}" for i in range(5)]

    def test_metadata_is_decoded_like_get_messages(self, repo):
        session = repo.create(workspace_path="/tmp/ws-meta")
        repo.add_message(
            session["id"], role="assistant", content="hi", metadata={"model": "m1"}
        )

        rows = repo.get_recent_messages(session["id"], limit=10)

        assert rows[0]["metadata"] == {"model": "m1"}

    def test_get_messages_still_pages_oldest_first(self, repo):
        """The REST transcript endpoint pages on ascending order — unchanged."""
        session_id = _seed(repo, 5)

        page1 = repo.get_messages(session_id, limit=3, offset=0)
        page2 = repo.get_messages(session_id, limit=3, offset=3)

        assert [r["content"] for r in page1] == ["msg 0000", "msg 0001", "msg 0002"]
        assert [r["content"] for r in page2] == ["msg 0003", "msg 0004"]


class TestLoadHistoryUsesRecentMessages:
    def test_latest_turn_is_present_past_the_limit(self, repo):
        """With >100 persisted messages the current turn must survive replay."""
        from codeframe.core.adapters.streaming_chat import StreamingChatAdapter

        session_id = _seed(repo, 150)

        adapter = StreamingChatAdapter.__new__(StreamingChatAdapter)
        adapter._session_id = session_id
        adapter._db_repo = repo

        history = adapter._load_history()

        contents = [m["content"] for m in history]
        assert "msg 0149" in contents, "replay dropped the most recent message"
        assert "msg 0000" not in contents, "replay is still anchored to the oldest rows"
        assert contents == sorted(contents), "history must stay chronological"

    def test_display_only_roles_are_still_dropped(self, repo):
        """The #765 role collapsing must survive the query change."""
        from codeframe.core.adapters.streaming_chat import StreamingChatAdapter

        session = repo.create(workspace_path="/tmp/ws-roles")
        repo.add_message(session["id"], role="user", content="q")
        repo.add_message(session["id"], role="thinking", content="hmm")
        repo.add_message(session["id"], role="error", content="boom")
        repo.add_message(session["id"], role="tool_result", content="out")

        adapter = StreamingChatAdapter.__new__(StreamingChatAdapter)
        adapter._session_id = session["id"]
        adapter._db_repo = repo

        history = adapter._load_history()

        assert [m["role"] for m in history] == ["user", "assistant", "user"]
        assert all(m["content"] != "boom" for m in history)
