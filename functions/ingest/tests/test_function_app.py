import importlib
import io
import sys

import pytest

ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
    "SEARCH_ENDPOINT": "https://fake.search.windows.net",
    "SEARCH_INDEX": "bank-docs",
}

DOC = b"""---
doc_id: ficha-demo
title: Ficha Demo
valid_from: 2026-03-01
---

## 1. Descripcion

Texto.
"""


def _load(monkeypatch, env: dict[str, str]):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("function_app", None)
    return importlib.import_module("function_app")


@pytest.mark.parametrize("missing", list(ENV))
def test_startup_fails_when_a_setting_is_missing(monkeypatch, missing):
    env = {k: v for k, v in ENV.items() if k != missing}

    with pytest.raises(RuntimeError, match=missing):
        _load(monkeypatch, env)


def test_blob_trigger_listens_to_docs_container_via_event_grid(monkeypatch):
    module = _load(monkeypatch, ENV)

    [function] = module.app.get_functions()
    [binding] = [b.get_dict_repr() for b in function.get_bindings()]

    assert binding["type"] == "blobTrigger"
    assert binding["path"] == "docs/{name}"
    assert binding["source"] == "EventGrid"


def test_blob_is_chunked_and_indexed_into_configured_deployment(monkeypatch):
    module = _load(monkeypatch, ENV)
    calls = []
    monkeypatch.setattr(module, "index_document", lambda chunks, openai, deployment, search: calls.append(
        (chunks, openai, deployment, search)))
    [function] = module.app.get_functions()

    function.get_user_function()(io.BytesIO(DOC))

    [(chunks, openai, deployment, search)] = calls
    assert [c.id for c in chunks] == ["ficha-demo-0"]
    assert deployment == "text-embedding-3-small"
    assert openai is module.OPENAI
    assert search is module.SEARCH
