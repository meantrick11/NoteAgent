"""从既有来源表升级时保留文件身份和原件定位。"""
import uuid
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _migration(name: str):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_backfills_existing_file_record():
    SourceFiles = _migration("SourceFiles")
    UploadedFileRecords = _migration("UploadedFileRecords")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    source_id = uuid.uuid4()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            SourceFiles.upgrade()
            connection.execute(text("""
                INSERT INTO source_files
                  (id, display_name, folder, media_type, size_bytes, sha256, status, created_at, updated_at)
                VALUES (:id, 'old.txt', '', 'text/plain', 3, :digest, 'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {"id": source_id.hex, "digest": "0" * 64})
            UploadedFileRecords.upgrade()
        row = connection.execute(text("SELECT original_filename, storage_path, status FROM source_files")).one()
        assert tuple(row) == ("old.txt", str(source_id), "ready")
        assert "uq_active_source_sha256" not in {item["name"] for item in inspect(connection).get_indexes("source_files")}
    engine.dispose()
