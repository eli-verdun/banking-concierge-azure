"""Gateway chat clients with Entra auth, plus direct Foundry embeddings."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache

from azure.identity import ClientSecretCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_azure_ai.embeddings import AzureAIOpenAIApiEmbeddingsModel
from langchain_openai import ChatOpenAI

# override=True so .env wins over anything exported in the shell, no matter
# which entry point imported this module first.
load_dotenv(override=True)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set. Configure it in .env; see .env.example.")
    return value


@lru_cache(maxsize=1)
def _entra_token_provider() -> Callable[[], str]:
    """Reuse Entra's cached, automatically refreshed client-credentials token.

    Restart the process after changing the Entra settings.
    """
    scope = _required_env("ENTRA_SCOPE")
    credential = ClientSecretCredential(
        tenant_id=_required_env("ENTRA_TENANT_ID"),
        client_id=_required_env("ENTRA_CLIENT_ID"),
        client_secret=_required_env("ENTRA_CLIENT_SECRET"),
    )
    return get_bearer_token_provider(credential, scope)


def _gateway_headers() -> dict[str, str]:
    """Optional subscription/API key required by the gateway itself."""
    name, value = os.getenv("GATEWAY_KEY_HEADER"), os.getenv("GATEWAY_KEY")
    return {name: value} if name and value else {}


def _gateway_query() -> dict[str, str]:
    """Optional API version for gateways exposing Azure-shaped routes."""
    version = os.getenv("GATEWAY_API_VERSION")
    return {"api-version": version} if version else {}


def _project_endpoint() -> str:
    """Return the Foundry project endpoint, or raise a clear setup error."""
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "").strip()
    if not endpoint:
        raise RuntimeError(
            "AZURE_AI_PROJECT_ENDPOINT is not set. Copy .env.example to .env and "
            "set your Azure AI Foundry project endpoint."
        )
    return endpoint


def _credential() -> str | None:
    """Return the API key when set, else None to use Entra ID.

    A string credential is treated as an API key. ``None`` tells the Foundry
    client to fall back to ``DefaultAzureCredential``.
    """
    return os.getenv("AZURE_AI_API_KEY", "").strip() or None


def make_chat_model(
    *, model: str | None = None, temperature: float = 0.2
) -> ChatOpenAI:
    """Build an OpenAI-compatible gateway chat client.

    ``model`` overrides GATEWAY_MODEL, e.g. for the offline eval judge.
    GATEWAY_BASE_URL is the complete route prefix before /chat/completions.
    """
    return ChatOpenAI(
        base_url=_required_env("GATEWAY_BASE_URL"),
        model=model or _required_env("GATEWAY_MODEL"),
        temperature=temperature,
        api_key=_entra_token_provider(),
        default_headers=_gateway_headers(),
        default_query=_gateway_query(),
        use_responses_api=False,
    )


def make_embeddings(
    *, model: str | None = None
) -> AzureAIOpenAIApiEmbeddingsModel:
    """Build the Foundry embeddings client.

    ``model`` is the Foundry embedding deployment name. It defaults to
    ``CONCIERGE_EMBEDDING_MODEL`` from the environment, then
    ``text-embedding-3-small``.
    """
    return AzureAIOpenAIApiEmbeddingsModel(
        model=model or os.getenv("CONCIERGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        project_endpoint=_project_endpoint(),
        credential=_credential(),
    )
