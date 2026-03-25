from app.services.zep_graph_memory_updater import AgentActivity, ZepGraphMemoryUpdater


class _FakeGraphiti:
    def add_episode(self, **kwargs):
        return object()


class _FakeLoop:
    def __init__(self, error):
        self.error = error

    def is_closed(self):
        return False

    def run_until_complete(self, _):
        raise self.error


def _sample_activity():
    return AgentActivity(
        platform="twitter",
        agent_id=1,
        agent_name="Alice",
        action_type="CREATE_POST",
        action_args={"content": "Hello world"},
        round_num=1,
        timestamp="2026-03-25T00:00:00",
    )


def test_send_batch_stops_updater_on_fatal_shutdown_error():
    updater = ZepGraphMemoryUpdater("graph_test")
    updater._running = True
    updater._graphiti = _FakeGraphiti()
    updater._loop = _FakeLoop(RuntimeError("cannot schedule new futures after shutdown"))

    updater._send_batch_activities([_sample_activity()], "twitter")

    assert updater._running is False
    assert updater._graphiti is None


def test_send_batch_retries_nonfatal_errors(monkeypatch):
    updater = ZepGraphMemoryUpdater("graph_test")
    updater._running = True
    updater._graphiti = _FakeGraphiti()
    updater._loop = _FakeLoop(RuntimeError("Connection error."))
    monkeypatch.setattr("app.services.zep_graph_memory_updater.time.sleep", lambda _: None)

    updater._send_batch_activities([_sample_activity()], "twitter")

    assert updater._running is True
    assert updater._failed_count == 1
