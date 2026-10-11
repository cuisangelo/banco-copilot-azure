from types import SimpleNamespace

from copilot_api.workflow.rag import AzureSearchRetriever


class _Results:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeSearchClient:
    def __init__(self, rows):
        self.rows = rows
        self.kwargs = None

    async def search(self, **kwargs):
        self.kwargs = kwargs
        return _Results(self.rows)


class FakeEmbeddings:
    async def get_embeddings(self, values):
        return [SimpleNamespace(vector=[0.1] * 1536)]


async def test_hybrid_semantic_query_maps_reranker_score():
    search = FakeSearchClient([
        {
            "id": "ficha-hipotecario-1",
            "doc_id": "ficha-hipotecario",
            "doc_title": "Ficha crédito hipotecario",
            "section": "Requisitos",
            "content": "Antigüedad laboral mínima de 12 meses.",
            "@search.reranker_score": 2.7,
        }
    ])

    retrieval = await AzureSearchRetriever(search, FakeEmbeddings()).search("antigüedad hipotecario", top=5)

    assert retrieval.mode == "hybrid"
    assert [(chunk.id, chunk.reranker_score) for chunk in retrieval.chunks] == [("ficha-hipotecario-1", 2.7)]
    assert search.kwargs["query_type"] == "semantic"
    assert search.kwargs["semantic_configuration_name"] == "default"
    assert search.kwargs["search_text"] == "antigüedad hipotecario"
    assert search.kwargs["vector_queries"][0].fields == "content_vector"
    assert search.kwargs["top"] == 5
