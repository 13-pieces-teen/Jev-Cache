"""Authenticated, local Windows named-pipe bridge; protocol uses bytes/JSON, not pickle."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener

from .storage import data_directory, protect_secret, unprotect_secret

HOST_NAME = "ai.typesafe.jevcache"
CONNECTION_CONFIG = "bridge-connection.json"
MAX_MESSAGE = 512 * 1024


def pipe_credentials() -> tuple[str, bytes]:
    folder = data_directory()
    path = folder / "bridge.secret"
    if not path.exists():
        path.write_text(protect_secret(os.urandom(32).hex()), encoding="utf-8")
    key = bytes.fromhex(unprotect_secret(path.read_text(encoding="utf-8")))
    suffix = hashlib.sha256(str(folder).casefold().encode()).hexdigest()[:20]
    return rf"\\.\pipe\JevCache-{suffix}", key


class Bridge:
    def __init__(self):
        self.incoming: queue.Queue = queue.Queue(maxsize=128)
        self.commands: list[dict] = []
        self.lock = threading.Lock()
        self.enabled = True
        self.last_seen = 0.0
        self.coverage_gap = False
        self.error = ""

    def start(self):
        if os.name == "nt":
            threading.Thread(target=self._listen, name="edge-pipe", daemon=True).start()

    def _listen(self):
        try:
            address, key = pipe_credentials()
            with Listener(address, family="AF_PIPE", authkey=key) as listener:
                while self.enabled:
                    try:
                        conn = listener.accept()
                        with conn:
                            while self.enabled:
                                data = conn.recv_bytes(MAX_MESSAGE)
                                message = json.loads(data)
                                if not isinstance(message, dict) or message.get("protocol") != 1:
                                    raise ValueError("protocol")
                                if message.get("kind") == "ping":
                                    conn.send_bytes(json.dumps({"protocol": 1, "commands": []}).encode())
                                    continue
                                if message.get("kind") != "snapshot":
                                    raise ValueError("message kind")
                                self.error = ""
                                self.last_seen = time.monotonic()
                                try:
                                    self.incoming.put_nowait(message)
                                except queue.Full:
                                    self.coverage_gap = True
                                    self.cancel()
                                with self.lock:
                                    commands, self.commands = self.commands, []
                                conn.send_bytes(json.dumps({"protocol": 1, "commands": commands}).encode())
                    except AuthenticationError:
                        # A stale/different launcher configuration must not stop
                        # the listener and prevent all subsequent reconnections.
                        self.error = "浏览器桥接认证失败，请重新准备 Edge 接入"
                        self.last_seen = 0
                        self.cancel()
                    except (EOFError, OSError, ValueError, json.JSONDecodeError):
                        self.last_seen = 0
                        self.cancel()
        except (OSError, ValueError):
            self.error = "浏览器桥接暂不可用"

    @property
    def connected(self):
        return bool(self.last_seen and time.monotonic() - self.last_seen < 8)

    def send(self, command: dict):
        if not self.connected:
            raise RuntimeError("Browser disconnected")
        with self.lock:
            if len(self.commands) >= 8:
                raise RuntimeError("Command queue full")
            self.commands.append({**command, "expires_at": time.time() + 5})

    def cancel(self):
        with self.lock:
            self.commands.clear()
