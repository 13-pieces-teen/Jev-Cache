import json
import os
from dataclasses import replace

import pytest
from test_policy import item

from jev_cache.provider import JevProvider, build_request, parse_answers
from jev_cache.storage import Store, protect_secret, unprotect_secret


def response(payload):
    choices = {"relation": "unrelated", "retention": "done", "action": "discard_tab"}
    return {
        "model": "test-model",
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "answers": {
            key: {
                "type": "choice",
                "choice": choices[key.rsplit("_", 1)[1]],
                "confidence": 0.95,
                "probabilities": {
                    option: float(option == choices[key.rsplit("_", 1)[1]]) for option in q["criteria"]
                },
            }
            for key, q in payload["questions"].items()
        },
    }


def test_request_omits_local_identity_titles_and_paths():
    target = replace(item(), name="private window title", pid=12345, hwnd=5678, details="C:\\secret\\file")
    payload, aliases = build_request([target], 100, [])
    encoded = json.dumps(payload)
    assert "private window title" not in encoded and "secret" not in encoded and "12345" not in encoded
    result = parse_answers(response(payload), aliases, [target])
    assert result["a"].source == "jev"


def test_bad_model_output_never_becomes_a_plan():
    target = item()
    payload, aliases = build_request([target], 100, [])
    body = response(payload)
    body["answers"]["item_0_action"]["choice"] = "kill_all"
    with pytest.raises(ValueError):
        parse_answers(body, aliases, [target])


def test_real_sdk_transport_and_serialization_without_network(monkeypatch):
    import httpx2
    import typesafe_sdk

    original = typesafe_sdk.TypeSafeClient
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx2.Response(200, json=response(body))

    def client(**kwargs):
        return original(**kwargs, transport=httpx2.MockTransport(handle))

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", client)
    judgments, metadata = JevProvider("synthetic-test-key").judge([item()], 100, [])
    assert judgments["a"].action == "discard_tab"
    assert metadata["model"] == "test-model"
    assert len(calls) == 1


def test_store_deletion_preserves_preferences_and_invalidates_history(tmp_path):
    store = Store(tmp_path / "memory.db")
    store.put("kept", ["keep-me"])
    store.remember("usage", {"a": 1})
    store.receipt("act", {"id": "act", "status": "completed"})
    store.decision("run", {"memory": "a"})
    store.forget()
    assert store.get("kept") == ["keep-me"] and store.memories() == {} and store.recent() == []
    assert store.get("memory_version") == 1
    store.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_secret_is_current_user_encrypted():
    encrypted = protect_secret("synthetic-test-key")
    assert "synthetic-test-key" not in encrypted
    assert unprotect_secret(encrypted) == "synthetic-test-key"
    assert unprotect_secret("invalid") == ""
