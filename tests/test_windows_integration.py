import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import psutil
import pytest

from jev_cache.core import Item
from jev_cache.runtime import Runtime
from jev_cache.storage import Store
from jev_cache.windows import request_normal_close

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows only")


def test_actual_wm_close_receipt_for_owned_disposable_window(tmp_path):
    ready = tmp_path / "ready.json"
    root = Path(__file__).resolve().parents[1]
    child = subprocess.Popen(
        [sys.executable, str(root / "scripts/controlled_window.py"), "--ready", str(ready)]
    )
    runtime = Runtime()
    runtime.store = Store(tmp_path / "run.sqlite3")
    runtime.kept = set()
    runtime.settings = {"memory": False}
    try:
        deadline = time.monotonic() + 12
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert ready.exists(), "Controlled target did not start"
        identity = json.loads(ready.read_text())
        target = Item(
            "controlled-target",
            "controlled-target",
            "测试窗口",
            "app",
            time.time(),
            "v1",
            pid=identity["pid"],
            created=identity["created"],
            hwnd=identity["hwnd"],
            allowed_action="request_exit",
        )
        assert psutil.pid_exists(target.pid)
        accepted, _ = request_normal_close(replace(target, created=target.created - 100))
        assert not accepted and psutil.pid_exists(target.pid), "Stale identity must be rejected"
        runtime._execute(target, time.time(), explicit=True)
        deadline = time.monotonic() + 10
        while runtime.pending and time.monotonic() < deadline:
            runtime._pending(time.time())
            time.sleep(0.1)
        receipts = runtime.store.recent()
        assert len(receipts) == 1 and receipts[0]["status"] == "completed"
        assert not psutil.pid_exists(target.pid)
        evidence = {
            "test": "controlled_normal_close",
            "target_was_owned_test_window": True,
            "stale_identity_rejected": True,
            "receipt": receipts[0],
            "third_party_compatibility_claim": False,
        }
        (root / "artifacts").mkdir(exist_ok=True)
        (root / "artifacts/controlled-close.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        if child.poll() is None:
            child.terminate()  # Only the exact disposable subprocess created by this test.
        child.wait(timeout=10)
        runtime.pool.shutdown(wait=False, cancel_futures=True)
        runtime.store.close()
