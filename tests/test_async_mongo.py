from unittest.mock import AsyncMock, MagicMock

import pytest

import src.db.async_mongo as mongo_module
from src.config import Config
from src.db.async_mongo import MongoDBManager, get_collection, get_database, mongo_manager
from src.db.mongo import mongo_client_kwargs


class FakeDatabase(dict):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.command = AsyncMock(return_value={"collections": 3, "dataSize": 99})

    def __getitem__(self, key):
        return f"collection:{self.name}.{key}"


class FakeMotorClient:
    instances: list["FakeMotorClient"] = []
    ping_error: Exception | None = None

    def __init__(self, uri, **options):
        self.uri = uri
        self.options = options
        self.closed = False
        self.admin = MagicMock()
        self.admin.command = AsyncMock(side_effect=self._ping)
        FakeMotorClient.instances.append(self)

    async def _ping(self, cmd):
        if FakeMotorClient.ping_error:
            raise FakeMotorClient.ping_error
        return {"ok": 1}

    def __getitem__(self, name):
        return FakeDatabase(name)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_motor(monkeypatch):
    FakeMotorClient.instances = []
    FakeMotorClient.ping_error = None
    monkeypatch.setattr(mongo_module, "AsyncIOMotorClient", FakeMotorClient)
    # start each test from a clean singleton
    mongo_manager.client = None
    mongo_manager.db = None
    mongo_manager._initialized = False
    mongo_manager._last_ping = 0.0
    mongo_manager.db_name = Config.MONGO_DB_NAME
    yield FakeMotorClient
    mongo_manager.client = None
    mongo_manager.db = None
    mongo_manager._initialized = False


def test_singleton():
    assert MongoDBManager() is mongo_manager
    assert MongoDBManager() is MongoDBManager()


class TestTlsOption:
    def test_unset_lets_uri_decide(self, monkeypatch):
        monkeypatch.setattr(Config, "MONGO_TLS", None)
        assert mongo_client_kwargs() == {}

    @pytest.mark.parametrize("value", [True, False])
    def test_explicit_is_forwarded(self, monkeypatch, value):
        monkeypatch.setattr(Config, "MONGO_TLS", value)
        assert mongo_client_kwargs() == {"tls": value}


class TestInitialize:
    async def test_initialize_connects_and_pings(self, fake_motor):
        await mongo_manager.initialize()
        assert mongo_manager.is_initialized
        [client] = fake_motor.instances
        assert client.uri == Config.MONGO_URI
        assert client.options["maxPoolSize"] == 20
        assert client.options["minPoolSize"] == 10
        assert "tls" not in client.options
        client.admin.command.assert_awaited_with("ping")
        assert mongo_manager.db.name == Config.MONGO_DB_NAME

    async def test_initialize_is_idempotent(self, fake_motor):
        await mongo_manager.initialize()
        await mongo_manager.initialize(db_name="other")
        assert len(fake_motor.instances) == 1
        assert mongo_manager.db_name == Config.MONGO_DB_NAME

    async def test_custom_db_and_pool_size_keeps_min_below_max(self, fake_motor):
        await mongo_manager.initialize(db_name="custom", max_pool_size=4)
        [client] = fake_motor.instances
        assert client.options["maxPoolSize"] == 4
        assert client.options["minPoolSize"] == 4
        assert mongo_manager.db.name == "custom"

    async def test_tls_forwarded_when_set(self, fake_motor, monkeypatch):
        monkeypatch.setattr(Config, "MONGO_TLS", True)
        await mongo_manager.initialize()
        assert fake_motor.instances[0].options["tls"] is True

    async def test_connect_failure_cleans_up_and_raises(self, fake_motor, monkeypatch):
        monkeypatch.setattr(mongo_module, "async_report", AsyncMock())
        fake_motor.ping_error = ConnectionError("refused")
        # skip backoff delays
        monkeypatch.setattr(
            mongo_module.MongoDBManager,
            "_ping_with_retry",
            mongo_module.MongoDBManager._ping_with_retry.__wrapped__,
        )
        with pytest.raises(ConnectionError):
            await mongo_manager.initialize()
        assert mongo_manager.client is None
        assert not mongo_manager.is_initialized
        assert fake_motor.instances[0].closed


class TestAccess:
    async def test_get_collection_and_database(self, fake_motor):
        await mongo_manager.initialize()
        assert mongo_manager.get_collection("users") == "collection:test_db.users"
        assert mongo_manager.get_database().name == "test_db"
        assert mongo_manager.get_database("analytics").name == "analytics"

    async def test_convenience_functions(self, fake_motor):
        await mongo_manager.initialize()
        assert await get_collection("users") == "collection:test_db.users"
        assert (await get_database("x")).name == "x"

    async def test_errors_before_initialize(self, fake_motor):
        with pytest.raises(RuntimeError, match="not initialized"):
            mongo_manager.get_collection("x")
        with pytest.raises(RuntimeError, match="not initialized"):
            mongo_manager.get_database()
        with pytest.raises(RuntimeError, match="not initialized"):
            await mongo_manager.ensure_connected()


class TestEnsureConnected:
    async def test_pings_are_throttled(self, fake_motor):
        await mongo_manager.initialize()
        client = fake_motor.instances[0]
        pings_after_init = client.admin.command.await_count
        await mongo_manager.ensure_connected()
        await mongo_manager.ensure_connected()
        assert client.admin.command.await_count == pings_after_init

    async def test_pings_again_after_interval(self, fake_motor):
        await mongo_manager.initialize()
        client = fake_motor.instances[0]
        before = client.admin.command.await_count
        mongo_manager._last_ping = 0.0
        await mongo_manager.ensure_connected()
        assert client.admin.command.await_count == before + 1

    async def test_reconnects_when_ping_fails(self, fake_motor, monkeypatch):
        report = AsyncMock()
        monkeypatch.setattr(mongo_module, "async_report", report)
        await mongo_manager.initialize()
        first = fake_motor.instances[0]
        mongo_manager._last_ping = 0.0

        # First ping (the health check) fails, the one inside _connect succeeds
        calls = {"n": 0}

        async def flaky(cmd):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("gone")
            return {"ok": 1}

        first.admin.command = AsyncMock(side_effect=flaky)
        await mongo_manager.ensure_connected()
        assert first.closed
        assert len(fake_motor.instances) == 2
        assert mongo_manager.client is fake_motor.instances[1]
        report.assert_awaited()

    async def test_reconnects_when_client_missing(self, fake_motor):
        await mongo_manager.initialize()
        mongo_manager.client = None
        await mongo_manager.ensure_connected()
        assert mongo_manager.client is fake_motor.instances[1]


class TestCloseAndHealth:
    async def test_close(self, fake_motor):
        await mongo_manager.initialize()
        await mongo_manager.close()
        assert fake_motor.instances[0].closed
        assert mongo_manager.client is None
        assert not mongo_manager.is_initialized
        await mongo_manager.close()  # idempotent

    async def test_health_check(self, fake_motor):
        await mongo_manager.initialize()
        health = await mongo_manager.health_check()
        assert health == {
            "status": "healthy",
            "database": "test_db",
            "collections": 3,
            "dataSize": 99,
        }

    async def test_health_check_unhealthy(self, fake_motor):
        health = await mongo_manager.health_check()
        assert health["status"] == "unhealthy"
        assert "not initialized" in health["error"]
