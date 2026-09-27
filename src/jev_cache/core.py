"""Deterministic policy; no Qt, network, storage, or operating-system actions."""

from __future__ import annotations

import math
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from statistics import median

POLICY_VERSION = "cache-0.1"
MIB = 1024 * 1024


@dataclass(frozen=True)
class Item:
    id: str
    stable_key: str
    name: str
    kind: str
    observed_at: float
    version: str
    memory_bytes: int | None = None
    active: bool = False
    protections: tuple[str, ...] = ()
    allowed_action: str = "none"
    auto_eligible: bool = False
    last_used: float | None = None
    frequency: float | None = None
    activity_ended: bool = False
    reopen_cost: int | None = None
    pid: int = 0
    created: float = 0.0
    hwnd: int = 0
    tab_id: int = -1
    browser_session: str = ""
    navigation: int = 0
    details: str = ""
    semantic_hint: str = ""

    def eligible(self, now: float, kept: set[str], cooldown: set[str]) -> bool:
        return (
            not self.active
            and not self.protections
            and self.auto_eligible
            and self.allowed_action in {"discard_tab", "request_exit"}
            and self.stable_key not in kept | cooldown
            and 0 <= now - self.observed_at <= 15
        )

    def model_state(self, now: float, alias: str) -> dict:
        # Do not upload PID, executable paths, raw titles, URLs, HWND, or exact identities.
        return {
            "id": alias,
            "kind": self.kind,
            "seconds_since_use": None if self.last_used is None else round(max(0, now - self.last_used)),
            "decayed_frequency": self.frequency,
            "activity_ended_observed": self.activity_ended,
            "allowed_action": self.allowed_action,
            "reopen_cost": self.reopen_cost,
            "state_verified": self.auto_eligible,
            "user_permitted_title_summary": self.semantic_hint,
        }


@dataclass(frozen=True)
class Judgment:
    relation: str = "unknown"
    retention: str = "unknown"
    action: str = "unknown"
    confidence: float = 0.0
    source: str = "basic"


@dataclass
class CandidateBatch:
    items: list[Item]
    sources: dict[str, list[str]]
    omitted: dict[str, str]


class CandidateGenerator:
    def __init__(self):
        self.rotation = 0

    def generate(self, items: list[Item], now: float, kept: set[str], cooldown: set[str]) -> CandidateBatch:
        eligible = [i for i in items if i.eligible(now, kept, cooldown)]
        streams = {
            "recency": sorted(
                (i for i in eligible if i.last_used is not None), key=lambda i: (i.last_used, i.id)
            ),
            "frequency": sorted(
                (i for i in eligible if i.frequency is not None), key=lambda i: (i.frequency, i.id)
            ),
            "memory": sorted(
                (i for i in eligible if i.memory_bytes is not None), key=lambda i: (-i.memory_bytes, i.id)
            ),
            "ended": sorted((i for i in eligible if i.activity_ended), key=lambda i: i.id),
        }
        # Rotate equal-priority batches across rounds; avoid starving one source.
        names = list(streams)
        names = names[self.rotation % 4 :] + names[: self.rotation % 4]
        all_sources: dict[str, list[str]] = {}
        queues = {}
        for name in names:
            values = streams[name]
            for item in values:
                all_sources.setdefault(item.id, []).append(name)
            offset = (self.rotation // 4 * 2) % len(values) if values else 0
            queues[name] = deque(values[offset:] + values[:offset])
        selected: dict[str, Item] = {}
        for _ in range(2):
            for name in names:
                if queues[name]:
                    item = queues[name].popleft()
                    selected[item.id] = item
        while len(selected) < 8 and any(queues.values()):
            for name in names:
                if queues[name] and len(selected) < 8:
                    item = queues[name].popleft()
                    selected[item.id] = item
        self.rotation += 1
        return CandidateBatch(
            list(selected.values())[:8],
            {i: all_sources[i] for i in selected},
            {i.id: "batch_limit_or_missing_usage" for i in eligible if i.id not in selected},
        )


def plan_batch(
    items: list[Item],
    judgments: dict[str, Judgment],
    now: float,
    kept: set[str],
    cooldown: set[str],
    threshold: float = 0.85,
    limit: int = 3,
) -> list[Item]:
    result = []
    for item in items:
        j = judgments.get(item.id, Judgment())
        if not item.eligible(now, kept, cooldown):
            continue
        if (
            j.relation != "unrelated"
            or j.retention not in {"defer", "done"}
            or j.action != item.allowed_action
            or j.source != "jev"
            or not math.isfinite(j.confidence)
            or j.confidence < threshold
        ):
            continue
        result.append(item)
    return sorted(
        result,
        key=lambda i: (
            0 if judgments[i.id].retention == "done" else 1,
            i.reopen_cost is None,
            i.reopen_cost or 0,
            i.memory_bytes is None,
            -(i.memory_bytes or 0),
            i.last_used is None,
            i.last_used or 0,
            i.frequency or 0,
            i.id,
        ),
    )[:limit]


@dataclass
class Usage:
    last_used: float | None = None
    frequency: float = 0.0
    updated_at: float = 0.0
    last_visit: float = 0.0


class UsageTracker:
    def __init__(self, half_life: float = 3600 * 24, merge_seconds: float = 15):
        self.half_life = half_life
        self.merge_seconds = merge_seconds
        self.values: dict[str, Usage] = {}
        self.seen: OrderedDict[str, None] = OrderedDict()

    def observe(self, key: str, event_id: str, now: float, origin: str) -> bool:
        if origin not in {"user", "foreground_observed"} or event_id in self.seen:
            return False
        self.seen[event_id] = None
        if len(self.seen) > 4096:
            self.seen.popitem(last=False)
        old = self.values.setdefault(key, Usage())
        delta = max(0, now - old.updated_at)
        score = old.frequency * math.pow(2, -delta / self.half_life)
        increment = old.last_used is None or now - old.last_visit >= self.merge_seconds
        old.frequency = score + int(increment)
        old.updated_at = now
        old.last_used = max(now, old.last_used or now)
        if increment:
            old.last_visit = now
        return bool(increment)

    def get(self, key: str, now: float) -> tuple[float | None, float | None]:
        value = self.values.get(key)
        if value is None:
            return None, None
        return value.last_used, value.frequency * math.pow(
            2, -max(0, now - value.updated_at) / self.half_life
        )

    def touch(self, key: str, now: float):
        """Continuing foreground time changes recency, not the number of visits."""
        if key in self.values:
            self.values[key].last_used = now

    def dump(self) -> dict:
        return {key: asdict(value) for key, value in self.values.items()}


@dataclass
class Ghost:
    action_id: str
    item_id: str
    stable_key: str
    completed_at: float
    observation_end: float
    covered_seconds: float = 0.0
    last_observed: float = 0.0
    interrupted: bool = False
    outcome: str = "observing"
    seen_events: set[str] = field(default_factory=set)

    def tick(self, now: float, connected: bool):
        if self.outcome != "observing":
            return
        previous = self.last_observed or self.completed_at
        delta = min(now, self.observation_end) - previous
        if not connected or delta > 10 or delta < 0:
            self.interrupted = True
        elif delta > 0:
            self.covered_seconds += delta
        self.last_observed = min(now, self.observation_end)
        if now >= self.observation_end:
            self.outcome = "incomplete" if self.interrupted else "no_reopen_observed"

    def revisit(self, event_id: str, item_id: str, origin: str, now: float) -> bool:
        if (
            event_id in self.seen_events
            or item_id != self.item_id
            or self.outcome != "observing"
            or now > self.observation_end
        ):
            return False
        self.seen_events.add(event_id)
        self.outcome = {"user": "user_reopened", "automatic": "auto_restarted"}.get(origin, "unknown_reopen")
        return True


class MemoryWindow:
    def __init__(self):
        self.samples: deque[tuple[float, int]] = deque(maxlen=301)

    def append(self, now: float, available: int):
        self.samples.append((now, available))
        while self.samples and now - self.samples[0][0] > 600:
            self.samples.popleft()

    def measure(self, started: float, ended: float, concurrent: bool = False) -> dict:
        before = [(t, n) for t, n in self.samples if started - 10 <= t < started]
        after = [(t, n) for t, n in self.samples if ended + 5 <= t <= ended + 20]

        def covered(values, span):
            return (
                len(values) >= 4
                and values[-1][0] - values[0][0] >= span
                and max((b[0] - a[0] for a, b in zip(values, values[1:])), default=0) <= 5
            )

        if concurrent or not covered(before, 6) or not covered(after, 10):
            return {"valid": False, "reason": "concurrent_activity" if concurrent else "insufficient_samples"}
        for values in (before, after):
            numbers = [n for _, n in values]
            if max(numbers) - min(numbers) > max(128 * MIB, median(numbers) * 0.1):
                return {"valid": False, "reason": "unstable_window"}
        return {
            "valid": True,
            "delta_bytes": int(median(n for _, n in after) - median(n for _, n in before)),
            "evidence": "E1",
            "label": "处理后观察到的可用内存变化",
        }
