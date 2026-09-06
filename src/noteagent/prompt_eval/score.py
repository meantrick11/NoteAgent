"""v0.1 L1 note-body scorer. L2 items are marked inapplicable and renormalized."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from noteagent.chat.context_pack import extract_source_headings
from noteagent.prompt_eval.cases import EvalCase

RUBRIC_VERSION = "v0.1"

# Parent weights for the comparison total. Inapplicable parents are dropped.
PARENT_WEIGHTS: dict[str, float] = {
    "faithful": 0.25,
    "complete": 0.30,
    "structure": 0.25,
    "fluent": 0.08,
    "form": 0.08,
    "retrievable": 0.04,
}

PARENT_ORDER = tuple(PARENT_WEIGHTS)

_HEDGE = ("通常", "可能", "往往", "建议", "默认", "usually", "may ", "might", "often")
_STRONG = ("一定", "必须", "总是", "绝对", "只能", "must always", "always must")
_ATX = re.compile(r"^(#{1,6})\s+(\S.*)$")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
_LITERAL = re.compile(
    r"(?:/[^\s，。；]+)|(?:python\d+\.\d+)|(?:sys\.argv(?:\[\d+\])?)|(?:UTF-8)|"
    r"(?:Control-[A-Z])|(?:py\.exe)|(?:quit\(\))|(?:functools\.wraps)|(?:@decorator)",
    re.I,
)
_COMMAND = re.compile(
    r"python\s+-[cm]\b|import\s+\w+|quit\(\)|#\s*-\*-\s*coding:",
    re.I,
)
_IDENT = re.compile(r"\b[A-Za-z_][\w.]{1,}\b")
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "python", "please",
    "into", "when", "then", "else", "elif", "true", "false", "none",
}


@dataclass
class MetricScore:
    """One rubric submetric, including 10/10 rows."""

    metric_id: str
    parent: str
    layer: str
    weight: int
    applicable: bool
    score: int | None
    raw: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)


@dataclass
class NoteScore:
    """Body score plus the behavior gate. total/parents are None if the gate fails."""

    behavior_pass: bool
    total: float | None
    parents: dict[str, float | None]
    metrics: list[MetricScore]
    behavior_evidence: list[str] = field(default_factory=list)


def score_note(
    case: EvalCase,
    *,
    proposed: bool,
    tools: list[str],
    action: str | None,
    file_name: str | None,
    content: str | None,
) -> NoteScore:
    """Run the behavior gate, then L1 body metrics when a draft exists and the gate passes."""
    gate_ok, gate_evidence = _behavior_gate(case, proposed=proposed, tools=tools, action=action)
    if not gate_ok:
        return NoteScore(
            behavior_pass=False,
            total=None,
            parents={key: None for key in PARENT_ORDER},
            metrics=[],
            behavior_evidence=gate_evidence,
        )
    if not proposed:
        return NoteScore(
            behavior_pass=True,
            total=None,
            parents={key: None for key in PARENT_ORDER},
            metrics=[],
            behavior_evidence=gate_evidence + ["无草稿，未评正文"],
        )
    metrics = _score_body(case, action=action, file_name=file_name, content=content or "")
    parents = _parent_scores(metrics)
    return NoteScore(
        behavior_pass=True,
        total=_weighted_total(parents),
        parents=parents,
        metrics=metrics,
        behavior_evidence=gate_evidence,
    )


def _behavior_gate(
    case: EvalCase, *, proposed: bool, tools: list[str], action: str | None
) -> tuple[bool, list[str]]:
    """True when propose / tool prefix / action match the case. Failures are listed."""
    evidence: list[str] = []
    ok = True
    if proposed != case.expect_propose:
        ok = False
        evidence.append(
            f"expect_propose={case.expect_propose} actual={proposed}"
        )
    prefix = case.expect_tools_prefix
    if prefix:
        actual_prefix = tools[: len(prefix)]
        if actual_prefix != prefix:
            ok = False
            evidence.append(f"expect_tools_prefix={prefix} actual_prefix={actual_prefix}")
    expected = case.expect_action
    if expected:
        if action is None:
            ok = False
            evidence.append(f"expect_action={expected} actual=None")
        elif expected == "append_or_create":
            if action not in ("append", "create"):
                ok = False
                evidence.append(f"expect_action=append_or_create actual={action}")
        elif action != expected:
            ok = False
            evidence.append(f"expect_action={expected} actual={action}")
    if ok:
        evidence.append("行为门通过")
    return ok, evidence


def _score_body(
    case: EvalCase, *, action: str | None, file_name: str | None, content: str
) -> list[MetricScore]:
    """Score every v0.1 submetric. This slice marks L2 rows inapplicable."""
    material = _material(case.user)
    source_headings = extract_source_headings(material)
    draft_headings = _atx_headings(content)
    required = case.must_headings or source_headings
    return [
        *_faithful(material, content),
        *_complete(case, material, content),
        *_structure(case, action, content, source_headings, draft_headings, required),
        *_fluent(case),
        *_form(case, material, content),
        *_retrievable(case, file_name),
    ]


def _faithful(material: str, content: str) -> list[MetricScore]:
    """Contradiction / unsupported / inference are L2 this slice."""
    return [
        _na("faithful.contradiction", "faithful", "L2", 30, "本期无 Judge，不评矛盾"),
        _literals(material, content),
        _hedge(material, content),
        _na("faithful.unsupported", "faithful", "L2", 20, "本期无 Judge，不评无支持命题"),
        _na("faithful.inference", "faithful", "L2", 10, "本期无 Judge，不评推论标注"),
    ]


def _literals(material: str, content: str) -> MetricScore:
    """Invented paths / versions / identifiers in the draft score 0."""
    src = {item.lower() for item in _LITERAL.findall(material)}
    dst = {item.lower() for item in _LITERAL.findall(content)}
    extra = sorted(dst - src)
    if extra:
        return MetricScore(
            "faithful.literals", "faithful", "L1", 20, True, 0,
            raw={"source": sorted(src), "draft": sorted(dst), "extra": extra},
            evidence=[f"草稿出现材料没有的字面量: {', '.join(extra)}"],
        )
    return MetricScore(
        "faithful.literals", "faithful", "L1", 20, True, 10,
        raw={"source": sorted(src), "draft": sorted(dst)},
        evidence=["草稿字面量均可在材料中找到"] if src else ["材料无明显字面量，草稿也未发明"],
    )


def _hedge(material: str, content: str) -> MetricScore:
    """Usually/may in the source must not become must/always in the draft."""
    src_hedge = [word for word in _HEDGE if word in material]
    if not src_hedge:
        return _na("faithful.hedge", "faithful", "L1", 20, "材料无情态词")
    strong = [word for word in _STRONG if word in content]
    dst_hedge = [word for word in _HEDGE if word in content]
    if strong:
        return MetricScore(
            "faithful.hedge", "faithful", "L1", 20, True, 0,
            raw={"source_hedge": src_hedge, "draft_strong": strong},
            evidence=[f"情态被加强: {', '.join(strong)}"],
        )
    if not dst_hedge:
        return MetricScore(
            "faithful.hedge", "faithful", "L1", 20, True, 5,
            raw={"source_hedge": src_hedge},
            evidence=["材料有情态，草稿未保留也未加强"],
        )
    return MetricScore(
        "faithful.hedge", "faithful", "L1", 20, True, 10,
        raw={"source_hedge": src_hedge, "draft_hedge": dst_hedge},
        evidence=["情态保留"],
    )


def _complete(case: EvalCase, material: str, content: str) -> list[MetricScore]:
    """Coverage metrics. outline skips compression."""
    return [
        _coverage("complete.anchors", 20, case.must_anchors, content, empty="无 must_anchors"),
        _terms(material, content),
        _commands(material, content),
        _examples(material, content),
        _compression(case, material, content),
        _scope(case, content),
    ]


def _coverage(
    metric_id: str, weight: int, needles: list[str], content: str, *, empty: str
) -> MetricScore:
    """0 if none, 5 if partial, 10 if every needle is in the draft."""
    if not needles:
        return _na(metric_id, "complete", "L1", weight, empty)
    found = [item for item in needles if item in content]
    missing = [item for item in needles if item not in content]
    if not found:
        band = 0
        evidence = [f"全部缺失: {', '.join(missing)}"]
    elif missing:
        band = 5
        evidence = [f"缺失: {', '.join(missing)}"]
    else:
        band = 10
        evidence = ["全部命中"]
    return MetricScore(
        metric_id, "complete", "L1", weight, True, band,
        raw={"found": found, "missing": missing},
        evidence=evidence,
    )


def _terms(material: str, content: str) -> MetricScore:
    """Identifier coverage from the source, minus stopwords."""
    terms = sorted(
        {
            token
            for token in _IDENT.findall(material)
            if token.lower() not in _STOP and len(token) >= 3
        }
    )
    if not terms:
        return _na("complete.terms", "complete", "L1", 15, "材料无术语标识符")
    found = [item for item in terms if item in content]
    ratio = len(found) / len(terms)
    band = 10 if ratio >= 0.8 else 5 if ratio >= 0.4 else 0
    missing = [item for item in terms if item not in content]
    return MetricScore(
        "complete.terms", "complete", "L1", 15, True, band,
        raw={"ratio": round(ratio, 3), "missing": missing[:12]},
        evidence=[f"术语覆盖 {len(found)}/{len(terms)}"]
        + ([f"缺失例: {', '.join(missing[:6])}"] if missing else []),
    )


def _commands(material: str, content: str) -> MetricScore:
    """python -c / import / coding cookie coverage."""
    src = _COMMAND.findall(material)
    if not src and "python -c" not in material and "python -m" not in material:
        return _na("complete.commands", "complete", "L1", 15, "材料无命令")
    needles = []
    if "python -c" in material:
        needles.append("python -c")
    if "python -m" in material:
        needles.append("python -m")
    if "import sys" in material:
        needles.append("import sys")
    if "quit()" in material:
        needles.append("quit()")
    if not needles:
        needles = src
    return _coverage("complete.commands", 15, needles, content, empty="材料无命令")


def _examples(material: str, content: str) -> MetricScore:
    """REPL prompts and explicit 例如 / 2 + 2 examples."""
    needles: list[str] = []
    if ">>>" in material:
        needles.append(">>>")
    if "..." in material and ">>>" in material:
        needles.append("...")
    if "2 + 2" in material:
        needles.append("2 + 2")
    if "例如" in material and not needles:
        needles.append("例如")
    if not needles:
        return _na("complete.examples", "complete", "L1", 15, "材料无例子")
    return _coverage("complete.examples", 15, needles, content, empty="材料无例子")


def _compression(case: EvalCase, material: str, content: str) -> MetricScore:
    """faithful_paragraphs must not collapse into an outline. outline is N/A."""
    if case.style == "outline":
        return _na("complete.compression", "complete", "L1", 25, "提纲任务不评压缩")
    src_len = max(len(material.strip()), 1)
    ratio = len(content.strip()) / src_len
    if case.style == "faithful_paragraphs" and ratio < 0.35:
        band = 0
        evidence = [f"压缩比 {ratio:.2f}，默认整理被压成提纲量级"]
    elif ratio < 0.55 and case.style == "faithful_paragraphs":
        band = 5
        evidence = [f"压缩比 {ratio:.2f}，明显删信息"]
    else:
        band = 10
        evidence = [f"压缩比 {ratio:.2f}，体量与任务匹配"]
    return MetricScore(
        "complete.compression", "complete", "L1", 25, True, band,
        raw={"ratio": round(ratio, 3), "src_len": src_len, "dst_len": len(content)},
        evidence=evidence,
    )


def _scope(case: EvalCase, content: str) -> MetricScore:
    """excerpt must not leak forbidden headings; outline must not become a full essay."""
    draft_keys = [_heading_key(text) for _level, text in _atx_headings(content)]
    leaked = [
        item for item in case.forbidden_headings
        if any(_same_heading(_heading_key(item), key) for key in draft_keys)
        or _heading_key(item) in content
    ]
    if leaked:
        return MetricScore(
            "complete.scope", "complete", "L1", 10, True, 0,
            raw={"leaked": leaked},
            evidence=[f"超出范围标题: {', '.join(leaked)}"],
        )
    if case.style == "outline" and len(content) > 800:
        return MetricScore(
            "complete.scope", "complete", "L1", 10, True, 0,
            raw={"len": len(content)},
            evidence=["提纲任务写成全文"],
        )
    return MetricScore(
        "complete.scope", "complete", "L1", 10, True, 10,
        raw={},
        evidence=["范围与任务一致"],
    )


def _structure(
    case: EvalCase,
    action: str | None,
    content: str,
    source_headings: list[str],
    draft_headings: list[tuple[int, str]],
    required: list[str],
) -> list[MetricScore]:
    """Heading recall/precision/level, H1 policy, and merge."""
    draft_keys = [_heading_key(text) for _level, text in draft_headings]
    return [
        _heading_recall(required, source_headings, draft_keys),
        _heading_precision(case, source_headings, required, draft_keys),
        _heading_level(source_headings, draft_headings),
        _h1(action, content),
        _merge(source_headings, draft_keys),
    ]


def _heading_recall(
    required: list[str], source_headings: list[str], draft_keys: list[str]
) -> MetricScore:
    """Original numbered headings must appear, including numbers."""
    if not source_headings and not required:
        return _na("structure.heading_recall", "structure", "L1", 30, "材料无原标题")
    missing_full: list[str] = []
    numbering_lost: list[str] = []
    for heading in required:
        key = _heading_key(heading)
        if any(_same_heading(key, draft) for draft in draft_keys):
            continue
        bare = _strip_number(key)
        if bare and any(_strip_number(draft) == bare for draft in draft_keys):
            numbering_lost.append(heading)
        else:
            missing_full.append(heading)
    if len(missing_full) >= 2:
        band, evidence = 0, [f"漏多个原标题: {', '.join(missing_full)}"]
    elif missing_full or numbering_lost:
        band, evidence = 5, []
        if missing_full:
            evidence.append(f"漏 1 个: {missing_full[0]}")
        if numbering_lost:
            evidence.append(f"编号丢失: {', '.join(numbering_lost)}")
    else:
        band, evidence = 10, ["原标题含编号全在"]
    return MetricScore(
        "structure.heading_recall", "structure", "L1", 30, True, band,
        raw={"missing": missing_full, "numbering_lost": numbering_lost},
        evidence=evidence,
    )


def _heading_precision(
    case: EvalCase,
    source_headings: list[str],
    required: list[str],
    draft_keys: list[str],
) -> MetricScore:
    """Invented skeleton headings, including forbidden_headings, score 0."""
    allowed = {_heading_key(item) for item in source_headings + required + case.must_headings}
    forbidden = {_heading_key(item) for item in case.forbidden_headings if item.strip()}
    invented = [
        key for key in draft_keys
        if key and key not in allowed and not any(_same_heading(key, allow) for allow in allowed)
    ]
    hit_forbidden = [key for key in draft_keys if key in forbidden]
    if hit_forbidden or (invented and any("其他" in key or "清单" in key or "总结" in key for key in invented)):
        return MetricScore(
            "structure.heading_precision", "structure", "L1", 30, True, 0,
            raw={"invented": invented, "forbidden": hit_forbidden},
            evidence=[f"发明或禁用标题: {', '.join(hit_forbidden or invented)}"],
        )
    if invented:
        band = 5 if len(invented) == 1 else 0
        return MetricScore(
            "structure.heading_precision", "structure", "L1", 30, True, band,
            raw={"invented": invented},
            evidence=[f"额外标题: {', '.join(invented)}"],
        )
    return MetricScore(
        "structure.heading_precision", "structure", "L1", 30, True, 10,
        raw={},
        evidence=["无发明标题"],
    )


def _heading_level(
    source_headings: list[str], draft_headings: list[tuple[int, str]]
) -> MetricScore:
    """2. → ##, 2.1. → ###, 2.1.1. → #### relative to the shallowest numbered heading."""
    numbered = [_numbered_parts(line) for line in source_headings]
    numbered = [item for item in numbered if item]
    if not numbered:
        return _na("structure.heading_level", "structure", "L1", 20, "材料无编号标题")
    min_parts = min(item[0] for item in numbered)
    expected = {
        _heading_key(line): 2 + (parts - min_parts)
        for parts, line in numbered
    }
    mismatches: list[str] = []
    matched = 0
    for level, text in draft_headings:
        key = _heading_key(text)
        want = expected.get(key)
        if want is None:
            for src_key, src_level in expected.items():
                if _same_heading(key, src_key):
                    want = src_level
                    break
        if want is None:
            continue
        matched += 1
        if level != want:
            mismatches.append(f"{key}: 期望 h{want} 实际 h{level}")
    if not matched:
        return MetricScore(
            "structure.heading_level", "structure", "L1", 20, True, 0,
            raw={"expected": expected},
            evidence=["草稿标题无法与编号层级对齐"],
        )
    if mismatches:
        band = 5 if len(mismatches) == 1 else 0
        return MetricScore(
            "structure.heading_level", "structure", "L1", 20, True, band,
            raw={"mismatches": mismatches},
            evidence=mismatches,
        )
    return MetricScore(
        "structure.heading_level", "structure", "L1", 20, True, 10,
        raw={"expected": expected},
        evidence=["层级映射规则全对"],
    )


def _h1(action: str | None, content: str) -> MetricScore:
    """create/append must not use '# '; replace should keep an H1; delete is N/A."""
    if action == "delete":
        return _na("structure.h1", "structure", "L1", 10, "delete 无正文 H1")
    has_h1 = any(
        line.startswith("# ") and not line.startswith("## ")
        for line in content.splitlines()
    )
    if action == "replace":
        band = 10 if has_h1 else 0
        evidence = ["replace 保留一级标题"] if has_h1 else ["replace 缺少一级标题"]
    else:
        band = 0 if has_h1 else 10
        evidence = ["create/append 写了 # "] if has_h1 else ["正文未写违规一级标题"]
    return MetricScore(
        "structure.h1", "structure", "L1", 10, True, band,
        raw={"has_h1": has_h1, "action": action},
        evidence=evidence,
    )


def _merge(source_headings: list[str], draft_keys: list[str]) -> MetricScore:
    """Multiple source headings collapsed into one invented umbrella → 0."""
    if len(source_headings) < 2:
        return MetricScore(
            "structure.merge", "structure", "L1", 10, True, 10,
            raw={},
            evidence=["无需判断合并"],
        )
    src_keys = [_heading_key(item) for item in source_headings]
    present = sum(1 for key in src_keys if any(_same_heading(key, draft) for draft in draft_keys))
    extra = [key for key in draft_keys if not any(_same_heading(key, src) for src in src_keys)]
    if present <= len(src_keys) - 2 and extra:
        return MetricScore(
            "structure.merge", "structure", "L1", 10, True, 0,
            raw={"present": present, "source": len(src_keys), "extra": extra},
            evidence=[f"多节并成自拟标题: {', '.join(extra)}"],
        )
    return MetricScore(
        "structure.merge", "structure", "L1", 10, True, 10,
        raw={"present": present, "source": len(src_keys)},
        evidence=["未合并"],
    )


def _fluent(case: EvalCase) -> list[MetricScore]:
    """All fluent rows are L2 this slice; translation stays N/A for non-translation."""
    rows = [
        _na("fluent.readability", "fluent", "L2", 50, "本期无 Judge，不评通顺"),
        _na("fluent.consistency", "fluent", "L2", 30, "本期无 Judge，不评术语一致"),
    ]
    if case.style != "translation":
        rows.append(_na("fluent.translation", "fluent", "L2", 20, "非翻译任务"))
    else:
        rows.append(_na("fluent.translation", "fluent", "L2", 20, "本期无 Judge，不评译文通顺"))
    return rows


def _form(case: EvalCase, material: str, content: str) -> list[MetricScore]:
    """Slogan / fence / quote / list / indent / spacing."""
    return [
        _slogan(content),
        _fence(material, content),
        _quote(material, content),
        _list_ratio(case, content),
        _indent(content),
        _spacing(content),
    ]


def _slogan(content: str) -> MetricScore:
    """Heading + one short sentence + next heading looks like a slogan template."""
    lines = [line.strip() for line in content.splitlines()]
    slogans = 0
    i = 0
    while i < len(lines):
        if _ATX.match(lines[i] or ""):
            body: list[str] = []
            j = i + 1
            while j < len(lines) and not _ATX.match(lines[j] or ""):
                if lines[j]:
                    body.append(lines[j])
                j += 1
            if len(body) == 1 and len(body[0]) < 40 and not body[0].startswith(("```", "-", "*", ">")):
                slogans += 1
            i = j
            continue
        i += 1
    if slogans >= 3:
        band, evidence = 0, [f"{slogans} 节为标题+一句口号"]
    elif slogans:
        band, evidence = 5, [f"{slogans} 节像口号"]
    else:
        band, evidence = 10, ["默认以段落为主"]
    return MetricScore(
        "form.slogan", "form", "L1", 25, True, band,
        raw={"slogans": slogans},
        evidence=evidence,
    )


def _fence(material: str, content: str) -> MetricScore:
    """Multi-line commands / REPL need ``` when the source has code-like text."""
    needs = any(token in material for token in ("python -c", "python -m", ">>>", "```"))
    if not needs:
        return _na("form.fence", "form", "L1", 25, "材料无代码态")
    if "```" in content:
        band, evidence = 10, ["草稿含围栏"]
    elif "`" in content:
        band, evidence = 5, ["仅有行内 code，无围栏"]
    else:
        band, evidence = 0, ["有代码态却无围栏"]
    return MetricScore(
        "form.fence", "form", "L1", 25, True, band,
        raw={"has_fence": "```" in content},
        evidence=evidence,
    )


def _quote(material: str, content: str) -> MetricScore:
    """备注 / 注 must land in a blockquote."""
    if not any(token in material for token in ("备注", "注：", "注:")):
        return _na("form.quote", "form", "L1", 20, "材料无备注")
    if any(line.startswith(">") for line in content.splitlines()):
        return MetricScore(
            "form.quote", "form", "L1", 20, True, 10,
            raw={},
            evidence=["备注落到 >"],
        )
    return MetricScore(
        "form.quote", "form", "L1", 20, True, 0,
        raw={},
        evidence=["有备注无 >"],
    )


def _list_ratio(case: EvalCase, content: str) -> MetricScore:
    """faithful_paragraphs should not be mostly short bullets. outline skips this."""
    if case.style == "outline":
        return _na("form.list", "form", "L1", 15, "提纲允许列表")
    body = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not _ATX.match(line.strip()) and not line.strip().startswith("```")
    ]
    if not body:
        return MetricScore(
            "form.list", "form", "L1", 15, True, 10, raw={"ratio": 0}, evidence=["无列表行"]
        )
    lists = [
        line for line in body
        if line.startswith(("- ", "* ", "+ ")) or re.match(r"^\d+\.\s", line)
    ]
    ratio = len(lists) / len(body)
    if ratio > 0.5:
        band, evidence = 0, [f"列表行占比 {ratio:.2f}"]
    elif ratio > 0.3:
        band, evidence = 5, [f"列表略多 {ratio:.2f}"]
    else:
        band, evidence = 10, [f"列表行占比 {ratio:.2f}"]
    return MetricScore(
        "form.list", "form", "L1", 15, True, band,
        raw={"ratio": round(ratio, 3)},
        evidence=evidence,
    )


def _indent(content: str) -> MetricScore:
    """Four-space indented code without a fence scores 0."""
    in_fence = False
    indented = 0
    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("    ") and line.strip() and not line.strip().startswith(("-", "*", ">")):
            indented += 1
    if indented >= 2:
        return MetricScore(
            "form.indent", "form", "L1", 10, True, 0,
            raw={"indented": indented},
            evidence=["只靠缩进当代码"],
        )
    return MetricScore(
        "form.indent", "form", "L1", 10, True, 10,
        raw={"indented": indented},
        evidence=["未用缩进冒充围栏"],
    )


def _spacing(content: str) -> MetricScore:
    """Count heading/fence/list glued to the previous non-empty line."""
    lines = content.splitlines()
    glued = 0
    prev_blank = True
    prev = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            prev = stripped
            continue
        block = bool(_ATX.match(stripped) or stripped.startswith("```") or stripped.startswith(("- ", "* ")))
        if block and not prev_blank and prev:
            glued += 1
        prev_blank = False
        prev = stripped
    if glued >= 3:
        band, evidence = 0, [f"{glued} 处块间缺空行"]
    elif glued:
        band, evidence = 5, [f"{glued} 处缺空行"]
    else:
        band, evidence = 10, ["块上下空一行"]
    return MetricScore(
        "form.spacing", "form", "L1", 5, True, band,
        raw={"glued": glued},
        evidence=evidence,
    )


def _retrievable(case: EvalCase, file_name: str | None) -> list[MetricScore]:
    """Path legality and a light stem/topic overlap check."""
    return [_file_name_ok(file_name), _file_name_topic(case, file_name)]


def _file_name_ok(file_name: str | None) -> MetricScore:
    """Note.md or Folder/Note.md; reject abs, .., extra nests, non-md."""
    if not file_name:
        return MetricScore(
            "retrievable.file_name_ok", "retrievable", "L1", 60, True, 0,
            raw={},
            evidence=["无 file_name"],
        )
    name = file_name.replace("\\", "/").strip()
    bad = (
        name.startswith("/")
        or ".." in name
        or not name.endswith(".md")
        or name.count("/") > 1
        or ":/" in name
        or re.match(r"^[A-Za-z]:/", name)
    )
    if bad:
        return MetricScore(
            "retrievable.file_name_ok", "retrievable", "L1", 60, True, 0,
            raw={"file_name": name},
            evidence=[f"路径不合法: {name}"],
        )
    return MetricScore(
        "retrievable.file_name_ok", "retrievable", "L1", 60, True, 10,
        raw={"file_name": name},
        evidence=["路径合法"],
    )


def _file_name_topic(case: EvalCase, file_name: str | None) -> MetricScore:
    """Stem should overlap an anchor or a heading token."""
    if not file_name:
        return MetricScore(
            "retrievable.file_name_topic", "retrievable", "L1", 40, True, 0,
            raw={},
            evidence=["无 file_name"],
        )
    stem = file_name.replace("\\", "/").split("/")[-1].lower()
    tokens = [item.lower() for item in case.must_anchors if item.strip()]
    for heading in case.must_headings:
        tokens.extend(part.lower() for part in re.split(r"[\s./]+", heading) if len(part) >= 2)
    if any(token in stem for token in tokens if len(token) >= 2):
        band, evidence = 10, ["stem 能看出主题"]
    else:
        band, evidence = 5, ["文件名勉强相关"]
    return MetricScore(
        "retrievable.file_name_topic", "retrievable", "L1", 40, True, band,
        raw={"stem": stem},
        evidence=evidence,
    )


def _parent_scores(metrics: list[MetricScore]) -> dict[str, float | None]:
    """Renormalize each parent over applicable children only."""
    out: dict[str, float | None] = {}
    for parent in PARENT_ORDER:
        rows = [item for item in metrics if item.parent == parent and item.applicable]
        if not rows:
            out[parent] = None
            continue
        weight_sum = sum(item.weight for item in rows)
        scored = sum((item.score or 0) / 10 * item.weight for item in rows)
        out[parent] = round(100.0 * scored / weight_sum, 2)
    return out


def _weighted_total(parents: dict[str, float | None]) -> float | None:
    """Drop inapplicable parents (e.g. all-fluent N/A) and renormalize."""
    pairs = [
        (PARENT_WEIGHTS[key], score)
        for key, score in parents.items()
        if score is not None
    ]
    if not pairs:
        return None
    num = sum(weight * score for weight, score in pairs)
    den = sum(weight for weight, _score in pairs)
    return round(num / den, 2)


def _material(user: str) -> str:
    """Text after the first blank line, or the whole user turn."""
    parts = user.split("\n\n", 1)
    return parts[1] if len(parts) == 2 else user


def _atx_headings(content: str) -> list[tuple[int, str]]:
    """Return (level, rest) for ATX headings. H1 is included for H1 checks elsewhere."""
    found: list[tuple[int, str]] = []
    for line in content.splitlines():
        match = _ATX.match(line.strip())
        if match:
            found.append((len(match.group(1)), match.group(2).strip()))
    return found


def _heading_key(line: str) -> str:
    """Strip hashes and collapse whitespace; keep numbering."""
    text = re.sub(r"^#{1,6}\s+", "", line.strip())
    return re.sub(r"\s+", " ", text)


def _same_heading(left: str, right: str) -> bool:
    """True when heading keys match ignoring trailing dots on numbers."""
    return _norm_num(left) == _norm_num(right)


def _norm_num(text: str) -> str:
    """'2.1. 唤出解释器' and '2.1 唤出解释器' compare equal."""
    return re.sub(r"\s+", " ", re.sub(r"^(\d+(?:\.\d+)*)\.\s+", r"\1 ", text)).strip()


def _strip_number(text: str) -> str:
    """Drop leading '2.1. ' so numbering-loss can be detected."""
    return re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text).strip()


def _numbered_parts(line: str) -> tuple[int, str] | None:
    """('2.1.1. Title' → (3, line))."""
    key = _heading_key(line)
    match = _NUMBERED.match(key)
    if not match:
        return None
    parts = match.group(1).split(".")
    return len(parts), key


def _na(metric_id: str, parent: str, layer: str, weight: int, reason: str) -> MetricScore:
    """Inapplicable row: kept in the table, excluded from the parent denominator."""
    return MetricScore(
        metric_id, parent, layer, weight, False, None,
        raw={},
        evidence=[reason],
    )
