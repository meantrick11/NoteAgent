"""Protect ownership seams and resources needed by the reorganized application."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "NoteAgent"


def test_source_has_five_documented_entry_points():
    for name in ("HttpApi", "BusinessModules", "ApplicationFlows", "TechnicalSupport", "AppBootstrap"):
        assert (PACKAGE / name / "README.md").is_file(), name


def test_business_and_workflow_code_do_not_import_http():
    for folder in (PACKAGE / "BusinessModules", PACKAGE / "ApplicationFlows"):
        assert folder.is_dir(), folder
        for file in folder.rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                imports = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                           else [alias.name for alias in node.names] if isinstance(node, ast.Import)
                           else [])
                for name in imports:
                    assert not name.startswith(("fastapi", "starlette", "NoteAgent.HttpApi")), (file, name)


def test_database_registry_keeps_existing_table_identities():
    from NoteAgent.TechnicalSupport.DatabaseAccess import Base, load_all_models

    load_all_models()
    assert set(Base.metadata.tables) == {
        "conversations", "messages", "conversation_branches", "conversation_runs",
        "user_message_boundaries", "workspace_state", "mutation_records",
        "recovery_previews", "recovery_jobs", "index_repairs",
    }


def test_frontend_build_and_backend_serve_the_same_directory():
    from NoteAgent.HttpApi.WebFrontend import DIST_DIR, TEMPLATES_DIR

    assert DIST_DIR == PACKAGE / "HttpApi" / "WebFrontend" / "dist"
    assert (TEMPLATES_DIR / "home.html").is_file()
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "../src/NoteAgent/HttpApi/WebFrontend/dist" in vite


def test_upper_modules_have_explicit_pascal_case_names():
    expected = {
        "HttpApi": {"ChatApi", "ConversationApi", "NoteApi", "ModelSettingsApi",
                    "ConversationRecoveryApi", "WebFrontend"},
        "BusinessModules": {"ChatAgent", "ConversationState", "NoteStorage",
                            "NoteRetrieval", "ModelSettings", "ConversationRecovery"},
        "ApplicationFlows": {"DraftApproval", "ModelRuntime", "ConversationRecovery"},
        "TechnicalSupport": {"DatabaseAccess", "ExecutionLogging", "NoteAccessControl"},
        "AppBootstrap": set(),
    }
    for parent, children in expected.items():
        assert (PACKAGE / parent / "README.md").is_file(), parent
        for child in children:
            assert (PACKAGE / parent / child / "README.md").is_file(), (parent, child)
    for obsolete in ("api", "modules", "application", "infrastructure", "bootstrap"):
        assert not (PACKAGE / obsolete).exists(), obsolete


def test_note_journal_access_state_and_recovery_records_have_distinct_owners():
    from NoteAgent.BusinessModules.NoteStorage.ChangeJournal.NoteChangeModels import MutationRecord
    from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessModels import WorkspaceState
    from NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels import RecoveryJob, RecoveryPreview

    assert MutationRecord.__module__ == "NoteAgent.BusinessModules.NoteStorage.ChangeJournal.NoteChangeModels"
    assert WorkspaceState.__module__ == "NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessModels"
    assert RecoveryJob.__module__ == RecoveryPreview.__module__ == "NoteAgent.BusinessModules.ConversationRecovery.RecoveryModels"


def test_all_python_application_packages_and_files_use_pascal_case():
    import re

    assert PACKAGE.name == "NoteAgent"
    for file in PACKAGE.rglob("*.py"):
        if file.name not in {"__init__.py", "__main__.py"}:
            assert re.fullmatch(r"[A-Z][A-Za-z0-9]*", file.stem), file
        for parent in file.relative_to(PACKAGE).parts[:-1]:
            assert re.fullmatch(r"[A-Z][A-Za-z0-9]*", parent), file


def test_repository_python_tools_and_tests_follow_pascal_case():
    import re

    for folder in ("Scripts", "Tools", "Tests"):
        assert (ROOT / folder).is_dir()
        for file in (ROOT / folder).rglob("*.py"):
            if file.name not in {"__init__.py", "__main__.py", "conftest.py"}:
                assert re.fullmatch(r"[A-Z][A-Za-z0-9]*", file.stem), file
    assert (ROOT / "main.py").is_file()


def test_main_entrypoint_keeps_requested_lowercase_name():
    entries = {path.name for path in ROOT.iterdir()}
    assert "main.py" in entries
    assert "Main.py" not in entries
