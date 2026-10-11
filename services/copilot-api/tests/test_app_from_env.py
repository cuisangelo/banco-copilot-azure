import pytest
from agent_framework.openai import OpenAIChatCompletionClient

from copilot_api.main import deps_from_env

REQUIRED = [
    "APIM_BASE_URL",
    "APIM_SUBSCRIPTION_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "SEARCH_ENDPOINT",
    "SEARCH_INDEX",
    "CONTENT_SAFETY_ENDPOINT",
    "COSMOS_ENDPOINT",
    "COSMOS_DATABASE",
    "MCP_BANK_URL",
    "PERSONA_PRIVATE_KEY_PEM",
    "PERSONA_KEY_ID",
    "DAILY_TOKEN_CAP",
    "CORS_ORIGIN",
]


@pytest.fixture
def env(monkeypatch, private_key_pem):
    values = {
        "APIM_BASE_URL": "https://apim.example",
        "APIM_SUBSCRIPTION_KEY": "sub-key",
        "AZURE_OPENAI_ENDPOINT": "https://aoai.example",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4.1-mini",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
        "AZURE_OPENAI_API_VERSION": "2024-10-21",
        "SEARCH_ENDPOINT": "https://search.example",
        "SEARCH_INDEX": "bank-docs",
        "CONTENT_SAFETY_ENDPOINT": "https://cs.example",
        "COSMOS_ENDPOINT": "https://cosmos.example:443/",
        "COSMOS_DATABASE": "copilot",
        "MCP_BANK_URL": "https://mcp-bank.internal/mcp",
        "PERSONA_PRIVATE_KEY_PEM": private_key_pem,
        "PERSONA_KEY_ID": "persona-1",
        "DAILY_TOKEN_CAP": "2000000",
        "CORS_ORIGIN": "https://web.example",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.mark.parametrize("missing", REQUIRED)
def test_every_setting_is_required(env, missing):
    env.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        deps_from_env()


def test_chat_goes_through_chat_completions_with_the_configured_api_version(env):
    deps = deps_from_env()

    client = deps.llm._client
    assert isinstance(client, OpenAIChatCompletionClient)
    assert client.client._api_version == "2024-10-21"
    assert deps.llm.model == "gpt-4.1-mini"
