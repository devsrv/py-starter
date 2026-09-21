from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.config import Config, env_bool, env_int, env_str


class TestEnvHelpers:
    def test_env_str_default_when_missing_or_blank(self, monkeypatch):
        monkeypatch.delenv("X_STR", raising=False)
        assert env_str("X_STR", "fallback") == "fallback"
        monkeypatch.setenv("X_STR", "   ")
        assert env_str("X_STR", "fallback") == "fallback"

    def test_env_str_strips(self, monkeypatch):
        monkeypatch.setenv("X_STR", "  value ")
        assert env_str("X_STR") == "value"

    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " y ", "t"])
    def test_env_bool_truthy(self, monkeypatch, raw):
        monkeypatch.setenv("X_BOOL", raw)
        assert env_bool("X_BOOL", default=False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "off", "n", "f"])
    def test_env_bool_falsy(self, monkeypatch, raw):
        monkeypatch.setenv("X_BOOL", raw)
        assert env_bool("X_BOOL", default=True) is False

    def test_env_bool_default_when_unset_or_blank(self, monkeypatch):
        monkeypatch.delenv("X_BOOL", raising=False)
        assert env_bool("X_BOOL", default=None) is None
        assert env_bool("X_BOOL", default=True) is True
        monkeypatch.setenv("X_BOOL", "")
        assert env_bool("X_BOOL", default=False) is False

    def test_env_bool_rejects_garbage(self, monkeypatch):
        monkeypatch.setenv("X_BOOL", "maybe")
        with pytest.raises(ValueError, match="not a boolean"):
            env_bool("X_BOOL", default=True)

    def test_env_int(self, monkeypatch):
        monkeypatch.setenv("X_INT", " 42 ")
        assert env_int("X_INT", 1) == 42
        monkeypatch.setenv("X_INT", "")
        assert env_int("X_INT", 7) == 7
        monkeypatch.delenv("X_INT")
        assert env_int("X_INT", 9) == 9

    def test_env_int_rejects_garbage(self, monkeypatch):
        monkeypatch.setenv("X_INT", "forty")
        with pytest.raises(ValueError, match="not an integer"):
            env_int("X_INT", 1)


class TestConfig:
    def test_test_environment_is_applied(self):
        assert Config.APP_MODE == "development"
        assert Config.DEBUG is True
        assert Config.HTTP_SECRET == "test-secret"
        assert ZoneInfo("America/New_York") == Config.TZ
        assert Config.MONGO_TLS is None

    def test_paths_are_absolute_and_under_storage_dir(self):
        assert Config.BASE_DIR.is_absolute()
        assert (Config.BASE_DIR / "app.py").exists()
        assert Config.LOG_DIR == Config.STORAGE_DIR / "logs"
        assert Config.LOG_DIR.is_dir()
        assert Path(Config.LOCAL_STORAGE_FULL_PATH) == Config.STORAGE_DIR / "app" / "media"

    def test_get_absolute_path(self):
        assert Config.get_absolute_path("storage/x") == Config.BASE_DIR / "storage" / "x"

    def test_logging_config_uses_daily_handlers_with_tz(self):
        handlers = Config.LOGGING["handlers"]
        assert handlers["file_daily"]["tz"] == Config.TZ
        assert "{date}" in handlers["file_daily"]["filename_pattern"]
        assert handlers["error_daily"]["level"] == "ERROR"
        assert Config.LOGGING["loggers"]["pymongo"]["level"] == "WARNING"

    def test_validate_passes_in_test_environment(self):
        Config.validate()

    def test_validate_rejects_bad_filesystem(self, monkeypatch):
        monkeypatch.setattr(Config, "DEFAULT_FILESYSTEM", "dropbox")
        with pytest.raises(ValueError, match="Invalid DEFAULT_FILESYSTEM"):
            Config.validate()

    def test_validate_rejects_bad_mode(self, monkeypatch):
        monkeypatch.setattr(Config, "APP_MODE", "staging")
        with pytest.raises(ValueError, match="Invalid APP_MODE"):
            Config.validate()

    def test_validate_production_requirements(self, monkeypatch):
        monkeypatch.setattr(Config, "APP_MODE", "production")
        monkeypatch.setattr(Config, "HTTP_SECRET", None)
        monkeypatch.setattr(Config, "ALLOWED_ORIGINS", "")
        with pytest.raises(ValueError) as exc:
            Config.validate()
        assert "HTTP_SECRET is required" in str(exc.value)
        assert "ALLOWED_ORIGINS is required" in str(exc.value)

    def test_validate_production_ok_when_configured(self, monkeypatch):
        monkeypatch.setattr(Config, "APP_MODE", "production")
        monkeypatch.setattr(Config, "HTTP_SECRET", "s")
        monkeypatch.setattr(Config, "ALLOWED_ORIGINS", "https://example.com")
        Config.validate()


class TestAllowedOrigins:
    def test_parses_and_strips(self, monkeypatch):
        monkeypatch.setattr(Config, "ALLOWED_ORIGINS", " https://a.com , https://b.com,, ")
        assert Config.allowed_origins() == ["https://a.com", "https://b.com"]

    def test_dev_empty_means_allow_all(self, monkeypatch):
        monkeypatch.setattr(Config, "APP_MODE", "development")
        monkeypatch.setattr(Config, "ALLOWED_ORIGINS", "")
        assert Config.allowed_origins() == ["*"]

    def test_production_empty_means_none(self, monkeypatch):
        monkeypatch.setattr(Config, "APP_MODE", "production")
        monkeypatch.setattr(Config, "ALLOWED_ORIGINS", "")
        assert Config.allowed_origins() == []
