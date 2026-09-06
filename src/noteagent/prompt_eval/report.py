"""Render evals/prompt/results/<dataset>/<run>/ n05.md, index.json, and config.json."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from noteagent.prompt_eval.score import PARENT_ORDER, NoteScore

_logger = logging.getLogger(__name__)

PARENT_LABELS = {
    "faithful": "忠实",
    "complete": "完整",
    "structure": "结构",
    "fluent": "流畅",
    "form": "形态",
    "retrievable": "可检索",
}

METRIC_LABELS = {
    "faithful.contradiction": "矛盾/编造",
    "faithful.literals": "字面量/标识符",
    "faithful.hedge": "情态",
    "faithful.unsupported": "无支持命题",
    "faithful.inference": "推论标注",
    "complete.anchors": "锚点覆盖",
    "complete.terms": "术语覆盖",
    "complete.commands": "命令覆盖",
    "complete.examples": "例子覆盖",
    "complete.compression": "节篇幅/压缩",
    "complete.scope": "范围",
    "structure.heading_recall": "标题原文",
    "structure.heading_precision": "标题无发明",
    "structure.heading_level": "层级映射",
    "structure.h1": "正文 H1",
    "structure.merge": "未合并",
    "fluent.readability": "通顺",
    "fluent.consistency": "术语一致",
    "fluent.translation": "译文通顺",
    "form.slogan": "非口号体",
    "form.fence": "代码围栏",
    "form.quote": "备注引用",
    "form.list": "列表是否符合任务",
    "form.indent": "禁止只靠缩进当代码",
    "form.spacing": "块间空行",
    "retrievable.file_name_ok": "路径合法",
    "retrievable.file_name_topic": "文件名能表达主题",
}


def case_filename(case_id: str) -> str:
    """n05.md, b06.md — filename is the golden-set id."""
    return f"{case_id}.md"


def selection_slug(ids: list[str] | None) -> str:
    """Folder fragment for which rows ran: all, b06-n05, or a bounded range."""
    if not ids:
        return "all"
    if len(ids) <= 8:
        return "-".join(ids)
    return f"{ids[0]}-{ids[-1]}-{len(ids)}ids"


def safe_label(label: str | None) -> str | None:
    """Optional --name tag. Reject path pieces so it cannot escape the results root."""
    if label is None:
        return None
    text = label.strip().replace("\\", "/").split("/")[-1]
    if not text or text in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        raise ValueError("invalid --name; use letters, digits, dot, underscore, hyphen")
    return text


def result_dest(
    results_root: Path,
    *,
    cases_path: Path,
    ids: list[str] | None,
    label: str | None,
    when: datetime,
) -> Path:
    """evals/prompt/results/<jsonl-stem>/<label_>ids_YYYYMMDD-HHMMSS/."""
    stamp = when.strftime("%Y%m%d-%H%M%S")
    tag = safe_label(label)
    slug = selection_slug(ids)
    folder = f"{tag}_{slug}_{stamp}" if tag else f"{slug}_{stamp}"
    return (results_root / cases_path.stem / folder).resolve()


def write_stage(
    dest: Path,
    *,
    prompt_text: str,
    config: dict,
    runs: list,
) -> None:
    """Write config.json, system.txt, index.json, and one markdown file per case."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "system.txt").write_text(prompt_text, encoding="utf-8")
    (dest / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    index = {
        "cases_path": config.get("cases_path"),
        "case_filter": config.get("case_filter"),
        "label": config.get("label"),
        "sort": "worst_first",
        "cases": [_index_row(run) for run in _sorted_runs(runs)],
    }
    (dest / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for run in runs:
        name = case_filename(run.case.id)
        (dest / name).write_text(render_case_md(run, config), encoding="utf-8")
        _logger.info("eval report wrote file=%s id=%s", name, run.case.id)
    _logger.info("eval stage wrote dest=%s cases=%d", dest, len(runs))


def render_case_md(run, config: dict | None = None) -> str:
    """Fixed sections: header, scores, metrics, behavior, input, tools, draft, bubble."""
    case = run.case
    score: NoteScore = run.score
    meta = config or {}
    lines: list[str] = [
        f"# {case.id}",
        "",
        "## 1. 题头",
        "",
        f"- seq: {run.seq:02d}",
        f"- id: `{case.id}`",
        f"- kind: `{case.kind}`",
        f"- style: `{case.style}`",
    ]
    if meta.get("cases_path"):
        filt = meta.get("case_filter")
        filt_text = ",".join(filt) if filt else "all"
        lines.append(f"- dataset: `{meta['cases_path']}`")
        lines.append(f"- filter: `{filt_text}`")
        if meta.get("label"):
            lines.append(f"- label: `{meta['label']}`")
    lines.extend(
        [
        "",
        "## 2. 得分摘要",
        "",
        ]
    )
    if not score.behavior_pass:
        lines.append("- 行为门: **失败**")
        lines.append("- 正文: 未评正文")
        lines.append("- 总分: —")
        for key in PARENT_ORDER:
            lines.append(f"- {PARENT_LABELS[key]}: 未评正文")
    elif score.total is None:
        lines.append("- 行为门: 通过")
        lines.append("- 正文: 未评正文")
        lines.append("- 总分: —")
        for key in PARENT_ORDER:
            lines.append(f"- {PARENT_LABELS[key]}: 未评正文")
    else:
        lines.append("- 行为门: 通过")
        lines.append(f"- 总分: {score.total}")
        for key in PARENT_ORDER:
            value = score.parents.get(key)
            label = PARENT_LABELS[key]
            lines.append(f"- {label}: {value if value is not None else '不适用（摊权）'}")
    lines.extend(["", "## 3. 小指标", "", "| id | 名称 | 档位 | 权重 | 适用 | 证据 |", "|----|------|------|------|------|------|"])
    if not score.metrics:
        lines.append("| — | — | — | — | — | 未评正文 |")
    else:
        for metric in score.metrics:
            band = "—" if metric.score is None else str(metric.score)
            applicable = "是" if metric.applicable else "否"
            evidence = "；".join(metric.evidence) if metric.evidence else ""
            name = METRIC_LABELS.get(metric.metric_id, metric.metric_id)
            lines.append(
                f"| `{metric.metric_id}` | {name} | {band} | {metric.weight} | {applicable} | {_cell(evidence)} |"
            )
    lines.extend(["", "## 4. 行为", ""])
    lines.append(f"- expect_propose: `{case.expect_propose}`")
    lines.append(f"- actual_propose: `{run.draft is not None}`")
    lines.append(f"- expect_tools_prefix: `{case.expect_tools_prefix}`")
    lines.append(f"- actual_tools: `{[hop.name for hop in run.tools]}`")
    lines.append(f"- expect_action: `{case.expect_action}`")
    actual_action = run.draft.get("action") if run.draft else None
    lines.append(f"- actual_action: `{actual_action}`")
    for item in score.behavior_evidence:
        lines.append(f"- {item}")
    if run.error:
        lines.append(f"- error: `{_cell(run.error)}`")
    lines.extend(["", "## 5. 输入", "", "```text", case.user, "```", ""])
    if case.seed_files:
        lines.append("seed_files:")
        lines.append("")
        for name, body in case.seed_files.items():
            lines.append(f"### {name}")
            lines.append("")
            lines.append("```markdown")
            lines.append(body.rstrip("\n"))
            lines.append("```")
            lines.append("")
    lines.extend(["## 6. 工具轨迹", ""])
    if not run.tools:
        lines.append("（无工具调用）")
        lines.append("")
    else:
        for index, hop in enumerate(run.tools, start=1):
            lines.append(f"### {index}. `{hop.name}`")
            lines.append("")
            lines.append(f"- status: `{hop.status}`")
            lines.append(f"- args: {_preview(hop.arguments)}")
            lines.append(f"- output: {_preview(hop.output_preview)}")
            lines.append("")
    lines.extend(["## 7. 草稿", ""])
    if run.draft is None:
        lines.append("无草稿")
        lines.append("")
    else:
        lines.append(f"- action: `{run.draft.get('action')}`")
        lines.append(f"- file_name: `{run.draft.get('file_name')}`")
        lines.append(f"- reason: {_preview(str(run.draft.get('reason') or ''))}")
        lines.append("")
        lines.append("```markdown")
        lines.append(str(run.draft.get("content") or "").rstrip("\n"))
        lines.append("```")
        lines.append("")
    lines.extend(["## 8. 助手气泡", ""])
    if run.assistant_final:
        lines.append(run.assistant_final)
    else:
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


def _sorted_runs(runs: list) -> list:
    """Behavior failures first, then lowest total, then faithful / complete / structure."""

    def key(run) -> tuple:
        score: NoteScore = run.score
        if not score.behavior_pass or score.total is None:
            return (0, 0.0, 0.0, 0.0, 0.0, run.seq)
        parents = score.parents
        return (
            1,
            score.total,
            parents.get("faithful") or 0.0,
            parents.get("complete") or 0.0,
            parents.get("structure") or 0.0,
            run.seq,
        )

    return sorted(runs, key=key)


def _index_row(run) -> dict:
    """Directory row; does not replace the per-case markdown file."""
    score: NoteScore = run.score
    return {
        "file": case_filename(run.case.id),
        "id": run.case.id,
        "kind": run.case.kind,
        "behavior_pass": score.behavior_pass,
        "total": score.total,
        "parents": score.parents,
    }


def _preview(text: str, limit: int = 240) -> str:
    """One-line truncated preview for args/output. Never dump secrets."""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact or "（空）"
    return compact[:limit] + "…"


def _cell(text: str) -> str:
    """Escape pipes so markdown tables stay one row."""
    return text.replace("|", "\\|").replace("\n", " ")
