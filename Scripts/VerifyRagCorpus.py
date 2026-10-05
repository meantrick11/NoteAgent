"""Re-check the corpus v1 audit claims and the unanswerable annotations.

This is the evidence behind `evals/rag/corpus/v1/audit.md` and the ten
`unanswerable` rows of `evals/rag/queries.v1.jsonl`: every claim below is a
mechanical check on the frozen copies, so a re-run either passes all of them or
names exactly which one stopped being true. Exit code 1 means the corpus or the
annotations drifted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORPUS = Path("evals/rag/corpus/v1")
H2 = "## "
H1LIKE = re.compile(r"^# \S")


def _text(corpus: Path, name: str) -> str:
    return (corpus / "notes" / f"{name}.md").read_text(encoding="utf-8")


def audit_checks(corpus: Path) -> list[tuple[str, bool]]:
    """Verify the per-note defects recorded in audit.md."""
    checks: list[tuple[str, bool]] = []
    bt = _text(corpus, "Backtracking")
    checks.append(
        (
            "Backtracking 有两个同级 H2 覆盖同一道 LC93",
            "## 切割问题实战：复原IP地址（LC93）" in bt
            and "## 切割问题实战：LeetCode 93 复原IP地址" in bt,
        )
    )
    checks.append(
        ('Backtracking 逐字重复句 "- 结果用".".join(curpath) 拼接" 出现 2 次',
         bt.count('- 结果用 ".".join(curpath) 拼接') == 2)
    )

    ov = _text(corpus, "Python_Tutorial_Overview")
    fence_hits, in_fence = 0, False
    for line in ov.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and H1LIKE.match(line):
            fence_hits += 1
    checks.append(("Python_Tutorial_Overview 围栏内形如 H1 的注释 >= 6 处", fence_hits >= 6))

    it = _text(corpus, "Python_Tutorial_Interpreter")
    fences = re.findall(r"^```(\S*)", it, flags=re.M)
    checks.append(
        (
            f"Python_Tutorial_Interpreter 12 个围栏全部无语言标注（实得 {len(fences)}）",
            len(fences) == 12 and all(not item for item in fences),
        )
    )
    checks.append(
        (
            "Python_Tutorial_Interpreter 脚注 [1] 定义落在末节",
            "[1] Unix 系统中，为了不与同时安装的 Python 2.x 冲突" in it,
        )
    )

    sq = _text(corpus, "SQLAlchemy_psycopg")
    lines = sq.splitlines()
    tight = [
        index + 1
        for index in range(1, len(lines))
        if lines[index].startswith(H2) and lines[index - 1].strip()
    ]
    checks.append((f"SQLAlchemy_psycopg 6 个二级标题前缺空行（实得 {len(tight)}）", len(tight) == 6))

    owl = _text(corpus, "OWL2_Document_Overview")
    checks.append(("OWL2 语法对比表存在", "| 语法名称 | 规范 | 状态 | 用途 |" in owl))
    checks.append(("OWL2 文档路线图表存在", "| 序号 | 类型 | 文档 |" in owl))

    sad = _text(corpus, "Software_Architecture_Design")
    dup = "使读者全面了解系统的设计方案和实现细节。"
    checks.append((f"Software_Architecture_Design 近逐字重复句出现 {sad.count(dup)} 次", sad.count(dup) >= 2))

    checks.append(
        (
            "Agent_Design_Patterns 无依据性能断言存在",
            "各关注点分离处理，性能优于单次调用" in _text(corpus, "Agent_Design_Patterns"),
        )
    )

    wet = _text(corpus, "Writing_Effective_Tools_for_Agents")
    checks.append(("WET 悬空脚注 [1]（正文引用但无定义）", "> [1] 本文讨论的是" in wet and "[1]:" not in wet))
    checks.append(("WET 记录了 25,000 token 上限", "Claude Code 默认把工具响应限制为 25,000 token" in wet))

    binary = _text(corpus, "BinaryTree")
    stamped = re.findall(r"^## \[\d\d:", binary, flags=re.M)
    checks.append((f"BinaryTree 4 个时间戳标题（实得 {len(stamped)}）", len(stamped) == 4))

    checks.append(("Python_Tutorial_Intro 的 H1 不含章号", _text(corpus, "Python_Tutorial_Intro").splitlines()[0] == "# Python_Tutorial_Intro"))
    source = corpus / "sources" / "python_tutorial_ch1_whetting_your_appetite.md"
    if source.is_file():
        checks.append(("英文源文含被压缩掉的限定语 for some of these tasks", "for some of these tasks" in source.read_text(encoding="utf-8")))
    return checks


def unanswerable_probe(corpus: Path, queries_path: Path) -> list[tuple[str, bool]]:
    """Check that no answer signature of an unanswerable query exists in the corpus.

    A signature is a set of terms that must appear **on one line** to count as an
    answer. Requiring co-occurrence matters: 「测试套件」 alone appears in an unrelated
    sentence about C/C++/Java, and 「最快」 appears in the interpreter's command-line
    editing paragraph — neither answers the question that probes it.
    """
    probes: dict[str, list[list[str]]] = {
        "q31": [["O(n!)"], ["阶乘"], ["渐近"], ["时间复杂度", "回溯"]],
        "q32": [["快多少"], ["性能对比"], ["基准测试"], ["PyPy", "倍"]],
        "q33": [["层序", "递归写法"], ["层序", "递归实现"]],
        "q34": [["证明过程"], ["证明思路"], ["推导过程"]],
        "q35": [["最低", "延迟"], ["最快", "模式"], ["延迟对比"]],
        "q36": [["Kubernetes"], ["Ingress"], ["灰度"]],
        "q37": [["GIL"], ["全局解释器锁"]],
        "q38": [["used"], ["去重"], ["重复元素"]],
        "q39": [["示例任务"], ["几个任务"], ["任务数量"]],
        "q40": [["测试套件", "OWL"], ["多少条", "测试"], ["用例数"]],
    }
    lines = [
        line
        for path in sorted((corpus / "notes").glob("*.md"))
        for line in (corpus / "notes" / path.name).read_text(encoding="utf-8").splitlines()
    ]
    rows = [
        json.loads(line)
        for line in queries_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unanswerable = {row["id"] for row in rows if not row["answerable"]}
    checks: list[tuple[str, bool]] = []
    for query_id, signatures in probes.items():
        hits = [
            signature
            for signature in signatures
            if any(all(term in line for term in signature) for line in lines)
        ]
        checks.append((f"{query_id} 无答案：答案特征均未在语料出现（命中 {hits or '无'}）", not hits))
    covered = set(probes) & unanswerable
    checks.append((f"探测覆盖全部无答案样例（{len(covered)}/{len(unanswerable)}）", covered == unanswerable))
    return checks


def main() -> int:
    """Run every check and report the ones that no longer hold."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--queries", type=Path, default=Path("evals/rag/queries.v1.jsonl"))
    args = parser.parse_args()

    checks = audit_checks(args.corpus)
    if args.queries.is_file():
        checks += unanswerable_probe(args.corpus, args.queries)
    else:
        print(f"note: {args.queries} not found, skipped the unanswerable probe")

    failed = 0
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
        failed += int(not ok)
    print(f"\n{len(checks) - failed}/{len(checks)} verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
