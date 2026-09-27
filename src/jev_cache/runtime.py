"""Single owner of mutable state, storage and action coordination."""

from __future__ import annotations

import queue
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace

from PySide6.QtCore import QThread, Signal

from .bridge import Bridge
from .core import CandidateGenerator, Ghost, Item, MemoryWindow, Usage, UsageTracker, plan_batch
from .provider import JevProvider, friendly_error
from .storage import Store, data_directory, protect_secret, unprotect_secret
from .windows import Collector, has_exited, request_normal_close


class Runtime(QThread):
    state_changed = Signal(object)
    notice = Signal(str)
    configuration_result = Signal(str)

    def __init__(self):
        super().__init__()
        self.commands: queue.Queue = queue.Queue(maxsize=128)
        self.stopping = threading.Event()
        self.cancelled = threading.Event()
        self.epoch = 0
        self.control_lock = threading.Lock()
        self.bridge = Bridge()
        self.apps: list[Item] = []
        self.tabs: list[Item] = []
        self.tab_payload: list[dict] = []
        self.browser_session = ""
        self.browser_seq = -1
        self.items: dict[str, Item] = {}
        self.usage = UsageTracker()
        self.generator = CandidateGenerator()
        self.window = MemoryWindow()
        self.ghosts: dict[str, Ghost] = {}
        self.cooldown: dict[str, float] = {}
        self.pending: dict[str, dict] = {}
        self.measurements: list[dict] = []
        self.last_result = None
        self.plan: list[Item] = []
        self.plan_deadline = 0.0
        self.plan_epoch = 0
        self.plan_automatic = False
        self.active_keys: set[str] = set()
        self.ghost_scopes: dict[str, str] = {}
        self.status = "正在了解这台电脑"
        self.paused = False
        self.future = None
        self.future_kind = ""
        self.future_epoch = 0
        self.future_batch = None
        self.context = ""
        self.pressure_since = None
        self.last_auto = 0.0
        self.latest = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jev-network")

    def submit(self, kind: str, **payload):
        if kind in {"pause", "keep", "forget", "settings", "correct"}:
            with self.control_lock:
                self.epoch += 1
            self.cancelled.set()
            self.bridge.cancel()
        try:
            self.commands.put_nowait((kind, payload))
        except queue.Full:
            self.cancelled.set()
            self.notice.emit("操作较多，已停止未执行计划，请稍后重试。")

    def stop(self):
        self.stopping.set()
        self.cancelled.set()
        self.bridge.cancel()
        self.bridge.enabled = False

    def run(self):
        store = self.store = Store(data_directory() / "memory.sqlite3")
        try:
            self.settings = {
                "auto": store.get("auto", False),
                "memory": store.get("memory_enabled", True),
                "cloud": store.get("cloud", False),
                "share_titles": store.get("share_titles", False),
                "model": store.get("model", "jev-latest"),
            }
            self.kept = set(store.get("kept", []))
            self.keep_names = store.get("keep_names", {})
            self.provider = JevProvider(unprotect_secret(store.get("api_key", "")), self.settings["model"])
            if self.settings["memory"]:
                saved = store.memories().get("usage", {})
                self.usage.values = {
                    key: Usage(**value)
                    for key, value in saved.items()
                    if time.time() - value.get("updated_at", 0) < 7 * 86400
                }
            self.collector = Collector()
            self.bridge.start()
            sample_due = collect_due = persist_due = view_due = 0.0
            while not self.stopping.is_set():
                now = time.time()
                self._commands(now)
                self._browser(now)
                if now >= sample_due:
                    self.latest = self.collector.sample()
                    self.window.append(now, self.latest["available"])
                    sample_due = now + 2
                if now >= collect_due:
                    old_ids = {i.id for i in self.apps}
                    self.apps = self.collector.collect(now)
                    new_ids = {i.id for i in self.apps}
                    expected_exits = {p["item"].id for p in self.pending.values() if "item" in p}
                    if old_ids and (old_ids ^ new_ids) - expected_exits:
                        for measurement in self.measurements:
                            measurement["concurrent"] = True
                    if self.status == "正在了解这台电脑":
                        self.status = (
                            "内存目前够用，可以按需整理"
                            if self.latest.get("used_percent", 0) < 85
                            else "内存有些紧，可以检查后台占用"
                        )
                    current_keys = {app.stable_key for app in self.apps if app.active}
                    for app in self.apps:
                        if app.active:
                            if app.stable_key not in self.active_keys:
                                self.usage.observe(
                                    app.stable_key, f"focus:{app.id}:{now}", now, "foreground_observed"
                                )
                            else:
                                self.usage.touch(app.stable_key, now)
                    self.active_keys = current_keys
                    collect_due = now + 8
                self._refresh_items(now)
                self._network_result(now)
                self._pending(now)
                self._advance_plan(now)
                for ghost in self.ghosts.values():
                    before = ghost.outcome
                    ghost.tick(now, self.bridge.connected if ghost.item_id.startswith("tab:") else True)
                    if ghost.outcome != before:
                        self._save_ghost(ghost)
                self._measure(now)
                self._automatic(now)
                if now >= persist_due:
                    horizon = 7 * 86400 if self.settings["memory"] else 600
                    self.usage.values = {
                        key: value
                        for key, value in self.usage.values.items()
                        if value.last_used is not None and now - value.last_used <= horizon
                    }
                    self.ghosts = {
                        key: ghost for key, ghost in self.ghosts.items() if now - ghost.completed_at <= 600
                    }
                    self.ghost_scopes = {
                        key: value for key, value in self.ghost_scopes.items() if key in self.ghosts
                    }
                    if self.settings["memory"]:
                        store.remember("usage", self.usage.dump())
                    store.prune()
                    persist_due = now + 60
                if now >= view_due:
                    self.state_changed.emit(self.view(now))
                    view_due = now + 2
                self.stopping.wait(0.5)
            if self.settings["memory"]:
                store.remember("usage", self.usage.dump())
        except Exception as error:
            # No repr(error): an HTTP error might contain confidential request headers.
            self.notice.emit(f"后台组件停止（{type(error).__name__}），未执行新的清理。")
            import logging

            logging.getLogger("jev_cache").exception("Runtime failure")
        finally:
            self.bridge.cancel()
            self.pool.shutdown(wait=False, cancel_futures=True)
            store.close()

    def _commands(self, now):
        for _ in range(32):
            try:
                kind, payload = self.commands.get_nowait()
            except queue.Empty:
                break
            if kind == "optimize":
                self.context = str(payload.get("context", ""))[:200]
                # An explicit click starts a new manual round, including from pause.
                self.paused = False
                self._optimize(
                    now, automatic=False, allow_summary_once=payload.get("allow_summary_once") is True
                )
            elif kind == "pause":
                self.paused = bool(payload["value"])
                self.plan.clear()
                self.status = "已暂停整理" if self.paused else "已恢复观察"
                if not self.paused:
                    self.cancelled.clear()
            elif kind == "keep":
                item = self.items.get(payload["item_id"])
                if item:
                    if item.stable_key in self.kept:
                        self.kept.remove(item.stable_key)
                        self.keep_names.pop(item.stable_key, None)
                    else:
                        self.kept.add(item.stable_key)
                        self.keep_names[item.stable_key] = item.name
                    self.store.put("kept", sorted(self.kept))
                    self.store.put("keep_names", self.keep_names)
                    self.plan.clear()
                    self.cancelled.clear()
            elif kind == "forget":
                self.store.forget()
                self.usage = UsageTracker()
                self.ghosts.clear()
                self.ghost_scopes.clear()
                self.cooldown.clear()
                self.plan.clear()
                # An already-posted OS request cannot be undone. Forget its pending
                # record too, so a late receipt cannot recreate deleted history.
                self.pending.clear()
                self.measurements.clear()
                self.last_result = None
                self.cancelled.clear()
                self.notice.emit("学习记录已清除；你明确设置的保留项仍然有效。")
            elif kind == "settings":
                self._settings(payload)
            elif kind == "test_connection":
                if self.future:
                    self.configuration_result.emit("已有请求进行中，请稍后测试。")
                else:
                    key = payload.get("key") or self.provider.key
                    test = JevProvider(key, payload.get("model") or self.provider.model)
                    if not test.configured:
                        self.configuration_result.emit("请先填写 API Key。")
                    else:
                        self.future = self.pool.submit(test.test_connection)
                        self.future_kind = "test"
            elif kind == "close_item":
                item = self.items.get(payload["item_id"])
                if item and not self.pending and not self.future and not self.paused:
                    self.cancelled.clear()
                    self._execute(item, now, explicit=True)
            elif kind == "reopen":
                record = next((r for r in self.store.recent() if r["id"] == payload["action_id"]), None)
                if record and record.get("kind") == "tab" and self.bridge.connected:
                    self._reopen(record, now)
            elif kind == "correct":
                record = next((r for r in self.store.recent() if r["id"] == payload["action_id"]), None)
                if record:
                    record["corrected"] = True
                    self.store.receipt(record["id"], record)
                    self.cooldown[record["stable_key"]] = now + 3600
                    if self.settings["memory"]:
                        self.store.remember(
                            "feedback:" + record["stable_key"],
                            {
                                "kind": "user_correction",
                                "scope": self.context,
                                "at": now,
                                "stable_key": record["stable_key"],
                                "reason": "用户认为本次不该清理",
                            },
                        )
                    self.plan.clear()
                    self.cancelled.clear()
                    self.notice.emit("已记录这次纠正，并暂停整理该对象。")

    def _settings(self, value):
        self.plan.clear()
        old_memory = self.settings["memory"]
        for key in self.settings:
            if key in value:
                self.settings[key] = value[key]
                self.store.put("memory_enabled" if key == "memory" else key, value[key])
        if "key" in value and value["key"]:
            self.store.put("api_key", protect_secret(value["key"].strip()))
        if value.get("remove_key"):
            self.store.put("api_key", "")
        self.provider = JevProvider(unprotect_secret(self.store.get("api_key", "")), self.settings["model"])
        if old_memory != self.settings["memory"]:
            self.usage = UsageTracker()
            self.ghosts.clear()
            self.cooldown.clear()
        self.cancelled.clear()
        self.configuration_result.emit(
            "设置已保存。" if self.provider.configured else "设置已保存，当前使用基础模式。"
        )

    def _browser(self, now):
        if self.bridge.coverage_gap:
            self.epoch += 1
            self.plan.clear()
            self.bridge.coverage_gap = False
            self.tabs.clear()
            for g in self.ghosts.values():
                g.interrupted = True
        for _ in range(24):
            try:
                packet = self.bridge.incoming.get_nowait()
            except queue.Empty:
                break
            if packet.get("kind") != "snapshot":
                continue
            session = str(packet.get("session", ""))[:80]
            if session != self.browser_session:
                self.epoch += 1
                self.plan.clear()
                self.browser_seq = -1
                self.browser_session = session
                for g in self.ghosts.values():
                    if g.item_id.startswith("tab:"):
                        g.interrupted = True
            seq = packet.get("seq", 0)
            if not isinstance(seq, int) or seq <= self.browser_seq:
                continue
            self.browser_seq = seq
            self.tab_payload = packet.get("tabs", [])[:160]
            self.tabs = [self._tab(p, now) for p in self.tab_payload if isinstance(p, dict)]
            for event in packet.get("events", [])[:100]:
                self._browser_event(event, now)

    def _tab(self, tab, now):
        navigation = int(tab.get("navigation", 0))
        tab_id = int(tab.get("id", -1))
        identity = f"tab:{self.browser_session}:{tab_id}:{navigation}"
        key = "page:" + str(tab.get("object_key") or f"{self.browser_session}:{tab_id}:{navigation}")[:100]
        protections = []
        for field, label in (
            ("active", "当前标签"),
            ("pinned", "固定的标签"),
            ("audible", "正在播放声音"),
            ("dirty", "可能有未保存输入"),
            ("loading", "正在加载"),
            ("discarded", "已释放"),
        ):
            if tab.get(field):
                protections.append(label)
        if not tab.get("auto_discardable", False):
            protections.append("浏览器要求保留")
        verified = bool(tab.get("verified"))
        hint = ""
        if self.settings["share_titles"]:
            hint = re.sub(r"[\w.+-]+@[\w.-]+|https?://\S+|[A-Za-z]:\\\S+", "[已省略]", tab.get("title", ""))[
                :80
            ]
        return Item(
            id=identity,
            stable_key=key,
            name=str(tab.get("name", "网页"))[:100],
            kind="tab",
            observed_at=now,
            version=f"{identity}:{verified}:{','.join(protections)}",
            active=bool(tab.get("active")),
            protections=tuple(protections),
            allowed_action="discard_tab" if verified else "none",
            auto_eligible=verified,
            last_used=tab.get("last_used"),
            tab_id=tab_id,
            browser_session=self.browser_session,
            navigation=navigation,
            reopen_cost=1 if verified else None,
            details="限定只读文档适配" if verified else "网页状态覆盖不足，保留",
            semantic_hint=hint,
        )

    def _browser_event(self, event, now):
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        identity = f"tab:{self.browser_session}:{event.get('tab_id')}:{event.get('navigation', 0)}"
        if kind == "usage":
            item = next((i for i in self.tabs if i.id == identity), None)
            if item:
                self.usage.observe(item.stable_key, event.get("event_id", ""), now, "user")
        elif kind == "revisit":
            for ghost in self.ghosts.values():
                if ghost.revisit(event.get("event_id", ""), identity, event.get("origin", "unknown"), now):
                    self.cooldown[ghost.stable_key] = now + 600
                    self._save_ghost(ghost)
        elif kind == "receipt":
            action_id = event.get("action_id")
            pending = self.pending.get(action_id)
            if pending:
                if pending.get("reopen"):
                    if event.get("status") == "completed":
                        ghost = self.ghosts.get(pending["parent_id"])
                        if ghost:
                            ghost.outcome = "user_reopened"
                            self.cooldown[ghost.stable_key] = now + 600
                            self._save_ghost(ghost)
                    self.pending.pop(action_id, None)
                else:
                    self._finish(
                        action_id,
                        event.get("status") == "completed",
                        now,
                        "网页已释放" if event.get("status") == "completed" else "网页状态已变化，本次保留",
                    )

    def _save_ghost(self, ghost):
        if not self.settings["memory"]:
            return
        self.store.remember(
            "ghost:" + ghost.stable_key,
            {
                "kind": "cleanup_outcome",
                "stable_key": ghost.stable_key,
                "outcome": ghost.outcome,
                "action_id": ghost.action_id,
                "scope": self.ghost_scopes.get(ghost.action_id, ""),
                "covered_seconds": ghost.covered_seconds,
                "interrupted": ghost.interrupted,
                "at": ghost.completed_at,
            },
        )

    def _refresh_items(self, now):
        self.cooldown = {key: expiry for key, expiry in self.cooldown.items() if expiry > now}
        if not self.bridge.connected:
            self.tabs.clear()
        self.items = {}
        for item in self.apps + self.tabs:
            used, frequency = self.usage.get(item.stable_key, now)
            self.items[item.id] = replace(item, last_used=used or item.last_used, frequency=frequency)

    def _optimize(self, now, automatic, *, allow_summary_once=False):
        if self.paused or self.pending or self.future or self.plan:
            if not automatic:
                self.notice.emit("当前已暂停或正在处理，请稍候。")
            return
        summary_allowed = self.settings["cloud"] or (not automatic and allow_summary_once)
        if not self.provider.configured or not summary_allowed:
            self.status = "已检查当前占用 · 基础模式"
            if not automatic:
                self.notice.emit("尚未启用 Jev。可在设置中配置，或自行选择应用请求正常关闭。")
            return
        batch = self.generator.generate(list(self.items.values()), now, self.kept, set(self.cooldown))
        if not batch.items:
            self.status = "目前没有适合一键整理的对象"
            return
        self.cancelled.clear()
        self.future_epoch = self.epoch
        self.plan_automatic = automatic
        self.future_batch = batch
        memories = []
        if self.settings["memory"]:
            stored = self.store.memories()
            for n, item in enumerate(batch.items):
                for prefix in ("ghost:", "feedback:"):
                    value = stored.get(prefix + item.stable_key)
                    if value and (not value.get("scope") or value.get("scope") == self.context):
                        memories.append(
                            {k: v for k, v in value.items() if k in {"kind", "scope", "outcome", "reason"}}
                            | {"candidate_id": f"item_{n}"}
                        )
        self.future = self.pool.submit(self.provider.judge, batch.items, now, memories, self.context)
        self.future_kind = "judge"
        self.plan_deadline = now + 30
        self.status = "Jev 正在结合使用记录判断"

    def _network_result(self, now):
        if not self.future or not self.future.done():
            return
        future, kind = self.future, self.future_kind
        self.future = None
        try:
            result = future.result()
            if kind == "test":
                self.configuration_result.emit(f"连接成功 · {result['model']}。尚未执行清理。")
                return
            if self.cancelled.is_set() or self.epoch != self.future_epoch or now > self.plan_deadline:
                self.status = "状态已变化，本次判断已失效"
                return
            judgments, meta = result
            batch = self.future_batch
            fresh = [
                self.items[i.id]
                for i in batch.items
                if i.id in self.items and self.items[i.id].version == i.version
            ]
            self.plan = plan_batch(fresh, judgments, now, self.kept, set(self.cooldown), limit=1)
            self.plan_epoch = self.epoch
            if self.settings["memory"]:
                self.store.decision(
                    uuid.uuid4().hex,
                    {
                        "candidate_sources": batch.sources,
                        "omitted": batch.omitted,
                        "judgments": {i: asdict(j) for i, j in judgments.items()},
                        "meta": meta,
                        "selected": [i.id for i in self.plan],
                        "policy": "cache-0.1",
                    },
                )
            self.status = f"已找到 {len(self.plan)} 个可整理对象" if self.plan else "Jev 建议保留当前候选"
        except Exception as error:
            if kind == "test":
                self.configuration_result.emit(friendly_error(error))
            else:
                self.status = "本次保留候选"
                self.notice.emit(friendly_error(error))

    def _advance_plan(self, now):
        if not self.plan or self.pending:
            return
        if (
            self.cancelled.is_set()
            or self.epoch != self.plan_epoch
            or self.paused
            or now > self.plan_deadline
        ):
            self.plan.clear()
            return
        if self.plan_automatic and self.latest.get("used_percent", 0) < 78:
            self.plan.clear()
            self.status = "内存压力已缓解"
            return
        selected = self.plan.pop(0)
        current = self.items.get(selected.id)
        if (
            current
            and current.version == selected.version
            and current.eligible(now, self.kept, set(self.cooldown))
        ):
            self._execute(current, now, explicit=False)

    def _execute(self, item, now, explicit):
        if (
            self.cancelled.is_set()
            or self.paused
            or item.active
            or item.protections
            or item.stable_key in self.kept
            or self.pending
        ):
            return
        for measurement in self.measurements:
            measurement["concurrent"] = True
        action_id = uuid.uuid4().hex
        body = {
            "id": action_id,
            "at": now,
            "item_id": item.id,
            "stable_key": item.stable_key,
            "name": item.name,
            "kind": item.kind,
            "action": item.allowed_action,
            "status": "requested",
            "source": "user" if explicit else "jev",
            "browser_session": item.browser_session,
            "tab_id": item.tab_id,
            "navigation": item.navigation,
        }
        self.store.receipt(action_id, body)
        self.pending[action_id] = {"item": item, "body": body, "started": now, "deadline": now + 15}
        self.status = "正在请求正常处理"
        if item.kind == "app" and explicit:
            ok, message = request_normal_close(item)
            if not ok:
                self._finish(action_id, False, now, message)
        elif item.kind == "tab" and item.allowed_action == "discard_tab":
            try:
                self.bridge.send(
                    {
                        "id": action_id,
                        "action": "discard_tab",
                        "tab_id": item.tab_id,
                        "session": item.browser_session,
                        "navigation": item.navigation,
                        "explicit": explicit,
                    }
                )
            except RuntimeError:
                self._finish(action_id, False, now, "浏览器连接已中断")
        else:
            self._finish(action_id, False, now, "没有已验证的执行能力")

    def _pending(self, now):
        for action_id, p in list(self.pending.items()):
            if p.get("reopen"):
                if now > p["deadline"]:
                    self.pending.pop(action_id, None)
            elif p["item"].kind == "app" and has_exited(p["item"]):
                self._finish(action_id, True, now, "已确认应用退出")
            elif now > p["deadline"]:
                self._finish(action_id, False, now, "尚未确认完成；可能有保存提示或已收起到托盘")

    def _finish(self, action_id, completed, now, message):
        pending = self.pending.pop(action_id)
        body, item = pending["body"], pending["item"]
        body.update(status="completed" if completed else "not_completed", message=message, completed_at=now)
        self.store.receipt(action_id, body)
        self.status = message
        if completed:
            self.ghosts[action_id] = Ghost(action_id, item.id, item.stable_key, now, now + 300)
            self.ghost_scopes[action_id] = self.context
            self.cooldown[item.stable_key] = now + 300
            self.measurements.append(
                {"id": action_id, "started": pending["started"], "ended": now, "body": body}
            )
            self.last_result = {
                "valid": False,
                "reason": "measuring",
                "name": item.name,
                "action_id": action_id,
            }

    def _measure(self, now):
        remaining = []
        for measurement in self.measurements:
            if now < measurement["ended"] + 20:
                remaining.append(measurement)
                continue
            result = self.window.measure(
                measurement["started"], measurement["ended"], measurement.get("concurrent", False)
            )
            self.last_result = result | {"name": measurement["body"]["name"], "action_id": measurement["id"]}
            self.store.receipt(measurement["id"], measurement["body"] | {"measurement": result})
        self.measurements = remaining

    def _reopen(self, record, now):
        action_id = uuid.uuid4().hex
        try:
            self.bridge.send(
                {
                    "id": action_id,
                    "action": "reopen",
                    "tab_id": record["tab_id"],
                    "session": record["browser_session"],
                    "navigation": record["navigation"],
                }
            )
            self.pending[action_id] = {"reopen": True, "parent_id": record["id"], "deadline": now + 10}
        except RuntimeError:
            self.notice.emit("浏览器暂未连接，原标签仍保留在浏览器中。")

    def _automatic(self, now):
        pressure = self.latest.get("used_percent", 0) >= 85
        self.pressure_since = (self.pressure_since or now) if pressure else None
        if (
            self.settings["auto"]
            and self.settings["cloud"]
            and self.provider.configured
            and self.pressure_since
            and now - self.pressure_since >= 20
            and now - self.last_auto >= 120
        ):
            self.last_auto = now
            self._optimize(now, automatic=True)

    def view(self, now):
        return {
            "sample": dict(self.latest),
            "items": list(self.items.values()),
            "status": self.status,
            "paused": self.paused,
            "busy": bool(self.future or self.pending or self.plan),
            "phase": (
                "executing"
                if self.pending or self.plan
                else "connecting"
                if self.future and self.future_kind == "test"
                else "judging"
                if self.future
                else "idle"
            ),
            "memory_pressure": bool(self.pressure_since and now - self.pressure_since >= 20),
            "configured": self.provider.configured,
            "settings": dict(self.settings),
            "browser_connected": self.bridge.connected,
            "browser_error": self.bridge.error,
            "kept": set(self.kept),
            "keep_names": dict(self.keep_names),
            "cooldown": set(self.cooldown),
            "history": self.store.recent(20),
            "last_result": self.last_result,
            "memory_count": len(self.usage.values) if self.settings["memory"] else 0,
            "ghosts": {
                k: {"outcome": g.outcome, "covered_seconds": g.covered_seconds, "interrupted": g.interrupted}
                for k, g in self.ghosts.items()
            },
        }
