from dataclasses import replace

import pytest

from jev_cache.core import CandidateGenerator, Ghost, Item, Judgment, MemoryWindow, UsageTracker, plan_batch


def item(key="a", **kwargs):
    base = Item(
        key,
        key,
        key,
        "tab",
        100,
        "v1",
        allowed_action="discard_tab",
        auto_eligible=True,
        last_used=50,
        frequency=1,
        reopen_cost=1,
    )
    return replace(base, **kwargs)


def test_four_sources_include_recent_finished_and_deduplicate():
    objects = [item(str(i), last_used=i, frequency=i + 1) for i in range(12)]
    objects += [
        item("recent-done", last_used=99, frequency=900, activity_ended=True),
        item("large", last_used=95, frequency=800, memory_bytes=10**9),
    ]
    batch = CandidateGenerator().generate(objects, 100, set(), set())
    ids = [i.id for i in batch.items]
    assert "recent-done" in ids and "large" in ids
    assert len(ids) <= 8 and len(ids) == len(set(ids))
    assert batch.omitted


@pytest.mark.parametrize(
    "change",
    [
        {"active": True},
        {"protections": ("editing",)},
        {"auto_eligible": False},
        {"observed_at": 70},
        {"observed_at": 101},
    ],
)
def test_protected_and_stale_items_never_become_candidates(change):
    assert not CandidateGenerator().generate([item(**change)], 100, set(), set()).items


def test_kept_and_cooldown_override_all_model_outputs():
    target = item()
    judgments = {"a": Judgment("unrelated", "done", "discard_tab", 1.0, "jev")}
    assert not plan_batch([target], judgments, 100, {"a"}, set())
    assert not plan_batch([target], judgments, 100, set(), {"a"})


@pytest.mark.parametrize(
    "judgment",
    [
        Judgment("current", "done", "discard_tab", 1, "jev"),
        Judgment("unrelated", "soon", "discard_tab", 1, "jev"),
        Judgment("unrelated", "done", "manual_only", 1, "jev"),
        Judgment("unrelated", "done", "request_exit", 1, "jev"),
        Judgment("unrelated", "done", "discard_tab", 1, "basic"),
        Judgment("unrelated", "done", "discard_tab", float("nan"), "jev"),
    ],
)
def test_conflicting_or_untrusted_judgments_do_not_execute(judgment):
    assert not plan_batch([item()], {"a": judgment}, 100, set(), set())


def test_known_cost_is_preferred_and_semantic_done_takes_priority():
    targets = [
        item("unknown", reopen_cost=None, memory_bytes=10**9),
        item("small", memory_bytes=1024),
        item("defer", memory_bytes=10**10),
    ]
    judgments = {
        i.id: Judgment("unrelated", "defer" if i.id == "defer" else "done", "discard_tab", 0.95, "jev")
        for i in targets
    }
    assert [i.id for i in plan_batch(targets, judgments, 100, set(), set())] == ["small", "unknown", "defer"]


def test_usage_deduplicates_decays_and_does_not_count_continuous_activity():
    tracker = UsageTracker(half_life=100, merge_seconds=10)
    assert tracker.observe("a", "event", 100, "user")
    assert not tracker.observe("a", "event", 101, "user")
    assert not tracker.observe("a", "auto", 150, "automatic")
    tracker.touch("a", 200)
    last, score = tracker.get("a", 200)
    assert last == 200 and score == pytest.approx(0.5)
    assert tracker.get("unseen", 200) == (None, None)


def test_ghost_requires_exact_identity_and_classifies_interruption():
    ghost = Ghost("action", "tab:a:1:4", "site", 100, 400)
    assert not ghost.revisit("event", "tab:a:1:5", "user", 102)
    ghost.tick(102, True)
    ghost.tick(130, True)
    ghost.tick(400, False)
    assert ghost.interrupted and ghost.outcome == "incomplete"


def test_ghost_auto_restart_is_not_user_preference_and_deduplicates():
    ghost = Ghost("action", "target", "stable", 100, 400)
    assert ghost.revisit("event", "target", "automatic", 101)
    assert ghost.outcome == "auto_restarted"
    assert not ghost.revisit("event", "target", "automatic", 102)


def test_measurements_preserve_negative_changes_and_reject_missing_windows():
    window = MemoryWindow()
    for t in range(90, 100, 2):
        window.append(t, 1000)
    assert not window.measure(100, 102)["valid"]
    for t in range(108, 124, 2):
        window.append(t, 800)
    assert window.measure(100, 102)["delta_bytes"] == -200
    assert not window.measure(100, 102, concurrent=True)["valid"]


def test_rotation_eventually_exposes_non_top_candidates():
    generator = CandidateGenerator()
    objects = [item(str(i), last_used=i, frequency=i) for i in range(20)]
    seen = set()
    for _ in range(40):
        seen.update(i.id for i in generator.generate(objects, 100, set(), set()).items)
    assert seen == {i.id for i in objects}
