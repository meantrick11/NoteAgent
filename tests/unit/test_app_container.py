import pytest

from noteagent.bootstrap.app import build_container
from noteagent.bootstrap.settings import Settings


def test_build_container_requires_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_container(Settings(database_url=""))
