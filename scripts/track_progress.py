#!/usr/bin/env python3
"""Cross-essay progress tracking for IELTS writing reports.

Reads every Markdown report written by the ielts-writing-coach skill, extracts
the four criterion scores, the overall band, word counts and error codes, then
aggregates them into a trend table, a persistent-weakness list, and the band
arithmetic that says what it would take to reach the next half band.

Reports are the durable artifact of a correction; without this script they are
write-only. Nothing here calls a model: it is pure parsing and arithmetic, so
the numbers are the same every time.

Standard library only. Python 3.8+.

Usage:
    python3 track_progress.py                       # ./ielts-reports
    python3 track_progress.py ~/my-reports --out trends.md
    python3 track_progress.py --json
    python3 track_progress.py --min-reports 3       # recurring threshold
"""

import argparse
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_format  # noqa: E402  — 分数卡的唯一解析实现，与 report_to_docx 共用

# --- Score card -----------------------------------------------------------------


CRITERION_LABEL = {"TR": "TR/TA", "CC": "CC", "LR": "LR", "GRA": "GRA"}
CRITERION_FULL = {
    "TR": "Task Response / Achievement",
    "CC": "Coherence & Cohesion",
    "LR": "Lexical Resource",
    "GRA": "Grammatical Range & Accuracy",
}

# --- Error codes -----------------------------------------------------------------

CODE_RE = re.compile(r"\b(GRA|LR|CC|TR|TA)-([A-Z]{2,8})\b")

try:
    from ielts_codes import CODES as _CODES, normalize_code as _normalize_code
except ImportError:  # a single script copied out of the bundle
    _CODES, _normalize_code = {}, lambda value: value
CODE_LABELS = {code: entry[1] for code, entry in _CODES.items()}

# --- Report parsing --------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
META_LINE_RE = re.compile(r"^>\s*(.*)$")


def find_section(text, keywords):
    """Return the body of the first heading containing any keyword.

    The score card must be read from its own section: other tables in the report
    (objective data, paragraph maps, vocabulary) also contain numbers, and a
    global table scan picks them up.
    """
    lines = text.splitlines()
    pattern = re.compile("|".join(keywords), re.IGNORECASE)
    start = None
    level = 0
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if start is None:
            if pattern.search(match.group(2)):
                start = index + 1
                level = len(match.group(1))
        elif len(match.group(1)) <= level:
            return "\n".join(lines[start:index])
    if start is not None:
        return "\n".join(lines[start:])
    return ""


def table_rows(block):
    """Yield cell lists for every Markdown table row in a block."""
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue  # separator row
        yield cells


def parse_score_card(text):
    """Extract the four criteria and the overall band from a report.

    Only an explicit score-card section counts. Scanning every table in the
    document would let an aggregate document (a comparison table that happens to
    list four criterion scores) masquerade as a correction report, which is worse
    than skipping the file: it would silently inject invented history.

    The section is read by `report_format.read_score_card`, shared with
    `report_to_docx.py`, so the two can never disagree about what a report says.
    That module locates the score column by its header, because the card now
    carries a range (`5.5-6.5`) next to the tracking midpoint and a positional
    reader would take the lower bound as the score.
    """
    card = report_format.read_score_card(text)
    if card is None:
        return None
    scores = card["scores"]
    if len(scores) < 4:
        return None
    overall = card["overall"]
    if overall is None:
        overall = round_band(sum(scores.values()) / 4.0)
    return {"criteria": scores, "overall": overall,
            "ranges": card["ranges"], "uses_range": card["uses_range"]}


def parse_error_codes(text):
    """Count error codes, preferring the explicit per-code statistics line."""
    counts = {}
    # English reports write "GRA-PREP 1" or "GRA-PREP: 1 time" without the
    # Chinese measure word, so the unit has to be optional.
    for match in re.finditer(
            r"\b([A-Z]{2,3}-[A-Z]{2,8})\b\s*[：:＝=]?\s*(\d{1,3})\s*(?:处|times?|errors?|occurrences?)?",
            text):
        code = match.group(1)
        if code not in CODE_LABELS:
            continue
        counts[code] = max(counts.get(code, 0), int(match.group(2)))
    if counts:
        return counts

    # Fallback: count codes that appear inside the error/defect list table.
    for heading in [r"错误清单", r"缺陷清单", r"错误列表",
                    r"error\s*list", r"error\s*table", r"defect\s*list"]:
        block = find_section(text, [heading])
        if not block:
            continue
        for cells in table_rows(block):
            if len(cells) < 4:
                continue
            joined = " ".join(cells)
            for head, tail in set(CODE_RE.findall(joined)):
                code = "%s-%s" % (head, tail)
                if code in CODE_LABELS:
                    counts[code] = counts.get(code, 0) + 1
        if counts:
            return counts
    return counts


def parse_report(path):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    card = parse_score_card(text)
    if card is None:
        return None  # not a correction report (e.g. an aggregate document)

    name = os.path.basename(path)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not date_match:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    date = date_match.group(1) if date_match else "0000-00-00"

    task_match = re.search(r"task\s*([12])", name, re.IGNORECASE)
    if not task_match:
        task_match = re.search(r"task\s*([12])", text, re.IGNORECASE)
    task = "Task %s" % task_match.group(1) if task_match else "?"

    if re.search(r"general\s*training", text, re.IGNORECASE):
        task += " (GT)"
    elif re.search(r"\bacademic\b", text, re.IGNORECASE) and task.startswith("Task 1"):
        task += " (Academic)"

    words = None
    words_match = re.search(r"(\d+)\s*词", text)
    if words_match:
        words = int(words_match.group(1))

    topic = ""
    topic_match = re.search(r"^>\s*\*{0,2}题目\*{0,2}\s*[：:]\s*(.+)$", text, re.MULTILINE)
    if topic_match:
        topic = topic_match.group(1).strip().strip("*")
        topic = re.sub(r"\s+", " ", topic)[:60]

    return {
        "file": name,
        "path": path,
        "date": date,
        "mtime": os.path.getmtime(path),
        "task": task,
        "words": words,
        "topic": topic,
        "criteria": card["criteria"],
        "overall": card["overall"],
        "total": round(sum(card["criteria"].values()), 2),
        # Carried through so the trend can say out loud that the numbers are
        # interval midpoints. Dropping it here was why the note did not appear.
        "ranges": card.get("ranges", {}),
        "uses_range": card.get("uses_range", False),
        "codes": parse_error_codes(text),
    }


# --- Band arithmetic -------------------------------------------------------------

def round_band(value):
    """Round to the nearest half band; .25 rounds up, .75 rounds up."""
    return math.floor(value * 2 + 0.5) / 2


def next_band_gap(total):
    """How much the four-criterion total must grow to gain half a band.

    The overall band is the mean of four criteria rounded to the nearest half
    band, so the next half band is secured at mean >= current + 0.25, i.e. a
    total increase of 1.0 ... except that the total is what moves. Working from
    the total directly: needed_total = 4 * (current_band + 0.25).
    """
    current = round_band(total / 4.0)
    needed_total = 4 * (current + 0.25)
    return {"current": current, "next": current + 0.5, "needed_total": needed_total,
            "delta": round(needed_total - total, 2)}


def single_fix_options(report, delta):
    """Which single criterion could close the gap, and by how much."""
    options = []
    for key in ("TR", "CC", "LR", "GRA"):
        current = report["criteria"][key]
        target = current + delta
        options.append({
            "criterion": key,
            "label": CRITERION_LABEL[key],
            "from": current,
            "to": round(target, 1),
            "feasible": target <= 9.0,
        })
    return options


# --- Aggregation -----------------------------------------------------------------

def build_summary(reports, min_reports):
    reports = sorted(reports, key=lambda item: (item["date"], item["mtime"], item["file"]))

    # A first-time user points this at an empty directory; that is a normal
    # state, not an error, so it must produce an empty summary rather than a
    # traceback.
    if not reports:
        return {
            "reports": [], "count": 0, "date_range": [None, None],
            "distinct_dates": [], "trend_reliable": False,
            "families": {}, "trends": {}, "spreads": {},
            "recurring": [], "all_codes": [],
            "latest": None, "gap": None, "weakest": None,
            "single_fix_options": [],
        }

    # A trend is only meaningful when the reports are ordered in time. Reports
    # from the same day (or, worse, three unrelated essays) must not be presented
    # as a progression: that would invent a decline that never happened.
    distinct_dates = sorted({report["date"] for report in reports})
    trend_reliable = len(distinct_dates) >= 2

    families = {}
    for report in reports:
        key = "Task 1" if report["task"].startswith("Task 1") else report["task"]
        families.setdefault(key, []).append(report)

    trends = {}
    spreads = {}
    for key, group in families.items():
        spreads[key] = {
            criterion: {
                "min": min(report["criteria"][criterion] for report in group),
                "max": max(report["criteria"][criterion] for report in group),
            }
            for criterion in ("TR", "CC", "LR", "GRA")
        }
        if len(group) < 2 or not trend_reliable:
            trends[key] = None
            continue
        first, last = group[0], group[-1]
        deltas = {}
        first_scores = {}
        last_scores = {}
        for criterion in ("TR", "CC", "LR", "GRA"):
            first_scores[criterion] = first["criteria"][criterion]
            last_scores[criterion] = last["criteria"][criterion]
            deltas[criterion] = round(last["criteria"][criterion] - first["criteria"][criterion], 1)
        trends[key] = {
            "first": first["file"],
            "last": last["file"],
            "deltas": deltas,
            "first_scores": first_scores,
            "last_scores": last_scores,
            "first_overall": first["overall"],
            "last_overall": last["overall"],
            "overall_delta": round(last["overall"] - first["overall"], 1),
        }

    code_reports = {}
    code_totals = {}
    for report in reports:
        for code, count in report["codes"].items():
            code_reports[code] = code_reports.get(code, 0) + 1
            code_totals[code] = code_totals.get(code, 0) + count

    recurring = sorted(
        [
            {"code": code, "reports": code_reports[code], "total": code_totals[code],
             "label": CODE_LABELS.get(code, "")}
            for code in code_reports
            if code_reports[code] >= min_reports
        ],
        key=lambda item: (-item["reports"], -item["total"], item["code"]),
    )

    all_codes = sorted(
        [
            {"code": code, "reports": code_reports[code], "total": code_totals[code],
             "label": CODE_LABELS.get(code, "")}
            for code in code_reports
        ],
        key=lambda item: (-item["total"], item["code"]),
    )

    latest = reports[-1]
    gap = next_band_gap(latest["total"])
    weakest = min(latest["criteria"], key=lambda key: latest["criteria"][key])

    return {
        "reports": reports,
        "count": len(reports),
        "date_range": [reports[0]["date"], reports[-1]["date"]] if reports else [None, None],
        "distinct_dates": distinct_dates,
        "trend_reliable": trend_reliable,
        "families": {key: len(group) for key, group in families.items()},
        "trends": trends,
        "spreads": spreads,
        "recurring": recurring,
        "all_codes": all_codes,
        "latest": latest,
        "gap": gap,
        "weakest": weakest,
        "single_fix_options": single_fix_options(latest, gap["delta"]),
    }


# --- Rendering -------------------------------------------------------------------

def render_markdown(summary, min_reports):
    if summary["count"] == 0:
        return ("# 批改历史趋势\n\n"
                "未找到可解析的批改报告。\n\n"
                "报告目录里需要有本 skill 生成的报告（含「分数卡」表格），"
                "其他 Markdown 文件会被自动跳过。\n")

    out = []
    add = out.append
    add("# 批改历史趋势\n")
    add("> 由 `scripts/track_progress.py` 从历史报告中提取，纯统计，无模型参与。\n")
    add("- 报告数量：**%d**" % summary["count"])
    add("- 日期范围：%s → %s" % (summary["date_range"][0], summary["date_range"][1]))
    add("- 任务分布：%s" % "、".join("%s ×%d" % (k, v) for k, v in sorted(summary["families"].items())))
    add("")

    add("## 1. 分项趋势\n")
    # Reports written after the range layout carry an interval per criterion. The
    # table has to stay numeric for the arithmetic below, so the numbers are the
    # midpoints -- and the reader is told so rather than left to assume the
    # report claimed a single score.
    if any(report.get("uses_range") for report in summary["reports"]):
        add("> 报告用的是**区间**格式；下表的数字是各区间**中点**（追踪需要可比数值，"
            "不代表报告给的是单点分数）。区间见各报告的 `## 分数卡`。\n")
    add("| 日期 | 任务 | 词数 | TR/TA | CC | LR | GRA | 总分 | 文件 |")
    add("|---|---|---|---|---|---|---|---|---|")
    for report in summary["reports"]:
        crit = report["criteria"]
        add("| %s | %s | %s | %s | %s | %s | %s | **%s** | `%s` |" % (
            report["date"], report["task"],
            report["words"] if report["words"] is not None else "—",
            crit["TR"], crit["CC"], crit["LR"], crit["GRA"], report["overall"], report["file"],
        ))
    add("")

    add("## 2. 变化（同一任务类型的首篇 → 末篇）\n")
    if summary["count"] > 1 and not summary["trend_reliable"]:
        add("### ⚠️ 不计算趋势变化\n")
        add("所有报告都落在同一天（%s），**无法判断先后顺序**。" % summary["distinct_dates"][0])
        add("")
        add("趋势只有在报告跨越不同日期时才有意义。把同一天（或互不相关的几篇）报告按文件名排序"
            "再相减，会得出一个「进步/退步」的数字，但那个数字是虚构的——**本脚本拒绝这样做**。")
        add("")
        add("下面给出的是**各分项的分布区间**，这是顺序未知时仍然成立的信息：")
        add("")
        for family, spread in sorted(summary["spreads"].items()):
            add("**%s**（%d 篇）\n" % (family, summary["families"][family]))
            add("| 项目 | 最低 | 最高 | 区间 |")
            add("|---|---|---|---|")
            for criterion in ("TR", "CC", "LR", "GRA"):
                low = spread[criterion]["min"]
                high = spread[criterion]["max"]
                add("| %s | %s | %s | %s |" % (
                    CRITERION_LABEL[criterion], low, high,
                    "%.1f" % round(high - low, 1) if high != low else "—"))
            add("")
        add("> 要看到真正的趋势，需要**同一类型任务、不同日期**的多次批改记录。")
        add("")
    elif not summary["trends"] or all(value is None for value in summary["trends"].values()):
        add("⚠️ 每种任务类型至少需要 2 份**不同日期**的报告才能比较趋势。继续积累批改记录后再看这一节。")
        add("")
        add("> 注意：Task 1 与 Task 2 的评分项目不同（Task Achievement vs Task Response），"
            "**不能跨任务类型比较**，所以趋势按任务类型分开计算。")
        add("")
    else:
        for family, trend in sorted(summary["trends"].items()):
            if trend is None:
                add("- **%s**：只有 1 份报告，暂无趋势。" % family)
                continue
            add("### %s（%s → %s）\n" % (family, trend["first"], trend["last"]))
            add("| 项目 | 首篇 | 末篇 | 变化 |")
            add("|---|---|---|---|")
            for criterion in ("TR", "CC", "LR", "GRA"):
                delta = trend["deltas"][criterion]
                mark = "📈 进步" if delta > 0 else ("📉 **退步**" if delta < 0 else "➖ 持平")
                add("| %s | %s | %s | %+0.1f %s |" % (
                    CRITERION_LABEL[criterion], trend["first_scores"][criterion],
                    trend["last_scores"][criterion], delta, mark))
            add("| **总分** | %s | %s | %+0.1f |" % (
                trend["first_overall"], trend["last_overall"], trend["overall_delta"]))
            add("")

    latest = summary["latest"]
    gap = summary["gap"]
    add("## 3. 当前状态与跨档算术\n")
    add("最新一篇：`%s`（%s，%s）" % (latest["file"], latest["date"], latest["task"]))
    add("")
    add("| 项目 | 分数 |")
    add("|---|---|")
    for criterion in ("TR", "CC", "LR", "GRA"):
        add("| %s（%s） | %s |" % (CRITERION_FULL[criterion], criterion, latest["criteria"][criterion]))
    add("| **总分** | **%s** |" % latest["overall"])
    add("")
    add("四项总和 **%.1f** ／ 当前总分 **%s** ／ 下一档 **%s**" % (
        latest["total"], gap["current"], gap["next"]))
    add("")
    add("**跨档需要四项总和增加 %.1f**（达到 %.1f）。" % (gap["delta"], gap["needed_total"]))
    add("")
    add("这就是为什么**单项提高 0.5 分通常不会改变总分**——"
        "总分是四项平均再取整，四舍五入的门槛落在 1.5 分的总量级上。")
    add("")
    add("**当前最弱项：%s（%s）**" % (
        CRITERION_FULL[summary["weakest"]], CRITERION_LABEL[summary["weakest"]]))
    add("")
    add("| 若只靠这一项填平差距 | 需从 | 提到 | 可行性 |")
    add("|---|---|---|---|")
    for option in summary["single_fix_options"]:
        if not option["feasible"]:
            verdict = "❌ 超出满分，单项做不到"
        elif option["to"] <= option["from"] + 1.0:
            verdict = "✅ 一项即可，代价较小"
        elif option["to"] <= option["from"] + 2.0:
            verdict = "⚠️ 一项即可，但需显著提升"
        else:
            verdict = "❌ 需同时提升两项"
        add("| %s | %s | %s | %s |" % (
            option["label"], option["from"], option["to"], verdict))
    add("")

    add("## 4. 错误代码频次（跨篇累计）\n")
    if not summary["all_codes"]:
        add("历史报告中没有可解析的错误代码统计。")
        add("")
        add("> 报告需要在「错误清单」后包含 `**按代码统计**：GRA-ART 6 处 ｜ LR-COLL 3 处` 这样的汇总行，"
            "本脚本才能跨篇累计。见 `templates/report-template.md`。")
        add("")
    else:
        add("| 代码 | 含义 | 出现篇数 | 累计次数 |")
        add("|---|---|---|---|")
        for entry in summary["all_codes"]:
            add("| `%s` | %s | %d | %d |" % (
                entry["code"], entry["label"], entry["reports"], entry["total"]))
        add("")

    add("## 5. 持续性问题（出现在 ≥%d 篇报告中）\n" % min_reports)
    if not summary["recurring"]:
        add("✅ 没有跨篇重复出现的错误代码。")
        add("")
        add("这通常意味着两件事之一：问题确实是随机的笔误；或者报告数量还太少。"
            "跨篇重复才是**系统性弱点**的证据。")
    else:
        add("以下问题**不是偶发笔误，而是稳定出现的系统性弱点**——它们比单篇错误更值得优先处理：")
        add("")
        add("| 代码 | 含义 | 出现篇数 | 累计次数 | 判断 |")
        add("|---|---|---|---|---|")
        for entry in summary["recurring"]:
            share = entry["reports"] / summary["count"]
            if summary["count"] >= 3 and entry["reports"] == summary["count"]:
                judgement = "🔴 每篇都出现"
            elif share >= 0.5 and entry["reports"] >= 3:
                judgement = "🟠 多数篇出现"
            else:
                judgement = "🟡 出现多次"
            add("| `%s` | %s | %d / %d | %d | %s |" % (
                entry["code"], entry["label"], entry["reports"], summary["count"],
                entry["total"], judgement))
        add("")
        top = summary["recurring"][0]
        add("**最该优先处理的模式：`%s`（%s）** —— 出现在 %d/%d 篇报告中，累计 %d 处。" % (
            top["code"], top["label"], top["reports"], summary["count"], top["total"]))
        add("")
    add("---\n")
    add("*本文件由脚本生成，可重复运行覆盖。数据来源：*")
    for report in summary["reports"]:
        add("- `%s`" % report["file"])
    add("")
    if summary.get("skipped"):
        add("**已跳过（没有「分数卡」小节，按非报告文件处理）**：%s" % "、".join(
            "`%s`" % name for name in summary["skipped"]))
        add("")
        add("> 报告必须包含 `## 分数卡` 小节才能被统计。这是刻意的："
            "汇总类文档里的对比表格也含四项分数，若允许全文扫描会把它们误当成批改记录，"
            "从而污染趋势数据。")
        add("")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aggregate IELTS writing correction reports into a progress trend.")
    parser.add_argument("reports_dir", nargs="?", default="ielts-reports",
                        help="directory holding the Markdown reports (default: ./ielts-reports)")
    parser.add_argument("--out", help="write the Markdown trend report to this path")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--min-reports", type=int, default=2,
                        help="how many reports a code must appear in to count as recurring (default: 2)")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.reports_dir):
        sys.stderr.write("no such directory: %s\n" % args.reports_dir)
        return 2

    paths = sorted(glob.glob(os.path.join(args.reports_dir, "**", "*.md"), recursive=True))
    reports = []
    skipped = []
    for path in paths:
        name = os.path.basename(path)
        if name.startswith(".") or name.startswith("_"):
            continue
        parsed = parse_report(path)
        if parsed is not None:
            reports.append(parsed)
        else:
            skipped.append(name)

    summary = build_summary(reports, max(1, args.min_reports))
    summary["skipped"] = skipped

    if args.json:
        rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        rendered = render_markdown(summary, max(1, args.min_reports))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        sys.stderr.write("wrote %s (%d reports)\n" % (args.out, len(reports)))
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
