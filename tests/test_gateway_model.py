"""Exercise gateway auth and routing with real SDKs and mocked HTTP only."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import httpx
from langchain_openai import ChatOpenAI

# Load only the factory: concierge.__init__ imports the graph and contacts
# Context Hub. Tests must not load developer credentials or external services.
spec = importlib.util.spec_from_file_location(
    "gateway_model_under_test",
    Path(__file__).resolve().parents[1] / "src/concierge/azure_foundry.py",
)
factory = importlib.util.module_from_spec(spec)
with patch("dotenv.load_dotenv"):
    spec.loader.exec_module(factory)


class GatewayModelTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "GATEWAY_BASE_URL": "https://gateway.example.test/custom/llm",
                "GATEWAY_MODEL": "banking-chat",
                "ENTRA_TENANT_ID": "test-tenant",
                "ENTRA_CLIENT_ID": "test-client",
                "ENTRA_CLIENT_SECRET": "test-secret",
                "ENTRA_SCOPE": "api://test-resource/.default",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        factory._entra_token_provider.cache_clear()
        self.addCleanup(factory._entra_token_provider.cache_clear)
        self.credential_patch = patch.object(factory, "ClientSecretCredential")
        self.credential = self.credential_patch.start()
        self.addCleanup(self.credential_patch.stop)
        self.token = Mock(side_effect=["test-token-one", "test-token-two"])
        provider_patch = patch.object(
            factory, "get_bearer_token_provider", return_value=self.token
        )
        self.provider = provider_patch.start()
        self.addCleanup(provider_patch.stop)
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "banking-chat",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }],
            },
        )

    def make_model(self, **kwargs):
        transport = httpx.MockTransport(self.respond)
        sync_client = httpx.Client(transport=transport)
        async_client = httpx.AsyncClient(transport=transport)
        self.addCleanup(sync_client.close)
        self.addCleanup(lambda: asyncio.run(async_client.aclose()))

        def build(**config):
            return ChatOpenAI(
                **config, http_client=sync_client, http_async_client=async_client
            )

        with patch.object(factory, "ChatOpenAI", side_effect=build):
            return factory.make_chat_model(**kwargs)

    def test_sync_requests_resolve_token_each_time_and_keep_gateway_route(self):
        os.environ.update({
            "GATEWAY_KEY_HEADER": "X-Gateway-Key",
            "GATEWAY_KEY": "test-gateway-key",
            "GATEWAY_API_VERSION": "test-version",
        })
        model = self.make_model()
        self.token.assert_not_called()
        for _ in range(2):
            self.assertEqual(model.invoke("Hi").content, "Hello")
        self.assertEqual(self.token.call_count, 2)
        for request, token in zip(self.requests, ["test-token-one", "test-token-two"]):
            self.assertEqual(request.url.path, "/custom/llm/chat/completions")
            self.assertEqual(dict(request.url.params), {"api-version": "test-version"})
            self.assertEqual(request.headers["authorization"], f"Bearer {token}")
            self.assertEqual(request.headers["x-gateway-key"], "test-gateway-key")
            self.assertEqual(json.loads(request.content)["model"], "banking-chat")

    def test_async_requests_and_judge_override(self):
        model = self.make_model(model="banking-judge", temperature=0)

        async def invoke_twice():
            for _ in range(2):
                self.assertEqual((await model.ainvoke("Hi")).content, "Hello")

        asyncio.run(invoke_twice())
        self.assertEqual(self.token.call_count, 2)
        for request, token in zip(self.requests, ["test-token-one", "test-token-two"]):
            self.assertEqual(request.url.path, "/custom/llm/chat/completions")
            self.assertEqual(dict(request.url.params), {})
            self.assertNotIn("x-gateway-key", request.headers)
            self.assertEqual(request.headers["authorization"], f"Bearer {token}")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "banking-judge")
            self.assertEqual(body["temperature"], 0)

    def test_token_provider_is_shared_across_model_instances(self):
        self.make_model()
        self.make_model()
        self.credential.assert_called_once_with(
            tenant_id="test-tenant", client_id="test-client", client_secret="test-secret"
        )
        self.provider.assert_called_once_with(
            self.credential.return_value, "api://test-resource/.default"
        )
        self.token.assert_not_called()

    def test_required_configuration_errors_name_the_missing_variable(self):
        for name in (
            "GATEWAY_BASE_URL", "GATEWAY_MODEL", "ENTRA_TENANT_ID",
            "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_SCOPE",
        ):
            with self.subTest(name=name), patch.dict(os.environ, {name: ""}):
                factory._entra_token_provider.cache_clear()
                with self.assertRaisesRegex(RuntimeError, name):
                    factory.make_chat_model()

    def test_incomplete_optional_key_is_omitted(self):
        os.environ["GATEWAY_KEY_HEADER"] = "X-Gateway-Key"
        self.assertEqual(factory._gateway_headers(), {})
        del os.environ["GATEWAY_KEY_HEADER"]
        os.environ["GATEWAY_KEY"] = "test-gateway-key"
        self.assertEqual(factory._gateway_headers(), {})

    def test_embeddings_keep_foundry_endpoint_and_auth(self):
        os.environ.update({
            "AZURE_AI_PROJECT_ENDPOINT": "https://foundry.example.test/api/projects/test",
            "AZURE_AI_API_KEY": "test-foundry-key",
            "CONCIERGE_EMBEDDING_MODEL": "banking-embeddings",
        })
        with patch.object(factory, "AzureAIOpenAIApiEmbeddingsModel") as embeddings:
            factory.make_embeddings()
            embeddings.assert_called_once_with(
                model="banking-embeddings",
                project_endpoint="https://foundry.example.test/api/projects/test",
                credential="test-foundry-key",
            )
            del os.environ["AZURE_AI_API_KEY"]
            factory.make_embeddings()
            self.assertIsNone(embeddings.call_args.kwargs["credential"])
        self.credential.assert_not_called()


if __name__ == "__main__":
    unittest.main()
