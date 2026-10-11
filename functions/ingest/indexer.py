from pathlib import Path

from azure.search.documents import SearchClient
from openai import AzureOpenAI

from chunker import Chunk, chunk_document

EMBEDDING_BATCH_SIZE = 16


def ingest_directory(path: Path, openai: AzureOpenAI, deployment: str, search: SearchClient) -> list[str]:
    ingested = []
    for doc in sorted(path.glob("*.md")):
        chunks = chunk_document(doc.read_text(encoding="utf-8"))
        index_document(chunks, openai, deployment, search)
        ingested.append(chunks[0].doc_id)
    return ingested


def index_document(chunks: list[Chunk], openai: AzureOpenAI, deployment: str, search: SearchClient) -> None:
    """Upserts the chunks of one document and removes chunks it no longer has."""
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        # Title and section go into the embedding so short sections keep their topic.
        texts = [f"{c.doc_title} — {c.section}\n\n{c.content}" for c in batch]
        response = openai.embeddings.create(model=deployment, input=texts)
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        documents = [_to_document(chunk, vector) for chunk, vector in zip(batch, vectors, strict=True)]
        _raise_on_failures(search.merge_or_upload_documents(documents))

    doc_id = chunks[0].doc_id
    current = {c.id for c in chunks}
    existing = search.search("*", filter=f"doc_id eq '{doc_id.replace("'", "''")}'", select=["id"])
    stale = [{"id": doc["id"]} for doc in existing if doc["id"] not in current]
    if stale:
        _raise_on_failures(search.delete_documents(stale))


def _to_document(chunk: Chunk, vector: list[float]) -> dict:
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "doc_title": chunk.doc_title,
        "section": chunk.section,
        "content": chunk.content,
        "content_vector": vector,
        "valid_from": f"{chunk.valid_from.isoformat()}T00:00:00Z",
    }


def _raise_on_failures(results) -> None:
    failed = [f"{r.key}: {r.error_message}" for r in results if not r.succeeded]
    if failed:
        raise RuntimeError(f"search indexing failed for {failed}")
