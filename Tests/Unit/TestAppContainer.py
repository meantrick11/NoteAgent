import pytest

from NoteAgent.AppBootstrap.ContainerAssembly import build_container
from NoteAgent.AppBootstrap.AppSettings import Settings


def test_build_container_requires_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_container(Settings(database_url=""))
