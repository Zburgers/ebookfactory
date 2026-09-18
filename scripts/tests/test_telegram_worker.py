import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("telegram_worker", Path(__file__).parents[1] / "telegram-worker.py")
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(worker)


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self):
        self.sessions = []

    def session(self):
        session = FakeSession()
        self.sessions.append(session)
        return session


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))
        return "telegram-1"

    def get_updates(self, *, offset, timeout):
        return []


def test_poll_once_uses_durable_offset_and_drains_outbox(monkeypatch):
    database = FakeDatabase()
    bot = FakeBot()
    updates = [{"update_id": 42, "message": {"chat": {"id": 7}, "from": {"id": 8}, "text": "hello"}}]
    observed = {}

    monkeypatch.setattr(worker, "get_next_update_id", lambda session: 41)
    monkeypatch.setattr(worker, "process_update", lambda session, config, update: observed.setdefault("update", update))
    monkeypatch.setattr(worker, "claim_outbox", lambda session: observed.setdefault("claimed", type("Delivery", (), {"outbox_id": "out-1", "chat_id": 7, "text": "reply"})()))
    monkeypatch.setattr(worker, "record_outbox_sent", lambda session, outbox_id, message_id: observed.setdefault("sent", (outbox_id, message_id)))
    monkeypatch.setattr(bot, "get_updates", lambda offset, timeout: updates if offset == 41 else [])

    worker.poll_once(database, bot, worker.TelegramConfig(False, frozenset(), frozenset()), timeout=1)

    assert observed["update"]["update_id"] == 42
    assert observed["sent"] == ("out-1", "telegram-1")
    assert all(session.closed for session in database.sessions)
