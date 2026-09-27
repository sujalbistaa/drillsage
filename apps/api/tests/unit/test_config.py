import httpx
import pytest

from drillsage.api.app import create_app
from drillsage.core.config import Environment, Settings
from tests.conftest import UNREACHABLE_DB, open_client


def test_reads_drillsage_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRILLSAGE_ENVIRONMENT", "production")
    monkeypatch.setenv("DRILLSAGE_LOCAL_ONLY", "true")
    settings = Settings(_env_file=None)
    assert settings.environment is Environment.PRODUCTION
    assert settings.is_production
    assert settings.local_only


def test_rejects_invalid_pool_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRILLSAGE_DATABASE_POOL_SIZE", "0")
    with pytest.raises(ValueError, match="database_pool_size"):
        Settings(_env_file=None)


def test_api_key_is_read_from_standard_variable_and_never_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test-123"
    assert "sk-ant-test-123" not in repr(settings)
    assert "sk-ant-test-123" not in settings.model_dump_json()


async def test_interactive_docs_disabled_in_production() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        database_url=UNREACHABLE_DB,
        _env_file=None,
    )
    async for c in open_client(create_app(settings)):
        response: httpx.Response = await c.get("/docs")
    assert response.status_code == 404
