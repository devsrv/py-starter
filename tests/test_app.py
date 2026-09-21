import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from src.config import Config
from src.filesystem.file_manager import FileManager
from src.utils.rate_limiter import limiter

VALID_HEADERS = {"X-API-KEY": "test-secret"}


@pytest.fixture
def client():
    limiter.reset()
    with TestClient(app) as c:
        yield c
    limiter.reset()


class TestHealth:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert body["mode"] == "development"
        assert body["boot_time"] is not None and body["boot_time"] >= 0
        assert "T" in body["timestamp"]

    def test_lifespan_booted_file_manager(self, client):
        fm = FileManager()
        assert fm.is_initialized
        assert fm.default_provider_name == "local"


class TestTestEndpoint:
    def test_missing_api_key(self, client):
        res = client.post("/test", json={"org_id": 1})
        assert res.status_code == 401
        assert "missing" in res.json()["detail"]

    def test_wrong_api_key(self, client):
        res = client.post("/test", json={"org_id": 1}, headers={"X-API-KEY": "nope"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid API key"

    def test_valid_request(self, client):
        res = client.post("/test", json={"org_id": 7, "metadata": {"a": 1}}, headers=VALID_HEADERS)
        assert res.status_code == 200
        assert res.json() == {"message": "Test function executed successfully", "org_id": 7}

    def test_header_name_is_case_insensitive(self, client):
        res = client.post("/test", json={"org_id": 7}, headers={"x-api-key": "test-secret"})
        assert res.status_code == 200

    def test_invalid_body(self, client):
        res = client.post("/test", json={"org_id": 0}, headers=VALID_HEADERS)
        assert res.status_code == 422
        res = client.post("/test", json={}, headers=VALID_HEADERS)
        assert res.status_code == 422

    def test_secret_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(Config, "HTTP_SECRET", None)
        res = client.post("/test", json={"org_id": 1}, headers=VALID_HEADERS)
        assert res.status_code == 500
        assert res.json()["detail"] == "API key not configured"


class TestRateLimit:
    def test_test_endpoint_limit(self, client):
        for _ in range(5):
            assert (
                client.post("/test", json={"org_id": 1}, headers=VALID_HEADERS).status_code == 200
            )
        res = client.post("/test", json={"org_id": 1}, headers=VALID_HEADERS)
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["error"]

    def test_health_has_a_limit(self, client):
        statuses = {client.get("/health").status_code for _ in range(61)}
        assert statuses == {200, 429}


class TestCors:
    def test_dev_allows_any_origin(self, client):
        res = client.options(
            "/health",
            headers={"Origin": "https://random.example", "Access-Control-Request-Method": "GET"},
        )
        assert res.status_code == 200
        assert res.headers["access-control-allow-origin"] in ("*", "https://random.example")


class TestErrors:
    def test_unhandled_exception_returns_json_500(self):
        @app.get("/__boom")
        async def boom():
            raise RuntimeError("kaboom")

        limiter.reset()
        with TestClient(app, raise_server_exceptions=False) as c:
            res = c.get("/__boom")
        assert res.status_code == 500
        assert res.json() == {"error": "Internal server error"}

    def test_openapi_lists_routes(self, client):
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == f"{Config.APP_NAME} API"
        assert "/health" in schema["paths"]
        assert "/test" in schema["paths"]


def test_module_wires_limiter_state():
    assert app.state.limiter is limiter
    assert app_module.verify_api_key is not None
