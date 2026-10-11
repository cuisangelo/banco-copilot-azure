from datetime import date
from types import SimpleNamespace

import pytest
from azure.core.exceptions import HttpResponseError
from azure.search.documents.models import IndexingResult

from chunker import Chunk
from indexer import index_document


def _chunks(n: int, doc_id: str = "ficha-oro") -> list[Chunk]:
    return [
        Chunk(
            id=f"{doc_id}-{i}",
            doc_id=doc_id,
            doc_title="Tarjeta Oro",
            section="2. Requisitos",
            content=f"texto {i}",
            valid_from=date(2026, 3, 1),
        )
        for i in range(n)
    ]


class FakeEmbeddings:
    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def create(self, *, model, input):
        self.calls.append((model, input))
        # Returned out of order on purpose: the API pairs vectors with inputs by index.
        data = [SimpleNamespace(index=i, embedding=[float(i), float(len(t))]) for i, t in enumerate(input)]
        return SimpleNamespace(data=list(reversed(data)))


class FakeSearch:
    def __init__(self, existing: list[dict] | None = None):
        self.docs = {d["id"]: d for d in existing or []}
        self.upserts: list[list[dict]] = []
        self.deleted: list[str] = []
        self.fail_keys: set[str] = set()

    def merge_or_upload_documents(self, documents):
        self.upserts.append(documents)
        results = []
        for doc in documents:
            ok = doc["id"] not in self.fail_keys
            if ok:
                self.docs[doc["id"]] = doc
            results.append(IndexingResult(key=doc["id"], succeeded=ok, status_code=200 if ok else 400,
                                          error_message=None if ok else "invalid vector"))
        return results

    def search(self, search_text, *, filter, select):
        return [{"id": d["id"]} for d in self.docs.values() if filter == f"doc_id eq '{d['doc_id']}'"]

    def delete_documents(self, documents):
        for doc in documents:
            self.deleted.append(doc["id"])
            del self.docs[doc["id"]]
        return [IndexingResult(key=d["id"], succeeded=True, status_code=200) for d in documents]


def _openai(embeddings: FakeEmbeddings) -> SimpleNamespace:
    return SimpleNamespace(embeddings=embeddings)


def test_embeds_and_upserts_in_batches_of_16():
    embeddings, search = FakeEmbeddings(), FakeSearch()

    index_document(_chunks(33), _openai(embeddings), "text-embedding-3-small", search)

    assert [len(texts) for _, texts in embeddings.calls] == [16, 16, 1]
    assert {model for model, _ in embeddings.calls} == {"text-embedding-3-small"}
    assert [len(batch) for batch in search.upserts] == [16, 16, 1]
    assert len(search.docs) == 33


def test_document_carries_contract_fields_and_its_own_vector():
    embeddings, search = FakeEmbeddings(), FakeSearch()

    index_document(_chunks(2), _openai(embeddings), "text-embedding-3-small", search)

    second = search.docs["ficha-oro-1"]
    assert set(second) == {"id", "doc_id", "doc_title", "section", "content", "content_vector", "valid_from"}
    assert second["valid_from"] == "2026-03-01T00:00:00Z"
    assert second["content"] == "texto 1"
    embedded_text = embeddings.calls[0][1][1]
    assert "texto 1" in embedded_text
    assert second["content_vector"] == [1.0, float(len(embedded_text))]


def test_failed_upsert_result_raises_with_the_key():
    search = FakeSearch()
    search.fail_keys = {"ficha-oro-1"}

    with pytest.raises(RuntimeError, match="ficha-oro-1"):
        index_document(_chunks(3), _openai(FakeEmbeddings()), "text-embedding-3-small", search)


def test_upsert_exception_propagates():
    class BrokenSearch(FakeSearch):
        def merge_or_upload_documents(self, documents):
            raise HttpResponseError(message="403 Forbidden")

    with pytest.raises(HttpResponseError):
        index_document(_chunks(1), _openai(FakeEmbeddings()), "text-embedding-3-small", BrokenSearch())


def test_reingest_with_fewer_chunks_removes_stale_chunks_of_that_document_only():
    other = {"id": "ficha-platinum-0", "doc_id": "ficha-platinum"}
    stale = {"id": "ficha-oro-5", "doc_id": "ficha-oro"}
    search = FakeSearch(existing=[other, stale])

    index_document(_chunks(2), _openai(FakeEmbeddings()), "text-embedding-3-small", search)

    assert search.deleted == ["ficha-oro-5"]
    assert set(search.docs) == {"ficha-oro-0", "ficha-oro-1", "ficha-platinum-0"}
