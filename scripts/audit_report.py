#!/usr/bin/env python3
"""Audit a correction report for the same defect being charged to two criteria.

One weakness must be charged to exactly one criterion. A run-on sentence that
also muddles the reference is *one* defect, not a grammar error plus a cohesion
error plus a task-response error -- scoring it three times depresses the band
systematically, which is as harmful as inflating it.

This script does not decide what the owner is; that is a judgement about the
essay. It finds every quoted fragment that the report uses as deduction evidence
under more than one criterion and requires the report to *declare* an owner for
it. An undeclared fragment is the violation.

Standard library only. Python 3.8+.

Usage:
    python3 audit_report.py ielts-reports/2026-09-13-task2.md
    python3 audit_report.py ielts-reports/ --json
    python3 audit_report.py report.md --min-length 20
"""

import argparse
import glob
import json
import os
import re
import sys

CRITERIA = [
    ("TR", r"task\s*response|task\s*achievement|\bTR\b|\bTA\b|任务回应|任务达成"),
    ("CC", r"coherence|\bCC\b|连贯|衔接"),
    ("LR", r"lexical|\bLR\b|词汇"),
    ("GRA", r"grammatical|\bGRA\b|语法"),
]
CRITERION_LABEL = {"TR": "Task Response / Achievement", "CC": "Coherence & Cohesion",
                   "LR": "Lexical Resource", "GRA": "Grammatical Range & Accuracy"}

DIAGNOSIS_HEADINGS = [r"逐项诊断", r"分项诊断", r"criterion\s*diagnosis"]
OWNERSHIP_HEADINGS = [r"缺陷归属", r"归属审计", r"charge\s*ownership", r"defect\s*ownership"]
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# Evidence is quoted three ways in practice; short backticked tokens (codes,
# single words) are below the length floor and fall out automatically.
QUOTE_PATTERNS = [
    re.compile(r'"([^"\n]{0,300})"'),
    re.compile(r"\u201c([^\u201d\n]{0,300})\u201d"),
    re.compile(r"`([^`\n]{0,300})`"),
]
EMPHASIS_RE = re.compile(r"\*\*|`|\*")


def find_section(text, keywords):
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
    return "\n".join(lines[start:]) if start is not None else ""


def split_by_subheading(block):
    """Yield (heading_text, body) for every sub-heading in a block."""
    lines = block.splitlines()
    current = None
    buffer = []
    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            if current is not None:
                yield current, "\n".join(buffer)
            current = match.group(2)
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    if current is not None:
        yield current, "\n".join(buffer)


def normalise(fragment):
    text = EMPHASIS_RE.sub("", fragment)
    text = re.sub(r"\s+", " ", text).strip()
    # A report often shortens a long quotation with a trailing ellipsis; strip it
    # so the shortened form still matches the full one.
    text = re.sub(r"\s*(?:\.\.\.|…)\s*$", "", text)
    # Surrounding quotation marks are presentation, not content: a declaration
    # may wrap the phrase in quotes while the extracted evidence does not. Leaving
    # them in made the common-prefix test fail on the first character.
    text = text.strip(" \u3002\uff0c,.;:!\"'\u201c\u201d\u2018\u2019\u300c\u300d")
    return text


def common_prefix_length(left, right):
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def same_location(left, right, prefix_floor=30):
    """Whether two quotations point at the same stretch of the essay.

    A declaration quotes the phrase at whatever length reads well, while the
    merged evidence key is the longest quotation of that place. Plain substring
    testing misses that pair, so a shared opening run also counts as a match.
    """
    if left == right or left in right or right in left:
        return True
    return common_prefix_length(left, right) >= prefix_floor


def merge_by_location(evidence, prefix_floor=30):
    """Fold quotations of the same place into one entry.

    The same defect gets quoted at different lengths across sections, so string
    equality under-reports. Two quotations are treated as the same place when one
    contains the other, or when they share a long opening run.
    """
    merged = {}
    for fragment in sorted(evidence, key=len, reverse=True):
        target = None
        for existing in merged:
            if same_location(fragment, existing, prefix_floor):
                target = existing
                break
        if target is None:
            merged[fragment] = set(evidence[fragment])
        else:
            merged[target] |= evidence[fragment]
    return merged


def criterion_of(heading):
    for key, pattern in CRITERIA:
        if re.search(pattern, heading, re.IGNORECASE):
            return key
    return None


def extract_evidence(text, min_length):
    """Map normalised fragment -> set of criteria it is used as evidence under.

    Only the per-criterion diagnosis section counts. A phrase repeated inside a
    single criterion's discussion is not a violation, and neither is prose
    outside the diagnosis.
    """
    block = find_section(text, DIAGNOSIS_HEADINGS)
    if not block:
        return {}, False

    evidence = {}
    for heading, body in split_by_subheading(block):
        key = criterion_of(heading)
        if key is None:
            continue
        # Only deductions count. A criterion may quote the student's sentence as
        # praise ("simple sentences are clean"), and charging that to the
        # criterion would be a false positive.
        polarity = None
        for line in body.splitlines():
            if "✅" in line and "❌" not in line:
                polarity = "positive"
            elif "❌" in line and "✅" not in line:
                polarity = "negative"
            if polarity == "positive":
                continue
            for pattern in QUOTE_PATTERNS:
                for match in pattern.finditer(line):
                    fragment = normalise(match.group(1))
                    if len(fragment) < min_length:
                        continue
                    evidence.setdefault(fragment, set()).add(key)
    return merge_by_location(evidence), True


def extract_declarations(text):
    """Read the ownership section: quoted fragment -> declared owner."""
    block = find_section(text, OWNERSHIP_HEADINGS)
    if not block:
        return {}, False

    declared = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        fragment = normalise(cells[0].replace("*", ""))
        owner = normalise(cells[1] if len(cells) > 1 else "")
        if not fragment or fragment in ("原文片段", "片段", "fragment", "位置"):
            continue
        for key, pattern in CRITERIA:
            if re.search(pattern, owner, re.IGNORECASE):
                declared[fragment] = key
                break
    return declared, True


def count_candidates(text, min_length):
    """Quotes of any polarity, used to detect evidence this tool cannot audit.

    Reports whose deduction is lexical rather than sentential ("students never
    appears") argue in tables and short quotations. Those are invisible to a
    length-floored fragment scan, and a zero-fragment result must not be read as
    "nothing to declare".
    """
    block = find_section(text, DIAGNOSIS_HEADINGS)
    if not block:
        return 0, 0
    total = 0
    negative_lines = 0
    polarity = None
    for line in block.splitlines():
        if "\u2705" in line and "\u274c" not in line:
            polarity = "positive"
        elif "\u274c" in line and "\u2705" not in line:
            polarity = "negative"
        if "\u274c" in line:
            negative_lines += 1
        for pattern in QUOTE_PATTERNS:
            for match in pattern.finditer(line):
                if len(normalise(match.group(1))) >= min_length:
                    total += 1
    return total, negative_lines


def audit(text, min_length=20):
    evidence, has_diagnosis = extract_evidence(text, min_length)
    declared, has_ownership = extract_declarations(text)
    candidates, negative_lines = count_candidates(text, min_length)

    contested = {fragment: keys for fragment, keys in evidence.items() if len(keys) > 1}

    undeclared = []
    mismatched = []
    for fragment, keys in sorted(contested.items()):
        owner = None
        for candidate, declared_owner in declared.items():
            if same_location(candidate, fragment):
                owner = declared_owner
                break
        if owner is None:
            undeclared.append({"fragment": fragment, "criteria": sorted(keys)})
        elif owner not in keys:
            mismatched.append({"fragment": fragment, "criteria": sorted(keys), "declared": owner})

    used = set()
    for fragment in contested:
        for candidate in declared:
            if same_location(candidate, fragment):
                used.add(candidate)
    stale = sorted(set(declared) - used)

    # Coverage is reported, never silently assumed: a clean result from a scan
    # that could not see the evidence would be false assurance.
    if not has_diagnosis:
        coverage = "none"
    elif evidence:
        coverage = "full"
    else:
        coverage = "partial"
    coverage_note = ""
    if coverage == "partial":
        if candidates == 0 and negative_lines == 0:
            coverage_note = ("逐项诊断里没有找到成句引用，也没有扣分条目——本条报告未提供可审计的证据，"
                             "审计结果不构成通过。")
        else:
            coverage_note = ("本条报告的扣分证据以**表格或短引文**为主（成句引用 %d 条、其中扣分引用 0 条，"
                             "扣分行 %d 行）。审计器只覆盖成句引用——**这些证据是否重复计分，本次未能检查，"
                             "需人工确认。**" % (candidates, negative_lines))

    return {
        "has_diagnosis_section": has_diagnosis,
        "has_ownership_section": has_ownership,
        "coverage": coverage,
        "coverage_note": coverage_note,
        "candidate_quotes": candidates,
        "negative_lines": negative_lines,
        "evidence_fragments": len(evidence),
        "contested": [{"fragment": fragment, "criteria": sorted(keys)}
                      for fragment, keys in sorted(contested.items())],
        "undeclared": undeclared,
        "mismatched": mismatched,
        "stale": stale,
        "pass": has_diagnosis and not undeclared and not mismatched,
    }


def render(path, result, min_length):
    out = []
    add = out.append
    add("# 缺陷归属审计：%s\n" % os.path.basename(path))
    add("> 规则：**一处缺陷只归一个评分项**。同一处被两个以上评分项当作扣分证据时，"
        "报告必须显式声明它的归属项。\n")

    if not result["has_diagnosis_section"]:
        add("⚠️ 报告里没有「逐项诊断」小节，无法审计。")
        add("")
        add("（这不是通过——是**没审**。批改报告必须包含按评分项分的诊断段落。）")
        return "\n".join(out)

    add("- 逐项诊断中提取到 **%d** 条独立引文" % result["evidence_fragments"])
    add("- 其中被 **≥2 个评分项**用作证据的：**%d** 条" % len(result["contested"]))
    add("- 归属声明：%s" % ("有" if result["has_ownership_section"] else "**缺失**"))
    add("- 审计覆盖：%s" % {"full": "**完整**（有成句引用可查）",
                            "partial": "**不完整**", "none": "无"}[result["coverage"]])
    add("")
    if result.get("coverage_note"):
        add("> ⚠️ " + result["coverage_note"])
        add("")

    if not result["contested"]:
        if result["coverage"] == "full":
            add("## ✅ 通过\n")
            add("没有任何引文被两个以上评分项重复用作扣分依据。")
        else:
            # Never let a clean result from a blind scan read as a clean bill of health.
            add("## ⚠️ 未发现违规，但审计不完整\n")
            add("在**能看到的部分**里，没有引文被两个以上评分项重复用作扣分依据。")
            add("")
            add("但这**不等于通过**——本条报告的扣分证据不在审计器的覆盖范围内（见上方说明），"
                "重复计分与否需要人工核对。")
        return "\n".join(out)

    add("## 跨项引用的引文\n")
    add("| 引文片段 | 出现在哪些评分项 | 已声明归属 |")
    add("|---|---|---|")
    for item in result["contested"]:
        labels = "、".join(CRITERION_LABEL[key] for key in item["criteria"])
        declared = ""
        for entry in result["mismatched"]:
            if entry["fragment"] == item["fragment"]:
                declared = "❌ 声明为 %s，不在此列" % CRITERION_LABEL[entry["declared"]]
        for entry in result["undeclared"]:
            if entry["fragment"] == item["fragment"]:
                declared = "❌ **未声明**"
        add("| `%s` | %s | %s |" % (item["fragment"][:60], labels, declared or "✅"))
    add("")

    if result["undeclared"]:
        add("## ❌ 未通过：%d 处引文缺少归属声明\n" % len(result["undeclared"]))
        add("这些引文被多个评分项同时用作扣分证据。**如果它们其实是同一处缺陷，"
            "就会造成系统性低估**；如果确实是不同缺陷，也需要写明，否则无法复核。\n")
        for item in result["undeclared"]:
            add("- `%s`（出现在 %s）" % (
                item["fragment"][:70],
                "、".join(CRITERION_LABEL[key] for key in item["criteria"])))
        add("")
        add("**修法**：在报告里加一节 `## 缺陷归属审计`，用表格为每条引文声明唯一归属项：")
        add("")
        add("```markdown")
        add("## 缺陷归属审计")
        add("")
        add("| 原文片段 | 归属项 | 其他评分项的处理 |")
        add("|---|---|---|")
        add("| it is good for the society, it can make ... | GRA（逗号拼接） | CC 不再因此降档；LR 的低语域单独计入 |")
        add("```")
        add("")
    if result["mismatched"]:
        add("## ❌ 归属声明与出现位置不符：%d 处\n" % len(result["mismatched"]))
        for item in result["mismatched"]:
            add("- `%s` 声明归属为 %s，但它只出现在 %s" % (
                item["fragment"][:60],
                CRITERION_LABEL[item["declared"]],
                "、".join(CRITERION_LABEL[key] for key in item["criteria"])))
        add("")
    if result["stale"]:
        add("## ⚠️ 归属声明里有多余条目：%d 处\n" % len(result["stale"]))
        add("这些声明对应的引文已不在逐项诊断中重复出现，可删除以免混淆：\n")
        for fragment in result["stale"]:
            add("- `%s`" % fragment[:60])
        add("")

    add("---\n")
    add("*本审计只检查「同一引文是否被多项扣分」，不判断归属项是否正确——"
        "那要看作文本身。*")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit a correction report for one defect charged to two criteria.")
    parser.add_argument("target", help="a report file, or a directory of reports")
    parser.add_argument("--min-length", type=int, default=20,
                        help="shortest quoted fragment to consider (default 20)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", help="write the Markdown audit to this path")
    args = parser.parse_args(argv)

    if os.path.isdir(args.target):
        paths = sorted(glob.glob(os.path.join(args.target, "**", "*.md"), recursive=True))
        paths = [p for p in paths if not os.path.basename(p).startswith(("_", "."))]
    elif os.path.isfile(args.target):
        paths = [args.target]
    else:
        sys.stderr.write("no such file or directory: %s\n" % args.target)
        return 2

    results = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        if not find_section(text, DIAGNOSIS_HEADINGS):
            continue  # not a correction report
        results.append((path, audit(text, args.min_length)))

    if not results:
        sys.stderr.write("no correction report found under %s\n" % args.target)
        return 2

    if args.json:
        rendered = json.dumps(
            [{"file": os.path.basename(path), "result": result} for path, result in results],
            ensure_ascii=False, indent=2)
    else:
        rendered = "\n\n---\n\n".join(render(path, result, args.min_length)
                                      for path, result in results)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        sys.stderr.write("wrote %s (%d report(s))\n" % (args.out, len(results)))
    else:
        sys.stdout.write(rendered + "\n")

    incomplete = [path for path, result in results if result["coverage"] != "full"]
    if incomplete and not args.json:
        sys.stderr.write("warning: %d report(s) had evidence outside the auditor's reach\n"
                         % len(incomplete))
    return 0 if all(result["pass"] for _, result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
