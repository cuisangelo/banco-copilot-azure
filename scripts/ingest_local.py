"""Creates the search index and ingests data/docs from a laptop, bypassing Blob and Event Grid.

Run with `uv run --all-packages python scripts/ingest_local.py` after `az login`. The signed-in
identity needs Search Service Contributor, Search Index Data Contributor and Cognitive Services
OpenAI User on the target resources.
"""

from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from bank_contracts.settings import require_env
from openai import AzureOpenAI

from index_schema import ensure_index
from indexer import ingest_directory

DOCS = Path(__file__).resolve().parents[1] / "data" / "docs"


def main() -> None:
    credential = DefaultAzureCredential()
    openai = AzureOpenAI(
        azure_endpoint=require_env("AZURE_OPENAI_ENDPOINT"),
        api_version=require_env("AZURE_OPENAI_API_VERSION"),
        azure_ad_token_provider=get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default"),
    )
    deployment = require_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    search_endpoint = require_env("SEARCH_ENDPOINT")
    index_name = require_env("SEARCH_INDEX")

    ensure_index(SearchIndexClient(search_endpoint, credential), index_name)
    ingested = ingest_directory(DOCS, openai, deployment, SearchClient(search_endpoint, index_name, credential))
    print(f"Ingested {len(ingested)} documents into {index_name}: {', '.join(ingested)}")


if __name__ == "__main__":
    main()
