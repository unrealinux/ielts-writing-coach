#!/usr/bin/env python3
"""Aggregate the user's own calibration records into an accuracy verdict.

    python3 scripts/calibrate.py ~/ielts-calibration

The bundle estimates bands but has never been measured against anyone's real
essays -- the thresholds were calibrated on a handful of samples its author
wrote. This script cannot fix that; what it can do is let one user answer the
only accuracy question that matters to them: *on my essays, does this tool run
high, low, or neither?*

It reads records the user fills in from `templates/calibration-log.md`. It
refuses to state a direction below `--min-pairs` paired scores, and refuses to
rank error codes below `--min-signals` findings, because an average over three
essays is not a systematic bias and a "most common mistake" drawn from two
entries is noise wearing a number. When it cannot conclude, it says so.

Standard library only. Python 3.8+.
"""

import argparse
import json
import os
import re
import sys

# A record is one Markdown file. The labels are accepted in Chinese (what the
# shipped template uses) and in English, because a user may translate the
# template before filling it in -- and a silently empty result would be worse
# than accepting both spellings.
#
# Horizontal whitespace only: `\s` also matches a newline, so `[:：]\s*(.+?)`
# would step over the line ending of a *blank* field and capture the text of the
# next line as its value. A user who left "your total" empty had the following
# heading read as their score's source. Distinguishing "not filled in" from
# "filled in and unparsable" is the whole point of these fields; a pattern that
# crosses lines destroys that distinction.
FIELD_PATTERNS = {
    "date": (r"^[ \t]*[-*][ \t]*(?:日期|date)[ \t]*[:：][ \t]*(.+?)[ \t]*$",),
    "task": (r"^[ \t]*[-*][ \t]*(?:题型|task)[ \t]*[:：][ \t]*(.+?)[ \t]*$",),
    "tool_total": (r"^[ \t]*[-*][ \t]*(?:工具总分|tool total)[ \t]*[:：][ \t]*(.+?)[ \t]*$",),
    "own_total": (r"^[ \t]*[-*][ \t]*(?:你的总分|your total)[ \t]*[:：][ \t]*(.+?)[ \t]*$",),
    "own_source": (r"^[ \t]*[-*][ \t]*(?:你的判断来源|your source)[ \t]*[:：][ \t]*(.+?)[ \t]*$",),
}

# The two tables that carry the findings. Either heading opens a section whose
# first table is the one we want.
SECTION_PATTERNS = {
    "false_positive": r"^#{2,4}\s*误报|^#{2,4}\s*false positive",
    "false_negative": r"^#{2,4}\s*漏报|^#{2,4}\s*missed|^#{2,4}\s*false negative",
}

HEADING_RE = re.compile(r"^#{1,6}\s")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
# Error codes look like GRA-ART, LR-COLL, TR-UNDEV; a row without one is still
# counted, just grouped as unlabelled rather than dropped.
CODE_RE = re.compile(r"\b([A-Z]{2,4}-[A-Z]{2,12})\b")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def cell_value(raw):
    """Return the field's value, or '' when the user left it blank.

    The template ships with empty values, so 'blank' is the normal state of a
    fresh copy -- it must not be mistaken for a value.
    """
    text = raw.strip()
    # Strip a trailing inline comment or parenthetical the user may have added.
    return text


def parse_number(raw):
    """Pull the first number out of a cell, tolerating '6.0' and '6.0（预估）'."""
    if not raw:
        return None
    match = NUMBER_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def read_fields(body):
    fields = {}
    for name, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, body, re.MULTILINE)
            if match:
                fields[name] = cell_value(match.group(1))
                break
    return fields


def read_table(body, pattern):
    """Return the first table's data rows found after a heading matching `pattern`.

    Stops at the next heading so a later table (or the template's own example
    rows) cannot leak into this section.
    """
    lines = body.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            start = index + 1
            break
    if start is None:
        return []
    rows = []
    for line in lines[start:]:
        if HEADING_RE.match(line):
            break
        if SEPARATOR_RE.match(line):
            continue
        match = TABLE_ROW_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if not cells or not cells[0]:
            continue
        # Skip the header row by name, not by position: the template's columns
        # are labelled, and a header is not a finding.
        if cells[0] in ("工具的说法", "原文", "What the tool said", "Original"):
            continue
        rows.append(cells)
    return rows


def parse_record(path):
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    fields = read_fields(body)
    record = {
        "file": os.path.basename(path),
        "date": fields.get("date", ""),
        "task": fields.get("task", ""),
        "tool_total": parse_number(fields.get("tool_total", "")),
        "own_total": parse_number(fields.get("own_total", "")),
        "own_source": fields.get("own_source", ""),
        "false_positives": read_table(body, SECTION_PATTERNS["false_positive"]),
        "false_negatives": read_table(body, SECTION_PATTERNS["false_negative"]),
    }
    if not record["date"]:
        # Fall back to a date prefix in the filename, so a record that forgot
        # the field still sorts sensibly instead of landing at the top.
        match = re.match(r"(\d{4}-\d{2}-\d{2})", record["file"])
        record["date"] = match.group(1) if match else ""
    return record


def collect(directory):
    if not os.path.isdir(directory):
        return None
    records = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md") or name.startswith("_"):
            continue
        records.append(parse_record(os.path.join(directory, name)))
    return records


def code_of(row):
    for cell in row:
        match = CODE_RE.search(cell)
        if match:
            return match.group(1)
    return "（未标注代码）"


def summarise(records, min_pairs, min_signals):
    paired = [r for r in records if r["tool_total"] is not None and r["own_total"] is not None]
    deltas = [{"file": r["file"], "date": r["date"], "tool": r["tool_total"],
               "own": r["own_total"], "source": r["own_source"],
               "delta": round(r["tool_total"] - r["own_total"], 2)} for r in paired]

    signals = []
    for record in records:
        for row in record["false_positives"]:
            signals.append({"kind": "false_positive", "code": code_of(row),
                            "text": row[0], "file": record["file"]})
        for row in record["false_negatives"]:
            signals.append({"kind": "false_negative", "code": code_of(row),
                            "text": row[0], "file": record["file"]})

    by_code = {}
    for signal in signals:
        entry = by_code.setdefault(signal["code"], {"false_positive": 0, "false_negative": 0})
        entry[signal["kind"]] += 1

    return {
        "records": len(records),
        "paired": len(paired),
        "unpaired": len(records) - len(paired),
        # The scalar fields as parsed, before any aggregation. `--json` is the
        # structured view, so it has to expose what was actually read: without
        # this, a field that silently captured the wrong line is invisible in
        # the machine-readable output and only shows up as odd prose in the
        # Markdown. selfcheck asserts on these to catch exactly that.
        "entries": [{"file": record["file"], "date": record["date"], "task": record["task"],
                     "tool_total": record["tool_total"], "own_total": record["own_total"],
                     "own_source": record["own_source"],
                     "false_positives": len(record["false_positives"]),
                     "false_negatives": len(record["false_negatives"])}
                    for record in records],
        "dates": sorted({r["date"] for r in records if r["date"]}),
        "tasks": sorted({r["task"] for r in records if r["task"]}),
        "deltas": deltas,
        "signals": signals,
        "by_code": by_code,
        "min_pairs": min_pairs,
        "min_signals": min_signals,
        "high": len([d for d in deltas if d["delta"] > 0]),
        "low": len([d for d in deltas if d["delta"] < 0]),
        "equal": len([d for d in deltas if d["delta"] == 0]),
        "mean_delta": (round(sum(d["delta"] for d in deltas) / len(deltas), 2)
                       if deltas else None),
    }


def render(summary):
    out = []
    add = out.append
    add("# 批改校准结果\n")
    add("> 由 `scripts/calibrate.py` 从你自己的校准记录里统计，纯计算，无模型参与。\n")

    if not summary["records"]:
        add("**目录里没有找到校准记录**（`*.md`，跳过 `_` 开头的文件）。\n")
        add("从 `templates/calibration-log.md` 复制一份，填好后放进同一个目录再跑一次。\n")
        return "\n".join(out)

    add("- 记录数量：**%d**" % summary["records"])
    if summary["dates"]:
        span = ("%s → %s" % (summary["dates"][0], summary["dates"][-1])
                if len(summary["dates"]) > 1 else summary["dates"][0])
        add("- 日期范围：%s" % span)
    if summary["tasks"]:
        add("- 题型分布：%s" % "、".join(summary["tasks"]))
    add("- **填了自己判断的：%d / %d**" % (summary["paired"], summary["records"]))
    add("")

    # ---- 1. band bias -----------------------------------------------------
    add("## 1. 分数偏差\n")
    if not summary["paired"]:
        add("没有任何一篇填了「你的总分」，**无法判断偏差**。")
        add("")
        add("这不是失败——它只是说明这份记录目前只记了工具说了什么，没有可比的对照。")
        add("填入你的判断（老师给的分、官方模考分，或你自己核对后的估计）后重跑。")
        add("")
    else:
        add("| 日期 | 工具 | 你 | 差值（工具 − 你） | 来源 |")
        add("|---|---|---|---|---|")
        for item in summary["deltas"]:
            add("| %s | %.1f | %.1f | %+0.1f | %s |" % (
                item["date"] or item["file"], item["tool"], item["own"],
                item["delta"], item["source"] or "—"))
        add("")
        if summary["paired"] < summary["min_pairs"]:
            add("⚠️ **只有 %d 篇有对照，不足以下结论**（门槛 %d 篇）。"
                % (summary["paired"], summary["min_pairs"]))
            add("")
            add("上面列出的是**逐篇差值**，不是偏差结论。%d 篇的平均差值和真实的系统性偏差"
                "是两件事：把几篇作文的平均值当成「这个工具偏高 0.5」，"
                "和当初拿三个自造样本归纳出「跨档一律 +1.5」是同一个错误。\n"
                % summary["paired"])
            add("继续记录，攒到 %d 篇有对照的再来看这一段。" % summary["min_pairs"])
            add("")
        else:
            add("平均差值：**%+0.2f**" % summary["mean_delta"])
            add("")
            add("| 方向 | 篇数 |")
            add("|---|---|")
            add("| 工具偏高 | %d |" % summary["high"])
            add("| 工具偏低 | %d |" % summary["low"])
            add("| 一致 | %d |" % summary["equal"])
            add("")
            high, low, equal = summary["high"], summary["low"], summary["equal"]
            # The direction is carried by the essays where the two disagree. What
            # matters is not whether *every* essay leans the same way -- a tie is
            # not evidence against a lean -- but whether both directions ever
            # appear. "4 high / 0 low / 2 tied" is a one-sided result, and calling
            # it random because it is not unanimous would throw away the signal
            # the user spent six essays collecting.
            if high == 0 and low == 0:
                add("**全部一致**——在你这批作文上，工具的分数与你的判断逐篇吻合。")
            elif high > 0 and low == 0:
                add("**从未出现工具偏低**——%d 篇偏高、%d 篇一致、0 篇偏低。"
                    "这是一致方向的偏差，可以在心里先减掉：读分数时把工具的分"
                    "往下调约 **%0.2f**。" % (high, equal, abs(summary["mean_delta"])))
                add("")
                add("注意「往下调」只对总分成立。四项里哪一项最弱、差什么才能进档——"
                    "这两件事不随偏差失效，仍然可读。")
            elif low > 0 and high == 0:
                add("**从未出现工具偏高**——%d 篇偏低、%d 篇一致、0 篇偏高。"
                    "这是一致方向的偏差，可以在心里先加上：读分数时把工具的分"
                    "往上调约 **%0.2f**。" % (low, equal, abs(summary["mean_delta"])))
                add("")
                add("注意「往上调」只对总分成立。四项里哪一项最弱、差什么才能进档——"
                    "这两件事不随偏差失效，仍然可读。")
            else:
                add("偏高与偏低**都出现过**（%d / %d），说明偏差更像**逐篇的随机误差**"
                    "而不是系统性偏差。" % (high, low))
                add("")
                add("这种情况下看报告里的证据比看分数有用：分可能差 0.5，"
                    "但「哪一项最弱、差什么才能进档」这两件事仍然可读。")
            add("")

    # ---- 2. false positives and negatives ---------------------------------
    add("## 2. 误报与漏报\n")
    false_positives = [s for s in summary["signals"] if s["kind"] == "false_positive"]
    false_negatives = [s for s in summary["signals"] if s["kind"] == "false_negative"]
    add("- 误报（工具说错、其实没错）：**%d** 条" % len(false_positives))
    add("- 漏报（确实错了、工具没提）：**%d** 条" % len(false_negatives))
    add("")
    if not summary["signals"]:
        add("两处表格都是空的。如果确实没有发现误报漏报，这是好消息；")
        add("如果只是没顾上填，那么上面的分数偏差就是这份记录唯一的内容。")
        add("")
    elif len(summary["signals"]) < summary["min_signals"]:
        add("⚠️ **只有 %d 条，不足以说「最常错在哪儿」**（门槛 %d 条）。全部列出："
            % (len(summary["signals"]), summary["min_signals"]))
        add("")
        for signal in summary["signals"]:
            add("- [%s] `%s` %s" % (
                "误报" if signal["kind"] == "false_positive" else "漏报",
                signal["code"], signal["text"]))
        add("")
    else:
        add("| 代码 | 误报 | 漏报 | 合计 |")
        add("|---|---|---|---|")
        for code, counts in sorted(summary["by_code"].items(),
                                   key=lambda item: -(item[1]["false_positive"]
                                                      + item[1]["false_negative"])):
            add("| `%s` | %d | %d | %d |" % (
                code, counts["false_positive"], counts["false_negative"],
                counts["false_positive"] + counts["false_negative"]))
        add("")
        top = max(summary["by_code"].items(),
                  key=lambda item: item[1]["false_positive"] + item[1]["false_negative"])
        add("出现最多的是 **`%s`**（%d 条）。这一类判据在你的作文上最不可靠，"
            "看到它时多核对一遍原文；报告里其他代码的提示可以正常采信。"
            % (top[0], top[1]["false_positive"] + top[1]["false_negative"]))
        add("")

    # ---- 3. how much this is worth ---------------------------------------
    add("## 3. 这个结论有多可信（必读）\n")
    add("**不是盲测。** 你是先读了工具的输出，才判断它对不对的——知道答案之后再评判，"
        "人会不自觉地觉得「说得有道理」。所以这里量到的偏差通常会比真实偏差**小**。\n")
    add("**样本量决定结论强度。** 当前：%d 篇记录，其中 %d 篇有对照、%d 条误报漏报。"
        % (summary["records"], summary["paired"], len(summary["signals"])))
    add("")
    add("**这份记录能回答的和不能回答的：**\n")
    add("| 能回答 | 不能回答 |")
    add("|---|---|")
    add("| 这个工具**对我**偏高还是偏低 | 这个工具**本身**准不准 |")
    add("| 它最常在我这类作文上错在哪一类问题 | 它在别人、别的分数段上表现如何 |")
    add("| 我该按它安排复习，还是先在心里减 0.5 | 它和真实考官打分的相关程度 |")
    add("")
    add("要回答右边那一列，需要多人的记录汇总，并且判断要在看到工具输出**之前**做出——"
        "那是另一件事，不是这份文件能做的。\n")
    add("---")
    add("")
    add("*本文件由 `scripts/calibrate.py` 生成。判断标准是你自己定的，工具只做统计。*")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aggregate your own correction-calibration records into an accuracy verdict.")
    parser.add_argument("records_dir", nargs="?", default="ielts-calibration",
                        help="directory of filled calibration logs (default: ielts-calibration)")
    parser.add_argument("--out", help="write the Markdown result to this path")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument("--min-pairs", type=int, default=5,
                        help="paired scores needed before stating a bias direction (default: 5)")
    parser.add_argument("--min-signals", type=int, default=3,
                        help="findings needed before ranking error codes (default: 3)")
    args = parser.parse_args(argv)

    records = collect(args.records_dir)
    if records is None:
        sys.stderr.write("no such directory: %s\n" % args.records_dir)
        return 2
    summary = summarise(records, args.min_pairs, args.min_signals)

    if args.json:
        rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        rendered = render(summary)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        sys.stderr.write("wrote %s\n" % args.out)
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
