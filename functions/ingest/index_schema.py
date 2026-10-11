from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

EMBEDDING_DIMENSIONS = 1536


def build_index(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.STRING, key=True),
            SimpleField(name="doc_id", type=SearchFieldDataType.STRING, filterable=True),
            SearchableField(name="doc_title"),
            SearchableField(name="section"),
            SearchableField(name="content", analyzer_name="es.microsoft"),
            SearchField(
                name="content_vector",
                type="Collection(Edm.Single)",
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMENSIONS,
                vector_search_profile_name="default",
            ),
            SimpleField(
                name="valid_from", type=SearchFieldDataType.DATE_TIME_OFFSET, filterable=True, sortable=True
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="default", algorithm_configuration_name="hnsw")],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="default",
            configurations=[
                SemanticConfiguration(
                    name="default",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="doc_title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ],
        ),
    )


def ensure_index(client: SearchIndexClient, name: str) -> None:
    client.create_or_update_index(build_index(name))
