import pytest

from boot import app_boot, build_storage_providers
from src.config import Config
from src.filesystem.adapters.local_storage import LocalStorage
from src.filesystem.adapters.s3_compatible_storage import S3CompatibleStorage
from src.filesystem.file_manager import FileManager
from src.filesystem.providers import StorageProvider
from src.utils.performance import performance_tracker


@pytest.fixture(autouse=True)
async def clean_registry():
    await FileManager.reset()
    yield
    await FileManager.reset()


def test_only_local_when_no_cloud_credentials():
    providers = build_storage_providers()
    assert set(providers) == {StorageProvider.LOCAL}
    assert isinstance(providers[StorageProvider.LOCAL], LocalStorage)
    assert str(providers[StorageProvider.LOCAL].base_path) == str(
        Config.STORAGE_DIR / "app" / "media"
    )


def test_cloud_providers_registered_when_configured(monkeypatch):
    monkeypatch.setattr(Config, "AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setattr(Config, "AWS_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setattr(Config, "AWS_S3_BUCKET_NAME", "bucket")
    monkeypatch.setattr(Config, "DO_SPACES_KEY", "dk")
    monkeypatch.setattr(Config, "DO_SPACES_SECRET", "ds")
    monkeypatch.setattr(Config, "DO_SPACES_BUCKET", "space")
    monkeypatch.setattr(Config, "DO_SPACES_REGION", "ams3")
    monkeypatch.setattr(Config, "MINIO_ACCESS_KEY", "mk")
    monkeypatch.setattr(Config, "MINIO_SECRET_KEY", "ms")
    monkeypatch.setattr(Config, "MINIO_BUCKET", "mbucket")
    monkeypatch.setattr(Config, "MINIO_ENDPOINT", "http://minio:9000")

    providers = build_storage_providers()
    assert set(providers) == set(StorageProvider)
    s3 = providers[StorageProvider.S3]
    assert (
        isinstance(s3, S3CompatibleStorage) and s3.provider == "aws" and s3.bucket_name == "bucket"
    )
    do = providers[StorageProvider.DO_SPACES]
    assert do.endpoint_url == "https://ams3.digitaloceanspaces.com"
    minio = providers[StorageProvider.MINIO]
    assert minio.endpoint_url == "http://minio:9000"
    assert minio.client_config["use_ssl"] is False


def test_partial_credentials_are_ignored(monkeypatch):
    monkeypatch.setattr(Config, "AWS_ACCESS_KEY_ID", "ak")  # no secret / bucket
    assert StorageProvider.S3 not in build_storage_providers()


async def test_app_boot_registers_default_and_times_itself(capsys):
    # app_boot() installs the real logging config, so assert on the console handler output
    await app_boot()
    fm = FileManager()
    assert fm.providers == ["local"]
    assert fm.default_provider_name == "local"
    assert performance_tracker.get_boot_time() is not None
    assert "booted in development mode" in capsys.readouterr().out


async def test_app_boot_fails_when_default_not_configured(monkeypatch):
    monkeypatch.setattr(Config, "DEFAULT_FILESYSTEM", "s3")
    with pytest.raises(ValueError, match="credentials are not configured"):
        await app_boot()


async def test_app_boot_validates_config(monkeypatch):
    monkeypatch.setattr(Config, "DEFAULT_FILESYSTEM", "nope")
    with pytest.raises(ValueError, match="Invalid DEFAULT_FILESYSTEM"):
        await app_boot()


async def test_app_boot_replaces_previous_registry(monkeypatch, tmp_path):
    fm = FileManager()
    await fm.add_provider(StorageProvider.S3, LocalStorage(str(tmp_path)), set_as_default=True)
    await app_boot()
    assert fm.providers == ["local"]
