from unittest.mock import MagicMock

import pytest

import src.db.mongo as mongo_module
from src.config import Config
from src.db.mongo import Mongo


class FakeClient:
    instances: list["FakeClient"] = []
    fail_ping = False

    def __init__(self, uri, **kwargs):
        self.uri = uri
        self.kwargs = kwargs
        self.closed = False
        self.admin = MagicMock()
        self.admin.command = MagicMock(side_effect=self._ping)
        FakeClient.instances.append(self)

    def _ping(self, cmd):
        if FakeClient.fail_ping:
            raise ConnectionError("down")
        return {"ok": 1}

    def __getitem__(self, name):
        db = MagicMock(name=f"db:{name}")
        db.__getitem__ = lambda self_, key: f"{name}.{key}"
        return db

    def close(self):
        self.closed = True


@pytest.fixture
def fake_client(monkeypatch):
    FakeClient.instances = []
    FakeClient.fail_ping = False
    monkeypatch.setattr(mongo_module, "MongoClient", FakeClient)
    return FakeClient


def test_connects_on_construction_with_config_defaults(fake_client):
    m = Mongo()
    assert m.client is fake_client.instances[0]
    assert m.client.uri == Config.MONGO_URI
    assert m.database_name == Config.MONGO_DB_NAME
    m.client.admin.command.assert_called_with("ping")


def test_custom_uri_and_tls(fake_client, monkeypatch):
    monkeypatch.setattr(Config, "MONGO_TLS", False)
    m = Mongo("mongodb://custom:1/", "otherdb")
    assert m.client.uri == "mongodb://custom:1/"
    assert m.client.kwargs == {"tls": False}
    assert m.get_collection("users") == "otherdb.users"


def test_connect_failure_raises_and_cleans_up(fake_client):
    fake_client.fail_ping = True
    with pytest.raises(ConnectionError):
        Mongo()
    assert fake_client.instances[0].closed


def test_ensure_connected_reconnects_on_failure(fake_client):
    m = Mongo()
    first = m.client
    fake_client.fail_ping = True
    first.admin.command = MagicMock(side_effect=ConnectionError("gone"))
    fake_client.fail_ping = False
    m.ensure_connected()
    assert first.closed
    assert m.client is fake_client.instances[1]


def test_ensure_connected_after_close(fake_client):
    m = Mongo()
    m.close_connection()
    assert m.client is None
    with pytest.raises(RuntimeError):
        m.get_collection("x")
    m.ensure_connected()
    assert m.client is fake_client.instances[1]


def test_close_is_idempotent(fake_client):
    m = Mongo()
    m.close_connection()
    m.close_connection()
    assert fake_client.instances[0].closed
