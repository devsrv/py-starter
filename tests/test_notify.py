import asyncio
import logging

import aiohttp
import pytest

import src.report.notify as notify_module
from src.config import Config
from src.report.notify import NotificationType, async_report, build_card, report


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientError(f"HTTP {self.status}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    posts: list = []
    response = FakeResponse()
    error: Exception | None = None

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None):
        FakeSession.posts.append((url, json))
        if FakeSession.error:
            raise FakeSession.error
        return FakeSession.response


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(Config, "APP_MODE", "production")
    monkeypatch.setattr(Config, "GOOGLE_CHAT_DEV_TEAM_WEBHOOK", "https://chat.example/hook")
    FakeSession.posts = []
    FakeSession.response = FakeResponse()
    FakeSession.error = None
    monkeypatch.setattr(notify_module.aiohttp, "ClientSession", FakeSession)
    return FakeSession


def test_build_card_shape():
    card = build_card("hello", NotificationType.WARNING)
    inner = card["cardsV2"][0]["card"]
    assert inner["header"]["title"].endswith("WARNING")
    assert inner["sections"][0]["widgets"][0]["textParagraph"]["text"] == "hello"
    assert build_card("x", NotificationType.EXCEPTION)["cardsV2"][0]["card"]["header"][
        "title"
    ].endswith("ERROR")
    assert (
        "EMERGENCY"
        in build_card("x", NotificationType.EMERGENCY)["cardsV2"][0]["card"]["header"]["title"]
    )


async def test_non_production_only_logs(caplog):
    with caplog.at_level(logging.DEBUG, logger="src.report.notify"):
        assert await async_report("just a log", NotificationType.ERROR) is True
    record = next(r for r in caplog.records if "just a log" in r.getMessage())
    assert record.levelno == logging.ERROR
    assert "[ERROR]" in record.getMessage()


async def test_production_posts_card(production):
    assert await async_report("deploy done", NotificationType.INFO) is True
    url, payload = production.posts[0]
    assert url == "https://chat.example/hook"
    assert payload == build_card("deploy done", NotificationType.INFO)


async def test_explicit_webhook_overrides_config(production):
    await async_report("x", webhook_url="https://other.example/hook")
    assert production.posts[0][0] == "https://other.example/hook"


async def test_missing_webhook_returns_false(production, monkeypatch, caplog):
    monkeypatch.setattr(Config, "GOOGLE_CHAT_DEV_TEAM_WEBHOOK", "")
    with caplog.at_level(logging.ERROR):
        assert await async_report("lost") is False
    assert production.posts == []
    assert "not configured" in caplog.text


async def test_http_error_returns_false(production):
    production.response = FakeResponse(status=500)
    assert await async_report("x") is False


async def test_timeout_returns_false(production):
    production.error = TimeoutError()
    assert await async_report("x") is False


async def test_client_error_returns_false(production):
    production.error = aiohttp.ClientConnectionError("boom")
    assert await async_report("x") is False


async def test_unexpected_error_returns_false(production):
    production.error = RuntimeError("weird")
    assert await async_report("x") is False


class TestSyncReport:
    def test_outside_event_loop_runs_to_completion(self, caplog):
        with caplog.at_level(logging.INFO):
            assert report("sync message", NotificationType.WARNING) is True
        assert "sync message" in caplog.text

    async def test_inside_event_loop_schedules_task(self, caplog):
        with caplog.at_level(logging.INFO):
            assert report("scheduled message") is True
            assert "scheduled message" not in caplog.text  # not yet run
            await asyncio.sleep(0)
            await asyncio.gather(*notify_module._background_tasks)
            await asyncio.sleep(0)  # let the done-callback run
        assert "scheduled message" in caplog.text
        assert notify_module._background_tasks == set()
