import azure.functions as func
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from bank_contracts.settings import require_env
from openai import AzureOpenAI

from chunker import chunk_document
from indexer import index_document

CREDENTIAL = DefaultAzureCredential()
OPENAI = AzureOpenAI(
    azure_endpoint=require_env("AZURE_OPENAI_ENDPOINT"),
    api_version=require_env("AZURE_OPENAI_API_VERSION"),
    azure_ad_token_provider=get_bearer_token_provider(CREDENTIAL, "https://cognitiveservices.azure.com/.default"),
)
EMBEDDING_DEPLOYMENT = require_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
SEARCH = SearchClient(require_env("SEARCH_ENDPOINT"), require_env("SEARCH_INDEX"), CREDENTIAL)

app = func.FunctionApp()


@app.blob_trigger(arg_name="blob", path="docs/{name}", connection="DocsStorage", source=func.BlobSource.EVENT_GRID)
def ingest_blob(blob: func.InputStream) -> None:
    index_document(chunk_document(blob.read().decode("utf-8")), OPENAI, EMBEDDING_DEPLOYMENT, SEARCH)
