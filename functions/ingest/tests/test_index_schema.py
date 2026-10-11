from index_schema import build_index, ensure_index


def _fields() -> dict[str, dict]:
    return {f["name"]: f for f in build_index("bank-docs").as_dict()["fields"]}


def test_fields_match_contract():
    fields = _fields()

    assert list(fields) == ["id", "doc_id", "doc_title", "section", "content", "content_vector", "valid_from"]
    assert fields["id"]["key"] is True
    assert fields["doc_id"]["filterable"] is True
    assert fields["doc_title"]["searchable"] is True
    assert fields["section"]["searchable"] is True
    assert fields["section"]["retrievable"] is True
    assert fields["content"]["searchable"] is True
    assert fields["content"]["analyzer"] == "es.microsoft"
    assert fields["valid_from"]["type"] == "Edm.DateTimeOffset"
    assert fields["valid_from"]["filterable"] is True
    assert fields["valid_from"]["sortable"] is True
    assert all(fields[n]["type"] == "Edm.String" for n in ("id", "doc_id", "doc_title", "section", "content"))


def test_vector_field_uses_hnsw_default_profile_with_1536_dimensions():
    index = build_index("bank-docs").as_dict()
    vector = _fields()["content_vector"]

    assert vector["type"] == "Collection(Edm.Single)"
    assert vector["dimensions"] == 1536
    assert vector["vectorSearchProfile"] == "default"
    [profile] = index["vectorSearch"]["profiles"]
    [algorithm] = index["vectorSearch"]["algorithms"]
    assert profile["name"] == "default"
    assert profile["algorithm"] == algorithm["name"]
    assert algorithm["kind"] == "hnsw"


def test_semantic_configuration_default_uses_title_and_content():
    semantic = build_index("bank-docs").as_dict()["semantic"]
    [config] = semantic["configurations"]

    assert semantic["defaultConfiguration"] == "default"
    assert config["name"] == "default"
    assert config["prioritizedFields"]["titleField"] == {"fieldName": "doc_title"}
    assert config["prioritizedFields"]["prioritizedContentFields"] == [{"fieldName": "content"}]


def test_ensure_index_creates_or_updates_the_named_index():
    class FakeIndexClient:
        def __init__(self):
            self.indexes = []

        def create_or_update_index(self, index):
            self.indexes.append(index)
            return index

    client = FakeIndexClient()
    ensure_index(client, "bank-docs")

    assert [i.name for i in client.indexes] == ["bank-docs"]
