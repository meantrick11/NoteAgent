"""Judge model selection and calibration CLI tests without network access."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from NoteAgent.AppBootstrap.AppSettings import Settings
from Scripts import CalibrateLearningNotes as calibrate_learning_notes, EvalNotes as eval_notes

_ROOT = Path(__file__).resolve().parents[2]


def _settings() -> Settings:
    return Settings(_env_file=None)


def _resolved(name: str):
    return SimpleNamespace(config=SimpleNamespace(model=name), client=object())


def test_eval_notes_judge_defaults_to_active_model(monkeypatch, tmp_path: Path, capsys):
    """--judge warns and proceeds with the active model when no override is given."""
    captured = {}
    cases_path = tmp_path / "evals" / "prompt" / "cases.jsonl"
    cases_path.parent.mkdir(parents=True)
    cases_path.write_text('{"id":"x"}\n', encoding="utf-8")
    monkeypatch.setattr(eval_notes, "project_root", lambda: tmp_path)
    monkeypatch.setattr(eval_notes, "Settings", _settings)
    monkeypatch.setattr(eval_notes, "load_cases", lambda path, ids: [])
    monkeypatch.setattr(eval_notes, "build_active_chat", lambda settings: _resolved("chat-only"))
    monkeypatch.setattr(eval_notes, "build_judge", lambda settings, name=None: _resolved("chat-only"))
    monkeypatch.setattr(eval_notes, "setup_logging", lambda *args, **kwargs: None)

    async def fake_run_eval(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(eval_notes, "run_eval", fake_run_eval)

    exit_code = eval_notes.main(["--judge"])

    assert exit_code == 0
    assert captured["chat_model_name"] == "chat-only"
    assert captured["judge_model_name"] == "chat-only"
    assert len(captured["cases_sha256"]) == 64
    assert "judge_independent=false" in capsys.readouterr().err


def test_calibration_cli_archives_active_model_and_hashes(
    monkeypatch, tmp_path: Path, capsys
):
    """Calibration writes reproducibility metadata for the active Judge."""
    captured = {}
    monkeypatch.setattr(calibrate_learning_notes, "project_root", lambda: _ROOT)
    monkeypatch.setattr(
        calibrate_learning_notes, "RESULTS_ROOT", tmp_path / "learning_notes"
    )
    monkeypatch.setattr(calibrate_learning_notes, "Settings", _settings)
    monkeypatch.setattr(
        calibrate_learning_notes,
        "resolve_active_model",
        lambda settings: SimpleNamespace(model="chat-only"),
    )
    monkeypatch.setattr(
        calibrate_learning_notes,
        "build_judge",
        lambda settings, name=None: _resolved(name or "chat-only"),
    )
    monkeypatch.setattr(calibrate_learning_notes, "setup_logging", lambda *args, **kwargs: None)

    async def fake_calibrate(**kwargs):
        captured.update(kwargs)
        return {
            "case_id": "l01",
            "candidates": {
                name: {"fixture_sha256": "a" * 64}
                for name in ("good", "literal", "omitted", "hallucinated")
            },
            "contracts": {"sample": True},
            "pass": True,
            "errors": [],
        }

    monkeypatch.setattr(
        calibrate_learning_notes, "calibrate_learning_note", fake_calibrate
    )

    exit_code = calibrate_learning_notes.main([])

    assert exit_code == 0
    destinations = list((tmp_path / "learning_notes").iterdir())
    assert len(destinations) == 1
    dest = destinations[0]
    config = json.loads((dest / "config.json").read_text(encoding="utf-8"))
    calibration = json.loads((dest / "calibration.json").read_text(encoding="utf-8"))
    assert captured["judge_model_name"] == "chat-only"
    assert config["rubric_version"] == "v0.2"
    assert config["case_id"] == "l01"
    assert len(config["case_file_sha256"]) == 64
    assert set(config["fixture_sha256"]) == {
        "good.md",
        "literal.md",
        "omitted.md",
        "hallucinated.md",
    }
    assert all(len(value) == 64 for value in config["fixture_sha256"].values())
    assert config["judge_model"] == "chat-only"
    assert config["judge_independent"] is False
    assert len(config["judge_prompt_sha256"]) == 64
    assert config["errors"] == []
    assert config["started_at"]
    assert config["finished_at"]
    assert calibration["pass"] is True
    assert (dest / "judge_prompt.txt").read_text(encoding="utf-8")
    assert "judge_independent=false" in capsys.readouterr().err


def test_calibration_cli_marks_separate_judge_independent(
    monkeypatch, tmp_path: Path, capsys
):
    """An explicit Judge override is archived as independent."""
    monkeypatch.setattr(calibrate_learning_notes, "project_root", lambda: _ROOT)
    monkeypatch.setattr(
        calibrate_learning_notes, "RESULTS_ROOT", tmp_path / "learning_notes"
    )
    monkeypatch.setattr(calibrate_learning_notes, "Settings", _settings)
    monkeypatch.setattr(
        calibrate_learning_notes,
        "resolve_active_model",
        lambda settings: SimpleNamespace(model="chat-only"),
    )
    monkeypatch.setattr(
        calibrate_learning_notes,
        "build_judge",
        lambda settings, name=None: _resolved(name or "chat-only"),
    )
    monkeypatch.setattr(calibrate_learning_notes, "setup_logging", lambda *args, **kwargs: None)

    async def fake_calibrate(**kwargs):
        return {
            "case_id": "l01",
            "candidates": {
                name: {"fixture_sha256": "a" * 64}
                for name in ("good", "literal", "omitted", "hallucinated")
            },
            "contracts": {},
            "pass": True,
            "errors": [],
        }

    monkeypatch.setattr(
        calibrate_learning_notes, "calibrate_learning_note", fake_calibrate
    )

    assert calibrate_learning_notes.main(["--judge-model", "separate-judge"]) == 0

    dest = next((tmp_path / "learning_notes").iterdir())
    config = json.loads((dest / "config.json").read_text(encoding="utf-8"))
    assert config["judge_model"] == "separate-judge"
    assert config["judge_independent"] is True
    assert "judge_independent=false" not in capsys.readouterr().err


def test_calibration_cli_archives_missing_fixture_failure_and_exits_one(
    monkeypatch, tmp_path: Path
):
    """A failed calibration still writes null hash metadata and returns exit 1."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    source_fixtures = _ROOT / "evals" / "prompt" / "fixtures" / "learning_notes"
    for name in ("good", "omitted", "hallucinated"):
        shutil.copyfile(source_fixtures / f"{name}.md", fixtures / f"{name}.md")
    results = tmp_path / "results"
    monkeypatch.setattr(calibrate_learning_notes, "project_root", lambda: _ROOT)
    monkeypatch.setattr(calibrate_learning_notes, "RESULTS_ROOT", results)
    monkeypatch.setattr(calibrate_learning_notes, "Settings", _settings)
    monkeypatch.setattr(
        calibrate_learning_notes,
        "resolve_active_model",
        lambda settings: SimpleNamespace(model="chat-only"),
    )
    monkeypatch.setattr(
        calibrate_learning_notes,
        "build_judge",
        lambda settings, name=None: _resolved(name or "chat-only"),
    )
    monkeypatch.setattr(calibrate_learning_notes, "setup_logging", lambda *args, **kwargs: None)

    async def fake_calibrate(**kwargs):
        return {
            "case_id": "l01",
            "candidates": {"literal": {"error": "fixture missing"}},
            "contracts": {},
            "pass": False,
            "errors": ["literal: fixture missing"],
        }

    monkeypatch.setattr(
        calibrate_learning_notes, "calibrate_learning_note", fake_calibrate
    )

    exit_code = calibrate_learning_notes.main(
        ["--fixtures", str(fixtures), "--judge-model", "separate-judge"]
    )

    assert exit_code == 1
    dest = next(results.iterdir())
    config = json.loads((dest / "config.json").read_text(encoding="utf-8"))
    assert config["fixture_sha256"]["literal.md"] is None
    assert "literal: fixture missing" in config["errors"]
