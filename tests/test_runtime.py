from concurrent.futures import Future
from types import SimpleNamespace

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


def test_auto_requires_sustained_pressure_and_obeys_cooldown_and_off_switch(runtime, monkeypatch):
    runtime.settings.update(auto=True, cloud=True)
    runtime.provider = SimpleNamespace(configured=True)
    runtime.latest = {"used_percent": 90}
    calls = []
    monkeypatch.setattr(runtime, "_optimize", lambda now, automatic: calls.append((now, automatic)))
    runtime._automatic(200)
    runtime._automatic(219)
    assert calls == []
    runtime._automatic(220)
    runtime._automatic(221)
    assert calls == [(220, True)]
    runtime.settings["auto"] = False
    runtime._automatic(400)
    assert calls == [(220, True)]
    runtime.settings["auto"] = True
    runtime.latest = {"used_percent": 40}
    runtime._automatic(500)
    assert runtime.pressure_since is None
    runtime.latest = {"used_percent": 90}
    runtime._automatic(600)
    runtime._automatic(620)
    assert calls == [(220, True), (620, True)]


def test_manual_round_reaches_judgment_and_execution_without_persisting_auto_permission(runtime, monkeypatch):
    runtime.settings.update(cloud=False, auto=False, memory=False)
    runtime.store.put("cloud", False)
    target = item()
    runtime.items[target.id] = target
    calls, executions = [], []

    def judge(items, now, memories, context):
        calls.append((items, memories, context))
        return {target.id: Judgment("unrelated", "defer", "discard_tab", 0.99, "jev")}, {}

    runtime.provider = SimpleNamespace(configured=True, judge=judge)
    monkeypatch.setattr(runtime, "_execute", lambda obj, now, explicit: executions.append(obj.id))
    runtime.paused = True
    runtime.submit("optimize", context="手动整理", allow_summary_once=True)
    runtime.submit("optimize", context="手动整理", allow_summary_once=True)
    runtime._commands(100)
    assert not runtime.paused
    assert runtime.future is not None
    runtime.future.result(timeout=2)
    runtime._network_result(100)
    runtime._advance_plan(100)
    assert len(calls) == 1 and calls[0][2] == "手动整理"
    assert executions == [target.id]
    assert not runtime.settings["cloud"] and not runtime.settings["auto"]
    assert runtime.store.get("cloud") is False
    runtime._optimize(101, automatic=False)
    assert runtime.future is None and len(calls) == 1


@pytest.mark.parametrize(
    ("automatic", "allow_once", "configured"),
    [(False, False, True), (True, True, True), (False, True, False)],
)
def test_one_round_permission_never_grants_unrequested_or_automatic_uploads(
    runtime, automatic, allow_once, configured
):
    runtime.settings.update(cloud=False)
    runtime.provider = SimpleNamespace(configured=configured)
    runtime.items = {"a": item()}
    runtime._optimize(100, automatic=automatic, allow_summary_once=allow_once)
    assert runtime.future is None and not runtime.settings["cloud"]
