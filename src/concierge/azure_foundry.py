"""Azure AI Foundry model factory.

This module builds the two model clients the concierge needs — a chat model and
an embeddings model — and points both at an Azure AI Foundry project. Inference
runs directly against Foundry. There is no gateway in the request path.

Both clients read one endpoint and follow one auth rule:

- Endpoint: ``AZURE_AI_PROJECT_ENDPOINT`` (the Foundry project endpoint, e.g.
  ``https://<resource>.services.ai.azure.com/api/projects/<project>``).
- Auth: set ``AZURE_AI_API_KEY`` to use an API key. Leave it empty to use
  Microsoft Entra ID through ``DefaultAzureCredential`` (managed identity,
  ``az login``, environment credentials, and so on).

The Foundry clients (`AzureAIOpenAIApiChatModel`, `AzureAIOpenAIApiEmbeddingsModel`)
subclass the OpenAI clients. A string credential is used as the API key. A
``None`` credential falls back to ``DefaultAzureCredential``.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from langchain_azure_ai.embeddings import AzureAIOpenAIApiEmbeddingsModel

# override=True so .env wins over anything exported in the shell, no matter
# which entry point imported this module first.
load_dotenv(override=True)

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


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
) -> AzureAIOpenAIApiChatModel:
    """Build the Foundry chat client.

    ``model`` is the Foundry model deployment name. It defaults to
    ``CONCIERGE_MODEL`` from the environment, then ``gpt-4o-mini``.
    """
    return AzureAIOpenAIApiChatModel(
        model=model or os.getenv("CONCIERGE_MODEL", DEFAULT_CHAT_MODEL),
        temperature=temperature,
        project_endpoint=_project_endpoint(),
        credential=_credential(),
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
