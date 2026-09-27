from concurrent.futures import Future

import pytest
from test_policy import item

from jev_cache.core import CandidateBatch, Judgment
from jev_cache.runtime import Runtime
from jev_cache.storage import Store


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("JEVCACHE_DATA_DIR", str(tmp_path))
    worker = Runtime()
    worker.store = Store(tmp_path / "state.db")
    worker.kept = set()
    worker.keep_names = {}
    worker.settings = {"memory": True}
    yield worker
    worker.stop()
    worker.pool.shutdown(wait=True)
    worker.store.close()


def complete_judgment(runtime, target):
    runtime.future = Future()
    runtime.future.set_result(({target.id: Judgment("unrelated", "defer", "discard_tab", 0.99, "jev")}, {}))
    runtime.future_kind = "judge"
    runtime.future_epoch = runtime.epoch
    runtime.future_batch = CandidateBatch([target], {}, {})
    runtime.plan_deadline = 120
    runtime.items[target.id] = target


def test_user_keep_during_request_invalidates_completed_model_answer(runtime):
    target = item()
    complete_judgment(runtime, target)
    runtime.submit("keep", item_id=target.id)
    runtime._commands(101)
    runtime._network_result(102)
    assert target.stable_key in runtime.kept
    assert not runtime.plan and not runtime.pending


def test_changed_navigation_rejects_old_judgment(runtime):
    target = item()
    complete_judgment(runtime, target)
    runtime.items.clear()
    runtime._network_result(102)
    assert not runtime.plan and not runtime.pending


def test_forgetting_while_action_is_pending_does_not_recreate_history(runtime):
    runtime.store.receipt("old", {"id": "old", "status": "requested"})
    runtime.pending["old"] = {"body": {"id": "old"}, "item": item()}
    runtime.submit("forget")
    runtime._commands(100)
    runtime._browser_event({"type": "receipt", "action_id": "old", "status": "completed"}, 101)
    assert runtime.store.recent() == []
    assert not runtime.pending and not runtime.ghosts
