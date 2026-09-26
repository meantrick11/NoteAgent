import json
from collections import Counter
from pathlib import Path

from noteagent.prompt_eval.cases import load_cases


def test_v1_acceptance_set_is_complete_and_loadable():
    path = Path(__file__).resolve().parents[2] / "evals/prompt/v1_acceptance.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 25
    assert {row["id"] for row in rows} == {f"g{i:02d}" for i in range(1, 26)}
    assert Counter(row["category"] for row in rows) == {
        "dialogue": 5, "long_text": 5, "english": 5, "code": 5, "modify": 5,
    }
    assert len({row["user"] for row in rows}) == 25
    for row in rows:
        assert row["kind"] == "quality"
        assert row["expect_propose"] is True
        assert row["expect_action"] in {"create", "append", "replace"}
        assert row["user"].strip()
        if row["category"] == "long_text":
            assert len(row["user"]) >= 2000
        if row["category"] == "modify":
            assert row["seed_files"]
    assert len(load_cases(path)) == 25
