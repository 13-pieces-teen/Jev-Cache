"""Edge Native Messaging host. stdout is exclusively binary protocol traffic."""

from __future__ import annotations

import json
import os
import struct
import sys
from multiprocessing.connection import Client

from .bridge import MAX_MESSAGE, pipe_credentials


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
                    address, key = pipe_credentials()
                    conn = Client(address, family="AF_PIPE", authkey=key)
                conn.send_bytes(message)
                response = conn.recv_bytes(MAX_MESSAGE)
            except (OSError, EOFError, ValueError):
                if conn:
                    conn.close()
                conn = None
                response = json.dumps(
                    {"protocol": 1, "commands": [], "error": "assistant_unavailable"}
                ).encode()
            sys.stdout.buffer.write(struct.pack("<I", len(response)) + response)
            sys.stdout.buffer.flush()
        except (EOFError, BrokenPipeError):
            return


if __name__ == "__main__":
    main()
