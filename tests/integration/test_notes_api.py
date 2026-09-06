from pathlib import Path

from fastapi.testclient import TestClient

from noteagent.bootstrap.app import AppContainer, create_app
from noteagent.bootstrap.settings import Settings
from noteagent.chat.history import ConversationStore
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore


class FakeAgent:
    async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
        yield {"event": "token", "data": "ok"}

    def review(self, thread_id: str, action: str, write_action=None, file_name=None):
        return {"status": "rejected"}


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


def _client(tmp_path: Path) -> tuple[TestClient, FileNoteRepository, RetrievalService]:
    notes = FileNoteRepository(tmp_path / "notes")
    retrieval = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "notes_api"),
    )
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    container = AppContainer(
        settings=Settings(notes_dir=tmp_path / "notes", chroma_dir=tmp_path / "chroma"),
        notes=notes,
        retrieval=retrieval,
        chat_agent=FakeAgent(),  # type: ignore[arg-type]
        engine=engine,
        history=ConversationStore(create_session_factory(engine)),
    )
    return TestClient(create_app(container)), notes, retrieval


def test_save_note_reindexes_new_body(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "旧句不会被检索到。\n", append=True)
    retrieval.index_note("Go.md")

    response = client.put("/notes/Go.md", json={"content": "# Go\n\n注意力机制用 Query Key Value。\n"})
    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "Go.md"
    assert body["indexed"] is True
    assert "注意力机制" in notes.read("Go.md")
    hits = retrieval.search("注意力", top_k=2)
    assert hits
    assert hits[0].metadata["file_name"] == "Go.md"


def test_move_note_drops_old_vectors(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value 计算权重。\n", append=True)
    retrieval.index_note("Go.md")
    client.post("/notes/folders", json={"name": "Lang"})

    response = client.post("/notes/move", json={"from": "Go.md", "to": "Lang/Go.md"})
    assert response.status_code == 200
    assert response.json()["file_name"] == "Lang/Go.md"
    assert not notes.exists("Go.md")
    old = retrieval._store._collection.get(where={"file_name": "Go.md"})
    assert not (old.get("ids") or [])
    assert retrieval.is_indexed("Lang/Go.md")


def test_list_notes_includes_folder_and_index_status(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Root.md", "Root")
    notes.create_folder("Python")
    notes.create("Python/GIL.md", "GIL")
    retrieval.index_note("Python/GIL.md")

    response = client.get("/notes")
    assert response.status_code == 200
    payload = response.json()
    assert "Python" in payload["folders"]
    by_name = {item["file_name"]: item for item in payload["files"]}
    assert by_name["Root.md"]["folder"] == ""
    assert by_name["Root.md"]["indexed"] is False
    assert by_name["Python/GIL.md"]["folder"] == "Python"
    assert by_name["Python/GIL.md"]["indexed"] is True


def test_delete_note_removes_file_and_vectors(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制。\n", append=True)
    retrieval.index_note("Go.md")

    response = client.delete("/notes/Go.md")
    assert response.status_code == 200
    assert not notes.exists("Go.md")
    got = retrieval._store._collection.get(where={"file_name": "Go.md"})
    assert not (got.get("ids") or [])


def test_create_note_indexes(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    response = client.post("/notes", json={"file_name": "Lang/Go.md"})
    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "Lang/Go.md"
    assert notes.exists("Lang/Go.md")
    assert body["indexed"] is retrieval.is_indexed("Lang/Go.md")


def test_index_endpoint_indexes_existing_file(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value。\n", append=True)
    assert retrieval.is_indexed("Go.md") is False

    response = client.post("/notes/Go.md/index")
    assert response.status_code == 200
    assert response.json()["indexed"] is True
    assert retrieval.is_indexed("Go.md") is True


def test_rename_folder_reindexes_paths(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Lang/Go.md", "Go")
    notes.write("Lang/Go.md", "注意力机制用 Query Key Value。\n", append=True)
    retrieval.index_note("Lang/Go.md")

    response = client.post("/notes/folders/rename", json={"from": "Lang", "to": "Runtime"})
    assert response.status_code == 200
    assert response.json()["to_name"] == "Runtime"
    assert not notes.exists("Lang/Go.md")
    assert notes.exists("Runtime/Go.md")
    old = retrieval._store._collection.get(where={"file_name": "Lang/Go.md"})
    assert not (old.get("ids") or [])
    assert retrieval.is_indexed("Runtime/Go.md")


def test_delete_folder_removes_notes_and_vectors(tmp_path: Path):
    client, notes, retrieval = _client(tmp_path)
    notes.create("Lang/Go.md", "Go")
    notes.write("Lang/Go.md", "注意力机制。\n", append=True)
    notes.create("Root.md", "Root")
    retrieval.index_note("Lang/Go.md")
    retrieval.index_note("Root.md")

    response = client.delete("/notes/folders/Lang")
    assert response.status_code == 200
    assert response.json()["deleted"] == ["Lang/Go.md"]
    assert not notes.exists("Lang/Go.md")
    assert notes.exists("Root.md")
    got = retrieval._store._collection.get(where={"file_name": "Lang/Go.md"})
    assert not (got.get("ids") or [])
    assert retrieval.is_indexed("Root.md")
