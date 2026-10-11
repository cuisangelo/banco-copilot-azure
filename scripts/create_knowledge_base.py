"""Creates or updates the bank-docs knowledge source and knowledge base for RETRIEVAL_MODE=agentic.

Run with `uv run --all-packages python scripts/create_knowledge_base.py` after `az login`; every PUT
is create-or-update, so running it again converges to the same definitions. The signed-in identity
needs Search Service Contributor on the search service.

Agentic retrieval then also needs, outside this script:
- the search service on Basic tier or higher: on Free it cannot call the planning model with its
  managed identity, and the planner never gets a key;
- that managed identity with Cognitive Services User on the Foundry resource.
"""

import httpx
from azure.identity import AzureCliCredential
from bank_contracts.settings import require_env

from copilot_api.workflow.agentic import (
    AGENTIC_API_VERSION,
    KNOWLEDGE_BASE,
    KNOWLEDGE_SOURCE,
    SEARCH_SCOPE,
    knowledge_base_definition,
    knowledge_source_definition,
)


def main() -> None:
    endpoint = require_env("SEARCH_ENDPOINT")
    token = AzureCliCredential().get_token(SEARCH_SCOPE).token
    with httpx.Client(
        base_url=endpoint,
        params={"api-version": AGENTIC_API_VERSION},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as http:
        source = knowledge_source_definition(require_env("SEARCH_INDEX"))
        http.put(f"/knowledgesources/{KNOWLEDGE_SOURCE}", json=source).raise_for_status()
        base = knowledge_base_definition(require_env("AZURE_OPENAI_ENDPOINT"), require_env("AZURE_OPENAI_CHAT_DEPLOYMENT"))
        http.put(f"/knowledgebases/{KNOWLEDGE_BASE}", json=base).raise_for_status()
    print(f"Knowledge base {KNOWLEDGE_BASE} over {KNOWLEDGE_SOURCE} is up to date ({AGENTIC_API_VERSION}).")


if __name__ == "__main__":
    main()
