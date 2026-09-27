"""Edge Native Messaging host. stdout is exclusively binary protocol traffic."""

from __future__ import annotations

import json
import os
import struct
import sys
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client
from pathlib import Path

from .bridge import CONNECTION_CONFIG, MAX_MESSAGE, pipe_credentials
from .storage import unprotect_secret


def host_credentials() -> tuple[str, bytes]:
    config = Path(sys.executable).parent / CONNECTION_CONFIG
    if not getattr(sys, "frozen", False) or not config.is_file():
        return pipe_credentials()
    settings = json.loads(config.read_text(encoding="utf-8"))
    address = settings["address"]
    secret = Path(settings["secret_path"])
    if (
        settings.get("version") != 1
        or not isinstance(address, str)
        or not address.startswith(r"\\.\pipe\JevCache-")
        or not secret.is_absolute()
        or secret.name != "bridge.secret"
    ):
        raise ValueError("Invalid installed bridge configuration")
    key = bytes.fromhex(unprotect_secret(secret.read_text(encoding="utf-8")))
    if len(key) != 32:
        raise ValueError("Invalid bridge credential")
    return address, key


def read_exact(stream, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise EOFError
        result.extend(chunk)
    return bytes(result)


def main():
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    conn = None
    while True:
        try:
            size = struct.unpack("<I", read_exact(sys.stdin.buffer, 4))[0]
            if size > MAX_MESSAGE:
                return
            message = read_exact(sys.stdin.buffer, size)
            try:
                if conn is None:
                    address, key = host_credentials()
                    conn = Client(address, family="AF_PIPE", authkey=key)
                conn.send_bytes(message)
                response = conn.recv_bytes(MAX_MESSAGE)
            except (OSError, EOFError, ValueError, KeyError, AuthenticationError) as error:
                if conn:
                    conn.close()
                conn = None
                code = (
                    "bridge_authentication_failed"
                    if isinstance(error, AuthenticationError)
                    else "assistant_unavailable"
                )
                response = json.dumps({"protocol": 1, "commands": [], "error": code}).encode()
            sys.stdout.buffer.write(struct.pack("<I", len(response)) + response)
            sys.stdout.buffer.flush()
        except (EOFError, BrokenPipeError):
            return


if __name__ == "__main__":
    main()
