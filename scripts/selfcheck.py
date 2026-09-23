#!/usr/bin/env python3
"""Self-check a shared copy of the ielts-writing-coach skill bundle.

Run this after unzipping or cloning the skill somewhere new:

    python3 scripts/selfcheck.py

Verifies the frontmatter the skill loader requires, that every resource the
skill references actually shipped, and that the analyzer runs on the bundled
sample essay. Exits non-zero on the first failure.

Standard library only. Python 3.8+.
"""

import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "README.en.md",
    "USAGE.md",
    "USAGE-EXAMPLE.md",
    "LICENSE",
    "NOTICE.md",
    ".gitignore",
    ".github/workflows/selfcheck.yml",
    "examples/README.md",
    "examples/report-task2.md",
    "examples/reviewed-task2.docx",
    "RELEASING.md",
    "references/scoring-protocol.md",
    "references/calibration-evidence.md",
    "references/failure-modes.md",
    "references/band-descriptors.md",
    "references/task1-guide.md",
    "references/task2-guide.md",
    "references/error-taxonomy.md",
    "references/language-bank.md",
    "templates/report-template.md",
    "templates/calibration-log.md",
    "scripts/analyze_essay.py",
    "scripts/track_progress.py",
    "scripts/report_to_docx.py",
    "scripts/ielts_codes.py",
    "scripts/check_stdlib_only.py",
    "scripts/calibrate.py",
    "evals/evals.json",
    "evals/samples/sample-task2-essay.txt",
    "evals/samples/sample-task2-prompt.txt",
    "evals/samples/sample-task2-hollow-essay.txt",
    "evals/samples/sample-task2-hollow-prompt.txt",
    "evals/samples/sample-task2-offtopic-essay.txt",
    "evals/samples/sample-task2-offtopic-prompt.txt",
    "evals/samples/sample-task1-chart-essay.txt",
    "evals/samples/sample-task1-chart-prompt.txt",
]

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Minimal but format-faithful correction report, used to test the progress
# tracker without shipping large fixtures. The score card heading and the
# per-code statistics line are both load-bearing for that script.
REPORT_FIXTURE = """# IELTS Writing 批改报告

> **预估分，非官方成绩** ｜ Task 2（Discussion + Opinion）｜ {date}
> **题目**：Synthetic prompt used by selfcheck.

## 分数卡

| 项目 | 预估分 | 一句话依据 |
|---|---|---|
| Task Response | {tr} | synthetic |
| Coherence & Cohesion | {cc} | synthetic |
| Lexical Resource | {lr} | synthetic |
| Grammatical Range & Accuracy | {gra} | synthetic |
| **总分** | **{overall}** | synthetic |

**客观数据**：300 词

## 错误清单

| # | 位置 | 原文 | 代码 | 修改 | 原因 |
|---|---|---|---|---|---|
| 1 | 1 | synthetic | GRA-ART | synthetic | synthetic |

**按代码统计**：GRA-ART {art} 处 ｜ TR-UNDEV {undev} 处
"""

# A tiny essay/report pair for the .docx builder. It deliberately contains two
# report rows quoting the same span (which must merge into one comment) and one
# row that does not quote the essay at all (which must stay unanchored).
DOCX_ESSAY_FIXTURE = """Nowadays, more and more people pay attention on the university education.

On the one hand, free university education has many advantages, it can help the poor students.
"""

TASK1_PROMPT = """The chart below shows the percentage of households in owned and rented accommodation in England and Wales between 1971 and 2001. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.
"""

TASK1_FLAWED = """The chart shows the percentage of households in owned and rented accommodation in England and Wales between 1971 and 2001.

In 1971, the percentage of owned households is 50%. The percentage of rented households is 50%. In 1981, the percentage of owned households is 58% and the percentage of rented households is 42%. In 1991, the percentage of owned households is 67%.

There are many differences between the two types of accommodation. The number of owned households increased, and the number of rented households decreased.
"""

TASK1_SOUND = """The chart compares the proportion of households in owned and rented accommodation in England and Wales between 1971 and 2001.

Overall, home ownership rose steadily throughout the period while the rented sector declined by a similar margin, so that by 2001 the two had reversed their relative positions.

In 1971, the two categories were evenly balanced at 50% each. Ownership then increased in every subsequent decade, reaching 58% in 1981 and 67% in 1991, before levelling off at 69% in 2001. Rented accommodation fell correspondingly, from 50% to 31% over the same thirty years.
"""

GT_PROMPT = """You recently bought a laptop which stopped working after three days. Write a letter to the shop. In your letter: say when and where you bought it; describe the problem; explain what you want them to do. Begin your letter "Dear Sir or Madam,".
"""

GT_LETTER = """Dear Sir or Madam,

I am writing to complain about a laptop which I purchased from your branch on 3 May.

The screen stopped working after three days. I returned it and was told to contact the manufacturer, which I did, but nobody has replied.

I would like a full refund or a replacement. Please let me know what you can do.

Cheers,
Zhang Wei
"""

# The letter above opens with "Dear Sir or Madam," -- an unnamed recipient, and
# for a long time it was the only GT fixture. That is exactly why two defects
# survived in the letter check: the greeting pattern matched honorifics only, so
# "Dear Tom," (the most common opening in the task) was reported as a *missing*
# greeting; and the closing rule accepted only "Yours sincerely" after a named
# recipient, rejecting "Best wishes". A fixture that covers one form certifies
# one form, and the same is true of the contradiction test below, which only
# exercised the direction that happened to be right.
GT_NAMED_PROMPT = """Your friend is coming to visit you next month. Write a letter to your friend. In your letter: explain when he should come; say what you will do together; tell him what he should bring. Begin your letter "Dear ...".
"""

GT_NAMED_LETTER = """Dear Tom,

I am very glad to hear that you are coming to visit me next month.

The best time to come is the second week of May, when the weather is warm and I have a few days off. We can walk along the river and eat at the night market. Please bring a warm jacket, because it is still cold in the evening.

Write back when you know your dates.

Best wishes,
Li Ming
"""

DUPLICATE_ESSAY = """The government should pay attention on the education.

Later in the essay the government should pay attention on the education again.
"""

DUPLICATE_REPORT = """# IELTS Writing 批改报告

> **预估分，非官方成绩** ｜ Task 2 ｜ 2026-06-06

## 分数卡

| 项目 | 预估分 | 一句话依据 |
|---|---|---|
| Task Response | 6.0 | a |
| Coherence & Cohesion | 6.0 | b |
| Lexical Resource | 6.0 | c |
| Grammatical Range & Accuracy | 6.0 | d |
| **总分** | **6.0** | e |

## 错误清单

| # | 位置 | 原文 | 代码 | 修改 | 原因 |
|---|---|---|---|---|---|
| 1 | ¶1 | pay attention on the education | GRA-PREP | pay attention to | 固定搭配 |
| 2 | ¶2 | pay attention on the education | GRA-PREP | pay attention to | 同一错误第二次出现 |
"""

EN_REPORT_FIXTURE = """# IELTS Writing Review

> Estimated band, not an official score ｜ Task 2 ｜ 2026-06-06

## Score Card

| Criterion | Band | Evidence |
|---|---|---|
| Task Response | 6.0 | position only in the final body paragraph |
| Coherence & Cohesion | 6.0 | linking is mechanical |
| Lexical Resource | 6.0 | no substitution |
| Grammatical Range & Accuracy | 5.5 | an error in most sentences |
| **Overall** | **6.0** | mean of the four |

## Error List

| # | Where | Original | Code | Fix | Reason |
|---|---|---|---|---|---|
| 1 | P1 | pay attention on the education | GRA-PREP | pay attention to | fixed phrase |

**Per-code totals**: GRA-PREP 1

## Sentence Upgrades

### 1. P1

**Original**
> pay attention on the education

**Rewrite**
> pay attention to education
"""

EMOJI_ESSAY = """The government should pay attention on education \U0001F600 and \u8fd9\u6837\u505a\uff0c\u662f\u4e0d\u5bf9\u7684\u3002

\u4e2d\u6587\u6d4b\u8bd5\U0001F4DA with \u201csmart quotes\u201d and a dash \u2014 here.
"""

EMOJI_REPORT_FIXTURE = """# IELTS Writing 批改报告

> **预估分，非官方成绩** ｜ Task 2 ｜ 2026-06-06

## 分数卡

| 项目 | 预估分 | 一句话依据 |
|---|---|---|
| Task Response | 6.0 | a |
| Coherence & Cohesion | 6.0 | b |
| Lexical Resource | 6.0 | c |
| Grammatical Range & Accuracy | 6.0 | d |
| **总分** | **6.0** | e |

## 错误清单

| # | 位置 | 原文 | 代码 | 修改 | 原因 |
|---|---|---|---|---|---|
| 1 | ¶1 | pay attention on education | GRA-PREP | pay attention to | 固定搭配 |
"""

AUDIT_BODY = """# IELTS Writing 批改报告

> **预估分，非官方成绩** ｜ Task 2 ｜ 2026-07-07

## 逐项诊断

### Task Response — 6.0

- \u274c **未达标之处**：\u00b62 "the government should do something about this problem" 是空泛断言，没有机制。

### Coherence & Cohesion — 6.0

- \u274c **未达标之处**：\u00b62 "the government should do something about this problem" 与前句缺乏衔接。

### Lexical Resource — 6.0

- \u274c **未达标之处**：\u00b62 "the government should do something about this problem. Nothing has changed since." 语域偏低。

### Grammatical Range & Accuracy — 6.0

- \u2705 **达标之处**：简单句基本干净（"the government should do something about this problem"）。
"""

AUDIT_OWNERSHIP = """
## 缺陷归属审计

| 原文片段 | 归属项 | 其他评分项的处理 |
|---|---|---|
| "the government should do something about this problem" | **LR**（语域） | TR 的空泛与 CC 的衔接问题各自独立，单独计入 |
"""

DOCX_REPORT_FIXTURE = """# IELTS Writing 批改报告

> **预估分，非官方成绩** ｜ Task 2 ｜ 2026-05-05
> **题目**：Synthetic prompt for the docx builder.

## 分数卡

| 项目 | 预估分 | 一句话依据 |
|---|---|---|
| Task Response | 6.0 | 立场清楚（含中文说明） |
| Coherence & Cohesion | 6.0 | 分段合理 |
| Lexical Resource | 6.0 | 搭配有误 |
| Grammatical Range & Accuracy | 5.5 | 逗号拼接 |
| **总分** | **6.0** | 四项均值 5.875 |

## 错误清单

| # | 位置 | 原文 | 代码 | 修改 | 原因 |
|---|---|---|---|---|---|
| 1 | ¶1 | pay attention on the university education | GRA-PREP | pay attention to | 固定搭配 |
| 2 | ¶1 | pay attention on the university education | LR-COLL | pay close attention to | 同一处的第二个问题，应合并进同一条批注 |
| 3 | ¶2 | it can help the poor students | GRA-RUN | ; it can help the poor students | 逗号拼接 |
| 5 | ¶2 | it can help the poor students | LR-WW（精确度） | it can also help students from low-income families | 带注释的代码应能归一化 |
| 4 | ¶2 | 这段文字并不在作文里 | TR-OFF | — | 无法逐字定位，应列为未锚定 |

## 句子升级（before → after）

### 1. ¶2

**原文**
> it can help the poor students

**改写**
> it can also help students from low-income families

**改动说明**：把 the poor students 换成更准确的表达。

## 附：目标分段示范

> 以下演示 Band 7.5 的写法，学习结构，不要背诵。

> A means-tested system combines modest fees with targeted grants, which preserves access without abandoning public finances.

**这段为什么达标**：

| 评分项 | 体现 |
|---|---|
| TR | names a mechanism |
"""

failures = []
checks_run = []


def check(condition, message):
    checks_run.append(bool(condition))
    if condition:
        print("  ok   %s" % message)
    else:
        print("  FAIL %s" % message)
        failures.append(message)


def main():
    print("bundle: %s" % ROOT)
    print("\n[1] required files")
    for relative in REQUIRED_FILES:
        check(os.path.isfile(os.path.join(ROOT, relative)), relative)

    print("\n[2] SKILL.md frontmatter")
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as handle:
        raw = handle.read()
    check(raw.startswith("---\n"), "file starts with YAML frontmatter")
    end = raw.find("\n---", 4)
    check(end > 0, "frontmatter block is closed")
    front = raw[4:end] if end > 0 else ""
    name_match = re.search(r"^name:\s*(\S+)\s*$", front, flags=re.MULTILINE)
    desc_match = re.search(r"^description:\s*(.+)$", front, flags=re.MULTILINE)
    check(name_match is not None, "frontmatter declares name")
    check(desc_match is not None, "frontmatter declares description")
    if name_match:
        name = name_match.group(1)
        check(NAME_RE.match(name) is not None, "name %r is valid kebab-case" % name)
        # The loader discovers a skill by the frontmatter `name`, so a clone into a
        # differently-named directory still works. A mismatch is worth reporting,
        # but failing on it would turn a legitimate install into a false alarm --
        # and false alarms train people to ignore real ones.
        if name != os.path.basename(ROOT):
            print("  --   directory %r differs from the skill name %r; discovery still works, "
                  "but the docs assume the directory is named %r"
                  % (os.path.basename(ROOT), name, name))
    body = raw[end + 4:] if end > 0 else ""
    check(len(body.strip()) > 500, "instruction body is non-trivial")

    print("\n[3] referenced resources exist")
    # One check for the whole set, not one per reference. Emitting a check per
    # path made the documented total depend on how many resources SKILL.md
    # happens to list: adding a single line to the instruction file silently
    # changed the number the READMEs declare, which is a footgun aimed at
    # exactly the invariant [17] is trying to hold. The message still names
    # every missing path, so nothing is lost but the churn.
    referenced = set(re.findall(r"`((?:references|templates|scripts|evals)/[A-Za-z0-9_./-]+)`", raw))
    dangling = sorted(relative for relative in referenced
                      if not os.path.isfile(os.path.join(ROOT, relative)))
    check(not dangling,
          "every resource SKILL.md references shipped (%d checked; %s)"
          % (len(referenced), "; ".join(dangling) if dangling else "all present"))

    print("\n[4] analyzer runs on the bundled sample")
    sample = os.path.join(ROOT, "evals", "samples", "sample-task2-essay.txt")
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "analyze_essay.py"), sample, "--task", "2", "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    check(result.returncode == 0, "analyzer exits 0")
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout.decode("utf-8"))
        check(data["word_count"] > 200, "sample word count reported (%d)" % data["word_count"])
        check(data["sentence_count"] > 5, "sample sentence count reported (%d)" % data["sentence_count"])
        check(len(data["error_probes"]) > 0, "error probes fire on the seeded sample")

    print("\n[5] analyzer separates the error-prone sample from the hollow sample")
    hollow = os.path.join(ROOT, "evals", "samples", "sample-task2-hollow-essay.txt")
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "analyze_essay.py"), hollow, "--task", "2", "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    check(result.returncode == 0, "analyzer exits 0 on the hollow sample")
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout.decode("utf-8"))
        check(len(data["error_probes"]) == 0, "hollow sample yields no error probes (it is error-free)")
        check(len(data["hollow_signals"]) >= 3, "hollow sample trips the support warnings")
        check(data["specificity"]["total"] == 0, "hollow sample has no concrete detail")
        check(data["hedges"] >= 6, "hollow sample's hedging is counted (%d)" % data["hedges"])

    print("\n[6] prompt relevance separates on-topic from off-topic")
    samples = os.path.join(ROOT, "evals", "samples")
    analyzer = os.path.join(HERE, "analyze_essay.py")

    on_topic = subprocess.run(
        [sys.executable, analyzer,
         os.path.join(samples, "sample-task2-essay.txt"), "--task", "2",
         "--prompt", os.path.join(samples, "sample-task2-prompt.txt"), "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    off_topic = subprocess.run(
        [sys.executable, analyzer,
         os.path.join(samples, "sample-task2-offtopic-essay.txt"), "--task", "2",
         "--prompt", os.path.join(samples, "sample-task2-offtopic-prompt.txt"), "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    check(on_topic.returncode == 0 and off_topic.returncode == 0, "relevance check runs on both samples")
    if on_topic.returncode == 0 and off_topic.returncode == 0:
        import json
        on = json.loads(on_topic.stdout.decode("utf-8"))["relevance"]
        off = json.loads(off_topic.stdout.decode("utf-8"))["relevance"]
        check(on["coverage"] >= 0.8, "on-topic sample covers the prompt (%.0f%%)" % (on["coverage"] * 100))
        check(off["coverage"] < 0.4, "off-topic sample misses the prompt (%.0f%%)" % (off["coverage"] * 100))
        check("students" in off["missing_keywords"] or "university" in off["missing_keywords"],
              "off-topic sample is missing the question's core nouns")
        check(off["suspect_prompt"] is None, "a valid prompt is not flagged as suspect")
        check(on["task_types"][0]["type"] == "discussion_opinion",
              "prompt task type is identified (%s)" % on["task_types"][0]["type"])

    misrouted = subprocess.run(
        [sys.executable, analyzer,
         os.path.join(samples, "sample-task2-offtopic-essay.txt"), "--task", "2",
         "--prompt", os.path.join(samples, "sample-task2-essay.txt"), "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if misrouted.returncode == 0:
        import json
        wrong = json.loads(misrouted.stdout.decode("utf-8"))["relevance"]
        check(wrong["suspect_prompt"] is not None, "passing an essay as the prompt is caught")

    print("\n[7] progress tracker parses reports, aggregates codes, and refuses fake trends")
    import json
    import shutil
    import tempfile

    tracker = os.path.join(HERE, "track_progress.py")
    workdir = tempfile.mkdtemp(prefix="ielts-track-")
    try:
        def write_report(directory, name, date, tr, cc, lr, gra, art, undev):
            os.makedirs(directory, exist_ok=True)
            body = REPORT_FIXTURE.format(
                date=date, tr=tr, cc=cc, lr=lr, gra=gra,
                overall=int((tr + cc + lr + gra) / 4 * 2 + 0.5) / 2,
                art=art, undev=undev,
            )
            with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
                handle.write(body)

        def run_tracker(directory):
            return subprocess.run(
                [sys.executable, tracker, directory, "--json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        def write_range_report(directory, name, date, midpoints):
            """The current card layout: a range column beside the midpoint.

            The trap this exists for: a reader that takes "the first number in
            column 2" reads `5.5-6.5` as 5.5 -- the lower bound -- and reports it
            as the essay's score with no error at all. Both readers now locate
            the column by its header, so this asserts the midpoint is what comes
            out, and that a report in the new layout is still recognised.
            """
            os.makedirs(directory, exist_ok=True)
            rows = "\n".join("| %s | %s | %s | synthetic |" % (label, span, mid)
                              for label, span, mid in midpoints)
            body = ("# IELTS Writing 批改报告\n\n"
                    "> **预估分，非官方成绩** ｜ Task 2 ｜ %s\n\n"
                    "## 分数卡\n\n"
                    "| 项目 | 预估区间 | 中点 | 一句话依据 |\n"
                    "|---|---|---|---|\n%s\n\n" % (date, rows))
            with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
                handle.write(body)

        ranged = os.path.join(workdir, "ranged", "ielts-reports")
        write_range_report(ranged, "2026-02-01-task2.md", "2026-02-01", (
            ("Task Response", "5.5–6.5", "6.0"),
            ("Coherence & Cohesion", "6.0–7.0", "6.5"),
            ("Lexical Resource", "5.5–6.5", "6.0"),
            ("Grammatical Range & Accuracy", "5.0–6.0", "5.5"),
            ("**整体位置**", "**5.0–7.0**", "**6.0**"),
        ))
        result = run_tracker(ranged)
        check(result.returncode == 0, "the tracker runs on a report using the range layout")
        if result.returncode == 0:
            data = json.loads(result.stdout.decode("utf-8"))
            check(data["count"] == 1,
                  "a range-layout report is recognised as a report (%d read)" % data["count"])
            if data["count"] == 1:
                latest = data["reports"][0]
                criteria = latest.get("criteria") or {}
                # TR's midpoint is 6.0 and its lower bound is 5.5; reading the
                # latter as the score is the specific misread to prevent.
                check(criteria.get("TR") == 6.0,
                      "the range is not read as its lower bound (TR=%s, want 6.0)"
                      % criteria.get("TR"))
                check(abs(float(latest["overall"]) - 6.0) < 0.01,
                      "the overall uses the stated midpoint (%s)" % latest["overall"])
            # The trend table has to stay numeric for its arithmetic, so its
            # numbers are midpoints. Saying so is not decoration: without it a
            # reader takes them as the scores the report gave. The flag was
            # dropped once between the parser and the summary, and the note
            # vanished with no test noticing -- hence this check.
            rendered = subprocess.run(
                [sys.executable, tracker, ranged],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ).stdout.decode("utf-8")
            check("中点" in rendered and "区间" in rendered,
                  "the trend discloses that its numbers are interval midpoints")

        dated = os.path.join(workdir, "dated", "ielts-reports")
        write_report(dated, "2026-01-01-task2.md", "2026-01-01", 6.0, 6.0, 6.0, 6.0, 3, 2)
        write_report(dated, "2026-02-01-task2.md", "2026-02-01", 6.5, 6.5, 6.0, 6.5, 1, 1)
        with open(os.path.join(dated, "2026-02-01-notes.md"), "w", encoding="utf-8") as handle:
            handle.write("# 备注\n\n这份文档没有分数卡小节，应被跳过。\n")

        result = run_tracker(dated)
        check(result.returncode == 0, "tracker exits 0")
        if result.returncode == 0:
            data = json.loads(result.stdout.decode("utf-8"))
            check(data["count"] == 2, "tracker found the two reports (%d)" % data["count"])
            check(data["trend_reliable"] is True, "distinct dates make the trend reliable")
            check(data["skipped"] == ["2026-02-01-notes.md"],
                  "a file without a score card is skipped (%s)" % data["skipped"])
            trend = data["trends"].get("Task 2")
            check(trend is not None and trend["deltas"]["TR"] == 0.5,
                  "TR delta across dates is computed (%s)" % (trend and trend["deltas"]["TR"]))
            codes = {entry["code"]: entry for entry in data["all_codes"]}
            check(codes.get("GRA-ART", {}).get("total") == 4,
                  "error codes aggregate across reports (GRA-ART=%s)"
                  % codes.get("GRA-ART", {}).get("total"))
            check(codes.get("GRA-ART", {}).get("reports") == 2,
                  "recurring codes count the reports they appear in")
            check(data["gap"]["current"] == 6.5 and data["gap"]["delta"] == 1.5,
                  "band gap arithmetic matches the four-criterion total (%s -> %s, delta %s)"
                  % (data["gap"]["current"], data["gap"]["next"], data["gap"]["delta"]))

        same_day = os.path.join(workdir, "same-day", "ielts-reports")
        write_report(same_day, "2026-03-01-task2-a.md", "2026-03-01", 6.0, 6.0, 6.0, 6.0, 2, 1)
        write_report(same_day, "2026-03-01-task2-b.md", "2026-03-01", 5.0, 5.5, 5.5, 5.0, 1, 3)
        result = run_tracker(same_day)
        if result.returncode == 0:
            data = json.loads(result.stdout.decode("utf-8"))
            check(data["trend_reliable"] is False,
                  "same-day reports are not treated as a progression")
            check(data["trends"].get("Task 2") is None,
                  "no delta is invented when the order is unknown")

        missing = subprocess.run(
            [sys.executable, tracker, os.path.join(workdir, "does-not-exist")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(missing.returncode == 2, "a missing reports directory fails loudly")

        empty_dir = os.path.join(workdir, "empty", "ielts-reports")
        os.makedirs(empty_dir, exist_ok=True)
        empty = run_tracker(empty_dir)
        check(empty.returncode == 0, "an empty reports directory is a normal state, not a crash")
        if empty.returncode == 0:
            data = json.loads(empty.stdout.decode("utf-8"))
            check(data["count"] == 0, "an empty directory reports zero reports")
        empty_md = subprocess.run(
            [sys.executable, tracker, empty_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check("未找到可解析的批改报告".encode("utf-8") in empty_md.stdout,
              "an empty directory explains what a report must contain")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n[8] docx builder: merged anchors, unanchored notes, byte-stable output")
    import hashlib
    import xml.etree.ElementTree as ElementTree
    import zipfile

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    builder = os.path.join(HERE, "report_to_docx.py")
    docx_dir = tempfile.mkdtemp(prefix="ielts-docx-")
    try:
        essay_path = os.path.join(docx_dir, "essay.txt")
        report_path = os.path.join(docx_dir, "report.md")
        with open(essay_path, "w", encoding="utf-8") as handle:
            handle.write(DOCX_ESSAY_FIXTURE)
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(DOCX_REPORT_FIXTURE)

        def build(name):
            return subprocess.run(
                [sys.executable, builder, "--essay", essay_path, "--report", report_path,
                 "--out", os.path.join(docx_dir, name)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        first = build("first.docx")
        check(first.returncode == 0, "docx builder exits 0")
        check(b"validation: ok" in first.stdout, "the builder validates its own output")

        build("second.docx")
        digests = [
            hashlib.sha256(open(os.path.join(docx_dir, name), "rb").read()).hexdigest()
            for name in ("first.docx", "second.docx")
        ]
        check(digests[0] == digests[1], "rebuilding the same input yields identical bytes")

        standalone = subprocess.run(
            [sys.executable, builder, "--validate-only", os.path.join(docx_dir, "first.docx")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(standalone.returncode == 0, "--validate-only accepts the output")

        with zipfile.ZipFile(os.path.join(docx_dir, "first.docx")) as archive:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            comments = ElementTree.fromstring(archive.read("word/comments.xml"))

        starts = document.findall(".//{%s}commentRangeStart" % W)
        definitions = comments.findall("{%s}comment" % W)
        check(len(starts) == 2,
              "two distinct anchors produced two comment ranges (%d)" % len(starts))
        check(len(starts) == len(definitions),
              "every range has exactly one definition (%d vs %d)" % (len(starts), len(definitions)))

        def comment_text(node):
            return " ".join("".join(t.text or "" for t in paragraph.iter("{%s}t" % W))
                            for paragraph in node.findall("{%s}p" % W))

        bodies = [comment_text(node) for node in definitions]

        check(any("Preposition" in body and "介词" in body for body in bodies),
              "a comment leads with its short margin tag and Chinese label")
        check(any("→ pay attention to" in body for body in bodies),
              "the correction is marked with an arrow on its own line")
        check(any("Collocation" in body and "Preposition" in body for body in bodies),
              "two rows on the same span merge into one tagged comment")
        check(any("Word choice" in body for body in bodies),
              "an annotated code (LR-WW（精确度）) is normalised to its tag")

        document_text = "".join(node.text or "" for node in document.iter("{%s}t" % W))
        check("批注标签统计" in document_text, "the margin-tag frequency table is on the score page")
        check("批注数" in document_text,
              "the tag table names its column so it is not confused with the report's error counts")
        check("只统计" in document_text,
              "the tag table explains why it may differ from the report's per-code totals")

        document_text = "".join(node.text or "" for node in document.iter("{%s}t" % W))

        # The unanchored row still belongs on the score page's problem list, but
        # its text must never be wrapped by a comment range in the essay body.
        anchored_spans = []
        for parent in document.iter("{%s}p" % W):
            stack = []
            for child in list(parent):
                if child.tag == "{%s}commentRangeStart" % W:
                    stack.append([child.get("{%s}id" % W), ""])
                elif child.tag == "{%s}commentRangeEnd" % W:
                    if stack:
                        _, covered = stack.pop()
                        anchored_spans.append(covered)
                else:
                    for text_node in child.iter("{%s}t" % W):
                        if stack:
                            stack[-1][1] += text_node.text or ""
        anchored_text = " | ".join(anchored_spans)
        check("这段文字并不在作文里" not in anchored_text,
              "a fragment absent from the essay is never wrapped by a comment range")
        check("pay attention on the university education" in anchored_text,
              "an anchored fragment really is the text inside its range")
        check(not any("这段文字并不在作文里" in body for body in bodies),
              "the unanchored fragment does not become a comment either")
        check("立场清楚（含中文说明）" in document_text,
              "non-ASCII report text survives the XML round trip")
        check("it can also help students from low-income families" in document_text,
              "the italic rewrite is inserted into the body")
        check("A means-tested system combines modest fees" in document_text,
              "the model paragraph from the report reaches the document")
        # The instruction line is deliberately rendered as the caption, but it
        # must never be concatenated into the model prose itself.
        text_nodes = [node.text or "" for node in document.iter("{%s}t" % W)]
        check(not any("学习结构" in node and "A means-tested system" in node
                      for node in text_nodes),
              "the model paragraph's instruction line is not merged into the model prose")

        broken = os.path.join(docx_dir, "broken.docx")
        with zipfile.ZipFile(broken, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("_rels/.rels", "<Relationships/>")
            archive.writestr("word/document.xml", "<w:document/>")
        rejected = subprocess.run(
            [sys.executable, builder, "--validate-only", broken],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(rejected.returncode == 1, "the validator rejects a truncated package")
    finally:
        shutil.rmtree(docx_dir, ignore_errors=True)

    print("\n[8b] the shipped example presents a position, not a single score")
    # Measured error is about half a band, so a report that leads with one total
    # claims a precision the tool does not have. The example is what people read
    # first, so it is asserted directly rather than trusted to stay in step with
    # the template.
    example_docx = os.path.join(ROOT, "examples", "reviewed-task2.docx")
    if os.path.isfile(example_docx):
        with zipfile.ZipFile(example_docx) as archive:
            page = re.sub(r"<[^>]+>", "", archive.read("word/document.xml").decode("utf-8"))
        check("位置（区间）" in page,
              "the example's score page labels the column as a range")
        check(re.search(r"\d(?:\.\d)?\s*[–~-]\s*\d(?:\.\d)?", page) is not None,
              "the example states an actual range")
        check(not re.search(r"预估分\s*\d", page),
              "the example never states a bare estimated score")
        # `总分` on its own is not the problem -- the example's own note says
        # "不给单点总分". What the old layout rendered was `总分6`: a total with a
        # number attached, which is the claim being removed.
        check("整体位置" in page and not re.search(r"总分\s*\d", page),
              "the example's overall row is a position, not a numbered total")

    print("\n[9] analyzer Task 1 mode: overview, mechanical listing, tense")
    t1_dir = tempfile.mkdtemp(prefix="ielts-t1-")
    try:
        prompt_path = os.path.join(t1_dir, "prompt.txt")
        flawed_path = os.path.join(t1_dir, "flawed.txt")
        sound_path = os.path.join(t1_dir, "sound.txt")
        for path, body in ((prompt_path, TASK1_PROMPT), (flawed_path, TASK1_FLAWED),
                           (sound_path, TASK1_SOUND)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)

        def run_task1(essay):
            return subprocess.run(
                [sys.executable, analyzer, essay, "--task", "1",
                 "--prompt", prompt_path, "--json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        flawed = run_task1(flawed_path)
        sound = run_task1(sound_path)
        check(flawed.returncode == 0 and sound.returncode == 0, "Task 1 mode runs on both essays")
        if flawed.returncode == 0 and sound.returncode == 0:
            bad = json.loads(flawed.stdout.decode("utf-8"))
            good = json.loads(sound.stdout.decode("utf-8"))

            check(bad["task1"] is not None, "Task 1 mode emits its own section instead of the argument axis")
            check(bad["task1"]["has_overview"] is False, "a missing overview is detected")
            check(bad["task1"]["tense_mixing"] is True,
                  "present tense against a past period is caught")
            check(bad["task1"]["mechanical_ratio"] >= 0.6,
                  "pure number-listing is flagged (%.0f%%)" % (bad["task1"]["mechanical_ratio"] * 100))
            check(any("overview" in finding for finding in bad["task1"]["findings"]),
                  "the missing overview becomes a finding")

            check(good["task1"]["has_overview"] is True, "a present overview is recognised")
            check(good["task1"]["tense_mixing"] is False,
                  "consistent past tense is not reported as mixing")

            relevance = bad["relevance"]
            check(relevance["task_types"][0]["type"] == "task1_academic",
                  "a Task 1 prompt is classified (%s)" % relevance["task_types"][0]["type"])
            check(relevance["coverage"] >= 0.8,
                  "Task 1 instruction words do not inflate the missing-keyword list (%.0f%%)"
                  % (relevance["coverage"] * 100))
            check(relevance["suspect_prompt"] is None,
                  "a valid Task 1 prompt is not flagged as suspect")
            check(any(component["present"] is False for component in relevance["components"]),
                  "the required overview is reported missing at the task level")

        gt_prompt = os.path.join(t1_dir, "gt-prompt.txt")
        gt_letter = os.path.join(t1_dir, "gt.txt")
        for path, body in ((gt_prompt, GT_PROMPT), (gt_letter, GT_LETTER)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        gt = subprocess.run(
            [sys.executable, analyzer, gt_letter, "--task", "1gt", "--prompt", gt_prompt, "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(gt.returncode == 0, "General Training letter mode runs")
        if gt.returncode == 0:
            data = json.loads(gt.stdout.decode("utf-8"))
            check(data["task1"]["kind"] == "gt_letter", "a GT letter is not treated as a chart")
            joined = " ".join(data["task1"]["findings"])
            check("overview" not in joined,
                  "a letter is never told it is missing an overview")
            check(any("敬语" in finding for finding in data["task1"]["findings"]),
                  "a missing letter farewell is reported")
            check(data["relevance"]["task_types"][0]["type"] == "task1_gt",
                  "a letter prompt is classified as task1_gt")

            # The flag and the prompt must not be allowed to disagree silently.
            clash = subprocess.run(
                [sys.executable, analyzer, sound_path, "--task", "1", "--prompt", gt_prompt, "--json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            check(clash.returncode == 0, "a contradictory task flag still runs")
            if clash.returncode == 0:
                data = json.loads(clash.stdout.decode("utf-8"))
                joined = " ".join(data["contradictions"])
                check(bool(data["contradictions"]),
                      "--task 1 with a letter prompt is reported as a contradiction")
                check("1gt" in joined, "the contradiction names the flag to use instead")

            # The direction above produced the right remedy even with the old
            # flag-keyed table, so on its own it certified nothing. This is the
            # direction that was wrong: a Task 2 prompt behind `--task 1` used to
            # be told to retry as `--task 1gt`, i.e. sent to a third wrong branch.
            backwards = subprocess.run(
                [sys.executable, analyzer, sound_path, "--task", "1", "--prompt",
                 os.path.join(ROOT, "evals", "samples", "sample-task2-prompt.txt"), "--json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            check(backwards.returncode == 0, "a Task 2 prompt behind --task 1 still runs")
            if backwards.returncode == 0:
                joined = " ".join(json.loads(backwards.stdout.decode("utf-8"))["contradictions"])
                check("--task 2" in joined,
                      "the remedy names the flag the prompt actually needs")
                check("--task 1gt" not in joined,
                      "a Task 2 prompt is not sent to the letter branch as a remedy")

            # A letter to a named friend: the common GT form, and the form the
            # honorific-only pattern used to reject outright.
            named_prompt = os.path.join(t1_dir, "named-prompt.txt")
            named_letter = os.path.join(t1_dir, "named.txt")
            for path, body in ((named_prompt, GT_NAMED_PROMPT), (named_letter, GT_NAMED_LETTER)):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(body)
            named = subprocess.run(
                [sys.executable, analyzer, named_letter, "--task", "1gt",
                 "--prompt", named_prompt, "--json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            check(named.returncode == 0, "a letter to a named friend runs")
            if named.returncode == 0:
                letter = json.loads(named.stdout.decode("utf-8"))["task1"]
                check(letter["letter"]["has_greeting"] is True,
                      '"Dear Tom," counts as a greeting rather than a missing one')
                check(letter["letter"]["closing_matches_greeting"] is True,
                      '"Best wishes" is an acceptable close after a named recipient')
                check(not any("缺少称呼" in finding for finding in letter["findings"]),
                      "a named greeting produces no false missing-greeting finding")

                # ...but the pairing that really is wrong must still be caught.
                wrong_letter = os.path.join(t1_dir, "wrong-close.txt")
                with open(wrong_letter, "w", encoding="utf-8") as handle:
                    handle.write(GT_NAMED_LETTER.replace("Best wishes,", "Yours faithfully,"))
                wrong = subprocess.run(
                    [sys.executable, analyzer, wrong_letter, "--task", "1gt",
                     "--prompt", named_prompt, "--json"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                check(wrong.returncode == 0, "a mispaired closing still runs")
                if wrong.returncode == 0:
                    letter = json.loads(wrong.stdout.decode("utf-8"))["task1"]
                    check(letter["letter"]["closing_matches_greeting"] is False,
                          '"Yours faithfully" after a named recipient is still a mismatch')
    finally:
        shutil.rmtree(t1_dir, ignore_errors=True)

    print("\n[10] docx builder refuses to deliver a document with nothing anchored")
    guard_dir = tempfile.mkdtemp(prefix="ielts-guard-")
    try:
        dup_essay = os.path.join(guard_dir, "dup.txt")
        dup_report = os.path.join(guard_dir, "dup.md")
        for path, body in ((dup_essay, DUPLICATE_ESSAY), (dup_report, DUPLICATE_REPORT)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        dup_out = os.path.join(guard_dir, "dup.docx")
        dup = subprocess.run(
            [sys.executable, builder, "--essay", dup_essay, "--report", dup_report, "--out", dup_out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(dup.returncode == 0, "a repeated phrase still builds")
        if dup.returncode == 0:
            with zipfile.ZipFile(dup_out) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            placed = [child.get("{%s}id" % W)
                      for paragraph in document.iter("{%s}p" % W)
                      for child in paragraph
                      if child.tag == "{%s}commentRangeStart" % W]
            check(len(placed) == 2,
                  "two rows about a repeated phrase mark two separate places (%d)" % len(placed))

        # A report written in English must parse, not half-parse.
        en_essay = os.path.join(guard_dir, "en-essay.txt")
        en_report = os.path.join(guard_dir, "en-report.md")
        for path, body in ((en_essay, DUPLICATE_ESSAY), (en_report, EN_REPORT_FIXTURE)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        en_out = os.path.join(guard_dir, "en.docx")
        english = subprocess.run(
            [sys.executable, builder, "--essay", en_essay, "--report", en_report, "--out", en_out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(english.returncode == 0, "an English report builds")
        if english.returncode == 0:
            with zipfile.ZipFile(en_out) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            text = "".join(node.text or "" for node in document.iter("{%s}t" % W))
            check("pay attention on the education" in text,
                  "an English error list still yields a comment")
            check("pay attention to education" in text,
                  "an English Sentence Upgrades section still yields a rewrite")
            check("Grammatical Range" in text, "an English score card reaches the score page")

        # Codes present but no rows parsed means the section was not recognised.
        mystery = os.path.join(guard_dir, "mystery.md")
        with open(mystery, "w", encoding="utf-8") as handle:
            handle.write(EN_REPORT_FIXTURE.replace("## Error List", "## Something Else"))
        mystery_out = os.path.join(guard_dir, "mystery.docx")
        half = subprocess.run(
            [sys.executable, builder, "--essay", en_essay, "--report", mystery, "--out", mystery_out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(half.returncode != 0, "a half-parsed report fails instead of shipping")
        check(b"BUILD FAILED" in half.stdout, "the half-parse failure names itself")
        check(not os.path.exists(mystery_out), "the half-parsed document is removed")

        # Astral-plane characters are valid XML and must survive the round trip.
        emoji_essay = os.path.join(guard_dir, "emoji.txt")
        emoji_report = os.path.join(guard_dir, "emoji.md")
        with open(emoji_essay, "w", encoding="utf-8") as handle:
            handle.write(EMOJI_ESSAY)
        with open(emoji_report, "w", encoding="utf-8") as handle:
            handle.write(EMOJI_REPORT_FIXTURE)
        emoji_out = os.path.join(guard_dir, "emoji.docx")
        emoji = subprocess.run(
            [sys.executable, builder, "--essay", emoji_essay, "--report", emoji_report,
             "--out", emoji_out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(emoji.returncode == 0, "an essay with astral-plane characters builds")
        if emoji.returncode == 0:
            with zipfile.ZipFile(emoji_out) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            text = "".join(node.text or "" for node in document.iter("{%s}t" % W))
            check("\U0001F600" in text, "an emoji survives the XML round trip")
            check("\u201c" in text and "\u2014" in text,
                  "full-width punctuation and dashes survive too")

        # An essay that shares nothing with the report must not yield a file.
        # (Passing the report itself would not work as a probe: its error table
        # literally contains the quoted fragments, so they would anchor.)
        unrelated = os.path.join(guard_dir, "unrelated.txt")
        with open(unrelated, "w", encoding="utf-8") as handle:
            handle.write("A completely unrelated essay about a different subject "
                         "altogether, which shares no wording with the report.\n")
        mismatched = os.path.join(guard_dir, "mismatch.docx")
        result = subprocess.run(
            [sys.executable, builder, "--essay", unrelated, "--report", dup_report,
             "--out", mismatched],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        check(result.returncode != 0, "nothing anchorable fails instead of exiting 0")
        check(b"BUILD FAILED" in result.stdout, "the failure names itself")
        check(not os.path.exists(mismatched), "no partial .docx is left behind")
    finally:
        shutil.rmtree(guard_dir, ignore_errors=True)

    print("\n[11] report audit: one defect must not be charged to two criteria")
    audit_dir = tempfile.mkdtemp(prefix="ielts-audit-")
    try:
        auditor = os.path.join(HERE, "audit_report.py")

        def run_audit(body, name):
            path = os.path.join(audit_dir, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            return subprocess.run([sys.executable, auditor, path],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        undeclared = run_audit(AUDIT_BODY, "undeclared.md")
        check(undeclared.returncode != 0, "an undeclared cross-criterion quote fails the audit")
        check("未声明".encode("utf-8") in undeclared.stdout,
              "the audit names the missing declaration")

        declared = run_audit(AUDIT_BODY + AUDIT_OWNERSHIP, "declared.md")
        check(declared.returncode == 0, "the same report passes once ownership is declared")

        result = subprocess.run(
            [sys.executable, auditor, os.path.join(audit_dir, "declared.md"), "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data = json.loads(result.stdout.decode("utf-8"))[0]["result"]
        contested = data["contested"]
        longest = max((item["fragment"] for item in contested), key=len, default=None)
        declared_version = data
        check(len(contested) == 1,
              "an ellipsis-shortened repeat merges into one contested fragment (%d)"
              % len(contested))
        if contested:
            criteria = set(contested[0]["criteria"])
            check(criteria == {"TR", "CC", "LR"},
                  "the merged fragment lists every deducting criterion (%s)" % sorted(criteria))
            check("GRA" not in criteria,
                  "a quote used as praise in another criterion is not counted as a deduction")
        # The merged key is the longest quotation of a place; a declaration that
        # quotes only its first sentence must still be recognised as the same place.
        check(longest is not None and len(longest) > 60,
              "the merged representative is the longest quotation (%d chars)"
              % (len(longest) if longest else 0))
        check(declared_version["undeclared"] == [],
              "a declaration quoting only the first sentence still matches")

        # A scan that cannot see the evidence must say so, never pass silently.
        # Strip the long quotations out of the deductions, leaving only short
        # prose claims -- the shape of a report whose evidence is lexical.
        table_only = AUDIT_BODY
        for original, replacement in (
            ('"the government should do something about this problem" 是空泛断言，没有机制。',
             "的关键词从未出现。"),
            ('"the government should do something about this problem" 与前句缺乏衔接。',
             "缺少衔接手段。"),
            ('"the government should do something about this problem. Nothing has changed since." 语域偏低。',
             "语域偏低。"),
        ):
            table_only = table_only.replace(original, replacement)
        table_path = os.path.join(audit_dir, "table-only.md")
        with open(table_path, "w", encoding="utf-8") as handle:
            handle.write(table_only)

        result = subprocess.run([sys.executable, auditor, table_path, "--json"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data = json.loads(result.stdout.decode("utf-8"))[0]["result"]
        check(data["coverage"] == "partial",
              "evidence outside the scan's reach is reported as partial coverage (%s)"
              % data["coverage"])
        check(data["evidence_fragments"] == 0,
              "no long fragment is extracted from the table-only variant")

        rendered = subprocess.run([sys.executable, auditor, table_path],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = rendered.stdout.decode("utf-8")
        check("不等于通过" in text, "partial coverage never reads as a clean pass")
        check("✅ 通过" not in text, "partial coverage does not print the passing verdict")

    finally:
        shutil.rmtree(audit_dir, ignore_errors=True)

    print("\n[12] the documented band arithmetic is correct, and not oversimplified")
    sys.path.insert(0, HERE)
    try:
        import track_progress as tracker_module
    except ImportError as error:  # pragma: no cover
        check(False, "track_progress is importable (%s)" % error)
        tracker_module = None
    if tracker_module is not None:
        check(tracker_module.round_band(6.25) == 6.5, ".25 rounds up to the next half band")
        check(tracker_module.round_band(6.75) == 7.0, ".75 rounds up to the next whole band")
        check(tracker_module.round_band(6.125) == 6.0, ".125 rounds down")

        # The gap to the next band is not a constant. An earlier version of this
        # bundle documented "+1.5" because the three sample essays happened to sit
        # at 4B-0.5 -- a coincidence of how their scores were chosen.
        gaps = {tracker_module.next_band_gap(total / 2)["delta"] for total in range(24, 73)}
        check(gaps == {0.5, 1.0, 1.5, 2.0},
              "the cross-band gap takes all four values (%s)" % sorted(gaps))

        reference = open(os.path.join(ROOT, "references", "failure-modes.md"),
                         encoding="utf-8").read()
        check("4 × (当前总分 + 0.25) − 四项总和" in reference,
              "the reference states the gap as a formula")

        # Assert the table itself, not merely that the strings occur somewhere:
        # a guard that only greps for "+1.0" still passes after the row is
        # un-bolded or reworded, which is exactly the regression to prevent.
        documented = re.findall(r"\|\s*4B[^|]*\|[^|]*\|\s*\*\*\+([0-9.]+)\*\*\s*\|",
                                reference)
        check(sorted(float(value) for value in documented) == [0.5, 1.0, 1.5, 2.0],
              "the gap table lists exactly the four possible values (%s)" % (documented or "none"))
        check(not re.search(r"需要四项总和增加\s*\*{0,2}1\.5", reference),
              "the reference does not claim a single fixed gap")

    print("\n[12b] the scoring path carries no calibration prior")
    # Measured on 24 real essays (see references/calibration-evidence.md): an
    # earlier version of this bundle put a frequency claim in SKILL.md's
    # inviolable principles ("most untrained essays land in 5.0-6.5") plus a
    # seven-row anti-inflation checklist and a band anchor calling 6.0 "the most
    # common". The result was a regression slope of 0.32 against a reference
    # whose self-consistency is its own noise floor -- the tool used 1.0 band of
    # output range where the reference used 2.5. Adding a symmetric checklist on
    # top moved it to 0.300; removing the whole apparatus moved it to 0.450 and
    # gave the best mean absolute error of every condition tried. So the guard
    # here is not "keep the two lists balanced", it is "keep the priors out".
    protocol = open(os.path.join(ROOT, "references", "scoring-protocol.md"),
                    encoding="utf-8").read()
    skill_file = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    scoring_path = protocol + "\n" + skill_file

    remnants = [name for name in ("防虚高", "防虚低", "Band 锚点") if name in protocol]
    check(not remnants,
          "the scoring protocol carries no calibration checklist or band anchor (%s)"
          % ("; ".join(remnants) if remnants else "none"))

    # An unsourced distributional claim is a prior the reader cannot check, and
    # it installs a default band before any evidence is weighed. The patterns
    # describe *claims* rather than any occurrence of a band range: the report
    # template legitimately contains example ranges like 5.0-6.5, and an earlier
    # version of this check flagged those, which is a guard testing the wrong
    # thing.
    patterns = (r"绝大多数", r"最常见", r"最常出现", r"罕见", r"大多数考生",
                r"多数考生", r"典型考生", r"落在\s*\**\d", r"集中在\s*\**\d")
    found = [pattern for pattern in patterns if re.search(pattern, scoring_path)]
    check(not found,
          "the scoring path states no unsourced frequency claim (%s)"
          % ("; ".join(found) if found else "none"))

    evidence_path = os.path.join(ROOT, "references", "calibration-evidence.md")
    check(os.path.isfile(evidence_path),
          "the calibration evidence is kept, in its own file")
    if os.path.isfile(evidence_path):
        evidence = open(evidence_path, encoding="utf-8").read()
        # Every condition that was measured, so the record cannot be quietly
        # reduced to the one number that looks best.
        # Substring checks, not a bolded-number pattern: the mean absolute
        # errors are bolded too and collided with the slopes, which made the
        # check fail for a reason that had nothing to do with what it guards.
        missing = [value for value in ("0.321", "0.300", "0.450", "0.550")
                   if value not in evidence]
        check(not missing,
              "every measured slope is recorded, not just the best one (missing %s)"
              % ("; ".join(missing) if missing else "none"))
        check("不要在评分时加载" in evidence or "不要在打分时加载" in evidence,
              "the evidence file says it must not be loaded while scoring")

    # The release-note template is the pitch. Leading it with the band estimate
    # advertises the one number this bundle measured to be its weakest (about
    # half a band of error), so the ordering is asserted rather than left to
    # editorial drift: the report comes first, and the score is introduced with
    # its interval and its error attached.
    releasing = open(os.path.join(ROOT, "RELEASING.md"), encoding="utf-8").read()
    template = releasing.split("## 5. 可以直接复制的发布说明", 1)[-1]
    check("分数请当成区间读" in template and "平均误差约半个档位" in template,
          "the release-note template introduces the score with its interval and error")
    check("四项分项预估分" not in template,
          "the release-note template does not lead with the band estimate")
    # The suggested repository description is the same pitch in one line, and it
    # was the last place still leading with the score after the READMEs were
    # fixed. GitHub's copy of it lives in repository metadata and cannot be
    # checked from here, but the suggestion can.
    # Only the fenced block -- the surrounding prose explains that the old
    # wording led with the score, and quoting it there tripped the first version
    # of this check. Fourth time in this file that a guard matched the text
    # describing a thing instead of the thing.
    section = releasing.split("### 2.4 仓库描述建议", 1)[-1].split("\n### ", 1)[0]
    blocks = re.findall(r"```[a-z]*\n(.*?)```", section, re.S)
    suggestion = " ".join(blocks)
    check(suggestion and "四项评分" not in suggestion and "逐句证据" in suggestion,
          "the suggested repository description leads with the report, not the score")

    # Same repositioning at the front door. The READMEs are what most people
    # read first, and leading with the band estimate advertises the one number
    # measured to be the weakest -- and the one that a naive reading takes as a
    # precise result.
    for name, opener, caveat, stale in (
        ("README.md", "分数是最弱的一环", "平均绝对误差", "四项分项预估分"),
        ("README.en.md", "The score is the weakest part", "Mean absolute error",
         "four-criterion\nband estimate"),
    ):
        body = open(os.path.join(ROOT, name), encoding="utf-8").read()
        head = body[:4000]
        check(opener in head and caveat in head,
              "%s introduces the score with its measured error" % name)
        check(stale not in head,
              "%s does not lead with the band estimate" % name)
        # The calibration apparatus was removed in 1.15.0 because it compressed
        # the scores. Advertising it in the docs would be both stale and
        # backwards -- this is the check that caught it still being described.
        # Scoped to the descriptive part: the changelog legitimately describes
        # removing this apparatus, so scanning the whole file would fail on the
        # very entry that records the fix. Same trap as the literal-string
        # frequency guard below -- the check has to look where the claim lives.
        descriptive = body.split("## 版本")[0]
        leftovers = [phrase for phrase in ("Band 锚点", "虚高信号自查表", "防虚高校准")
                     if phrase in descriptive]
        check(not leftovers,
              "%s does not advertise the removed calibration apparatus (%s)"
              % (name, "; ".join(leftovers) if leftovers else "none"))

    print("\n[13] release metadata: one version, stated consistently")
    front = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    version_match = re.search(r'^\s*version:\s*"([^"]+)"', front, re.MULTILINE)
    check(version_match is not None, "SKILL.md frontmatter declares a version")
    version = version_match.group(1) if version_match else ""
    if version:
        readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        newest = re.search(r"^- \*\*(\d+\.\d+\.\d+)\*\*", readme, re.MULTILINE)
        check(newest is not None and newest.group(1) == version,
              "the newest changelog entry is the current version (%s vs %s)"
              % (newest.group(1) if newest else "none", version))
        usage = open(os.path.join(ROOT, "USAGE.md"), encoding="utf-8").read()
        check(("v" + version) in usage,
              "USAGE.md states the current version")
        with open(os.path.join(ROOT, "evals", "evals.json"), encoding="utf-8") as handle:
            evals_version = json.load(handle).get("version")
        check(evals_version == version,
              "evals.json version matches the frontmatter (%s vs %s)"
              % (evals_version, version))
        # A translated README rots against the original the moment either side is
        # bumped, so its version statement is pinned to the same source of truth.
        english = open(os.path.join(ROOT, "README.en.md"), encoding="utf-8").read()
        english_version = re.search(r"\*\*Version\s+(\d+\.\d+\.\d+)\*\*", english)
        check(english_version is not None and english_version.group(1) == version,
              "README.en.md states the current version (%s vs %s)"
              % (english_version.group(1) if english_version else "none", version))

    licence = open(os.path.join(ROOT, "LICENSE"), encoding="utf-8").read()
    check("MIT License" in licence, "LICENSE carries the MIT text")
    # GitHub reports NOASSERTION when a recognised license text carries added
    # sections, and license scanners then fail to classify the project. Keeping
    # LICENSE to the bare text is the invariant, so assert it rather than trust it.
    stray = [line for line in licence.splitlines() if line.startswith("#")]
    check(not stray,
          "LICENSE holds no added sections, so scanners can classify it (%s)"
          % (stray[:2] or "clean"))
    check(len(licence.splitlines()) <= 25,
          "LICENSE is the bare MIT text (%d lines)" % len(licence.splitlines()))

    notice_path = os.path.join(ROOT, "NOTICE.md")
    if os.path.isfile(notice_path):
        notice = open(notice_path, encoding="utf-8").read()
        check("MIT" in notice, "NOTICE.md restates the license")
        check("ChanglinY" in notice and "AaronL725" in notice,
              "NOTICE.md carries the third-party acknowledgements")
        check("IELTS" in notice, "NOTICE.md carries the trademark disclaimer")

    print("\n[14] every relative Markdown link resolves")
    dangling = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", body):
                target = match.group(1).split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = os.path.normpath(os.path.join(root, target))
                if not os.path.exists(resolved):
                    dangling.append("%s -> %s" % (os.path.relpath(path, ROOT), target))
    check(not dangling,
          "no dangling relative link (%s)" % ("; ".join(sorted(set(dangling))[:3]) or "all resolve"))

    print("\n[15] the CI workflow promises what the bundle documents")
    # CI is a claim like any other: a matrix that starts above the documented
    # minimum silently drops the promise, one that starts below it claims
    # support the code was never tested against, and a renamed script turns the
    # job green while it checks nothing. Every branch below runs on every
    # bundle so this section always contributes the same number of checks --
    # the count is itself asserted at the end, so a conditional check here
    # would report a false mismatch instead of the real defect.
    workflow_file = os.path.join(ROOT, ".github", "workflows", "selfcheck.yml")
    workflow = ""
    if os.path.isfile(workflow_file):
        with open(workflow_file, encoding="utf-8") as handle:
            workflow = handle.read()
    check(bool(workflow), "the self-check workflow shipped")

    requires = re.search(r'requires:\s*"Python (\d+\.\d+)\+', front)
    promised = requires.group(1) if requires else ""
    matrix = re.search(r"python-version:\s*\[([^\]]*)\]", workflow)
    versions = re.findall(r"['\"](\d+\.\d+)['\"]", matrix.group(1)) if matrix else []
    check(bool(promised) and versions[:1] == [promised],
          "the matrix starts at the version SKILL.md promises (%s vs %s)"
          % (versions[:1] or ["none"], promised or "not stated"))
    check(len(versions) >= 5,
          "the matrix spans the supported range (%d interpreter(s))" % len(versions))
    check("scripts/selfcheck.py" in workflow,
          "CI runs the bundle self-check, not a narrower substitute")
    # The same guard CI runs, run here: "stdlib only" is the bundle's headline
    # promise, and a promise that is only checked on someone else's machine is
    # one you cannot verify before publishing.
    guard = subprocess.run([sys.executable,
                            os.path.join(ROOT, "scripts", "check_stdlib_only.py")],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    guard_tail = guard.stdout.decode("utf-8", "replace").strip().splitlines()
    check(guard.returncode == 0 and "scripts/check_stdlib_only.py" in workflow,
          "the stdlib-only guard passes here and is the one CI runs (%s)"
          % (guard_tail[-1] if guard_tail else "no output"))
    named = set(re.findall(r"(?<![\w./-])[\w./-]*scripts/[\w./-]+\.py", workflow))
    missing = sorted(p for p in named if not os.path.exists(os.path.join(ROOT, p)))
    check(not missing,
          "every path CI names exists, so a rename cannot leave it vacuously green (%s)"
          % (missing[:3] or "all resolve"))
    # The workflow runs on pull requests from forks; a token wider than read is
    # then a real risk rather than a formality.
    check("permissions:" in workflow and "contents: read" in workflow,
          "CI asks for read-only repository access")

    # The 3.8 CI job is the real test of the version promise, but it only runs
    # after a push. Parsing every script against 3.8 grammar catches syntax that
    # needs a newer interpreter -- a `match` statement, a parenthesized context
    # manager -- before the push. It does not catch API-level additions
    # (`str.removeprefix` is 3.9), so this is a fast pre-filter rather than the
    # guarantee; the wording says so, because a check that overstates its own
    # coverage is how a bundle ends up claiming support it never tested.
    syntax_bad = []
    scripts_dir = os.path.join(ROOT, "scripts")
    if os.path.isdir(scripts_dir):
        for name in sorted(os.listdir(scripts_dir)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(scripts_dir, name), encoding="utf-8") as handle:
                source = handle.read()
            try:
                ast.parse(source, filename=name, feature_version=(3, 8))
            except SyntaxError as exc:
                syntax_bad.append("%s:%s %s" % (name, exc.lineno, exc.msg))
    check(not syntax_bad,
          "no script uses syntax newer than Python 3.8 (%s; API-level additions "
          "are the 3.8 CI job's business, not this check's)"
          % ("; ".join(syntax_bad[:2]) or "all parse under 3.8 grammar"))

    print("\n[16] calibration log: template and aggregator agree, and small samples are refused")
    cal_dir = tempfile.mkdtemp(prefix="ielts-cal-")
    try:
        calibrator = os.path.join(ROOT, "scripts", "calibrate.py")
        template_path = os.path.join(ROOT, "templates", "calibration-log.md")
        with open(template_path, encoding="utf-8") as handle:
            template = handle.read()

        # The user fills in the shipped template, so the template and the parser
        # are one contract split across two files. A label renamed on either side
        # means a correctly filled record reads as empty -- and the aggregator
        # would report "0 records", which looks like the user's mistake.
        labels = ("- 日期：", "- 题型：", "- 工具总分：", "- 你的总分：",
                  "- 你的判断来源：", "## 误报", "## 漏报")
        absent = [label for label in labels if label not in template]
        check(not absent,
              "the shipped template carries every label the aggregator reads (%s)"
              % ("; ".join(absent) if absent else "all present"))

        def write_record(directory, name, date, tool, own, source="老师",
                         false_positives=(), false_negatives=()):
            body = template
            for pattern, value in (
                (r"^- 日期：.*$", "- 日期：%s" % date),
                (r"^- 工具总分：.*$", "- 工具总分：%s" % tool),
                (r"^- 你的总分：.*$", "- 你的总分：%s" % own),
                (r"^- 你的判断来源：.*$", "- 你的判断来源：%s" % source),
            ):
                # A lambda replacement, never a string: a value containing a
                # backslash would otherwise be read as a group reference.
                body = re.sub(pattern, lambda _match, text=value: text, body,
                              count=1, flags=re.MULTILINE)
            fp_rows = "\n".join("| %s | %s |" % pair for pair in false_positives) or "|  |  |"
            fn_rows = "\n".join("| %s | %s |" % pair for pair in false_negatives) or "|  |  |"
            body = re.sub(r"(\| 工具的说法 \| 为什么不是问题 \|\n\|---\|---\|\n)\|  \|  \|",
                          lambda match: match.group(1) + fp_rows, body, count=1)
            body = re.sub(r"(\| 原文 \| 问题 \|\n\|---\|---\|\n)\|  \|  \|",
                          lambda match: match.group(1) + fn_rows, body, count=1)
            path = os.path.join(directory, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            return path

        def run_calibrate(directory, *extra):
            return subprocess.run(
                [sys.executable, calibrator, directory] + list(extra),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        empty = os.path.join(cal_dir, "empty")
        os.mkdir(empty)
        result = run_calibrate(empty)
        check(result.returncode == 0 and "没有找到校准记录" in result.stdout.decode("utf-8"),
              "an empty records directory is reported as empty, not as zero bias")

        # Two paired essays: enough to show the difference, not enough to call it
        # a bias. The refusal is the feature -- three self-authored samples once
        # produced a fabricated rule in this very bundle.
        few = os.path.join(cal_dir, "few")
        os.mkdir(few)
        for index, day in enumerate(("01", "02"), start=1):
            write_record(few, "2026-08-%s-task2.md" % day, "2026-08-%s" % day, "6.5", "6.0")
        result = run_calibrate(few)
        body = result.stdout.decode("utf-8")
        check(result.returncode == 0 and "6.5 | 6.0 | +0.5" in body,
              "the aggregator reads the scores a user filled into the shipped template")
        check("不足以下结论" in body,
              "two paired essays are not enough to state a bias direction")

        # Six paired essays, all leaning the same way: that is a direction, and
        # the one-sided case must not be dismissed just because two essays tie.
        many = os.path.join(cal_dir, "many")
        os.mkdir(many)
        outcomes = (("6.5", "6.0"), ("6.0", "6.0"), ("6.5", "5.5"),
                    ("7.0", "6.5"), ("6.0", "5.5"), ("6.5", "6.5"))
        for index, (tool, own) in enumerate(outcomes):
            write_record(many, "2026-09-%02d-task2.md" % (index + 1),
                         "2026-09-%02d" % (index + 1), tool, own,
                         false_positives=(("GRA-ART：`the society`", "抽象名词用对"),),
                         false_negatives=(("第二段没有主题句", "CC-PROG"),))
        result = run_calibrate(many)
        body = result.stdout.decode("utf-8")
        check(result.returncode == 0 and "从未出现工具偏低" in body,
              "a one-sided result is called one-sided even when some essays tie")
        check("GRA-ART" in body and "误报（工具说错、其实没错）：**6** 条" in body,
              "both finding tables are parsed and counted from the template layout")

        # The shipped template, copied and not filled in at all. Every field is
        # empty, and every field must read as empty: a pattern whose whitespace
        # can cross a line ending captures the *next* line instead, so a blank
        # "your total" silently becomes the heading below it. That is the
        # "missing versus unparsed" confusion this bundle has hit before.
        blank = os.path.join(cal_dir, "blank")
        os.mkdir(blank)
        with open(os.path.join(blank, "2026-09-20-task2.md"), "w", encoding="utf-8") as handle:
            handle.write(template)
        result = run_calibrate(blank, "--json")
        # Assert on the parsed fields, not on the aggregate: with a line-crossing
        # pattern the numeric fields still read as "missing" (the captured text
        # contains no digits), so a paired-count assertion passes while the
        # source field is quietly holding the heading from the next line. The
        # first version of this check did exactly that and certified nothing.
        check(result.returncode == 0, "an unfilled template still runs")
        if result.returncode == 0:
            summary = json.loads(result.stdout.decode("utf-8"))
            entries = summary["entries"]
            check(len(entries) == 1
                  and entries[0]["tool_total"] is None
                  and entries[0]["own_total"] is None
                  and not entries[0]["own_source"]
                  and not entries[0]["date"].startswith("#")
                  and summary["paired"] == 0
                  and not summary["signals"],
                  "an unfilled template reads as empty rather than capturing the next line (%s)"
                  % {key: entries[0][key] for key in ("date", "tool_total", "own_source")}
                  if entries else "no entries parsed")

        # A record whose comparison was left blank must be counted as unpaired
        # rather than quietly dropped or treated as a zero difference.
        write_record(many, "2026-09-30-task2.md", "2026-09-30", "6.0", "")
        result = run_calibrate(many)
        body = result.stdout.decode("utf-8")
        check("填了自己判断的：6 / 7" in body,
              "a record without the user's own score is counted as unpaired")

        # English labels, because a user may translate the template first.
        english = os.path.join(cal_dir, "english")
        os.mkdir(english)
        with open(os.path.join(english, "2026-09-10-task2.md"), "w", encoding="utf-8") as handle:
            handle.write("# Calibration log\n\n- date: 2026-09-10\n- task: Task 2\n"
                         "- tool total: 6.5\n- your total: 6.0\n- your source: teacher\n\n"
                         "## False positives\n\n| What the tool said | Why |\n|---|---|\n"
                         "| GRA-ART: `the society` | used correctly |\n\n"
                         "## Missed\n\n| Original | Problem |\n|---|---|\n"
                         "| no topic sentence | CC-PROG |\n")
        result = run_calibrate(english)
        body = result.stdout.decode("utf-8")
        check(result.returncode == 0 and "6.5 | 6.0 | +0.5" in body
              and "误报（工具说错、其实没错）：**1** 条" in body,
              "a translated record is still read rather than silently ignored")

        result = run_calibrate(os.path.join(cal_dir, "does-not-exist"))
        check(result.returncode == 2, "a missing records directory fails instead of reporting no bias")
    finally:
        shutil.rmtree(cal_dir, ignore_errors=True)

    print("\n[17] documentation claims")
    # The install command is the first thing a user copies, and it was wrong in
    # three different ways at once: README.md said v1.0.0 (eleven releases
    # stale), README.en.md said the current version, and USAGE.md said "vX.Y.Z"
    # (not copy-pasteable at all). This is the count-rot failure again, on a
    # different number -- so it gets the same treatment. RELEASING.md keeps a
    # placeholder on purpose because it is a template for the maintainer, so
    # only the user-facing docs are checked.
    stale_install = []
    for name in ("README.md", "README.en.md", "USAGE.md"):
        body = open(os.path.join(ROOT, name), encoding="utf-8").read()
        # Anchored to the unzip line so README.md's packaging template, which
        # legitimately holds vX.Y.Z, cannot satisfy it.
        declared = re.findall(r"unzip ielts-writing-coach-skill-v([\w.]+)\.zip", body)
        if not version or declared != [version]:
            stale_install.append("%s says %s" % (name, declared or "nothing"))
    check(not stale_install,
          "every user-facing install command names the current version "
          "(v%s; %s)" % (version or "?", "; ".join(stale_install) or "all agree"))

    # The install table listed three of the four default roots: it omitted
    # <projectRoot>/.dsh/skills, which is rank 100 -- the highest-priority
    # project root, and the one a reader is most likely to want. Verified
    # against @deepseek-ai/dsh-skill-filesystem's own "Roots and priority"
    # table rather than from memory. Every user-facing doc carries all four so a
    # reader on any of them gets the same answer.
    missing_roots = []
    for name in ("README.md", "README.en.md", "USAGE.md"):
        body = open(os.path.join(ROOT, name), encoding="utf-8").read()
        # Full prefixes, not fragments: "/.dsh/skills/" is a substring of
        # "~/.dsh/skills/", so the fragment form passed even after the
        # project-level row was deleted -- a guard testing a string rather than
        # the claim, for the third time in this file.
        required = (
            ("project .dsh", ("<项目根>/.dsh/skills/", "<projectRoot>/.dsh/skills/")),
            ("project .agents", ("<项目根>/.agents/skills/", "<projectRoot>/.agents/skills/")),
            ("user .agents", ("~/.agents/skills/",)),
            ("user .dsh", ("~/.dsh/skills/",)),
        )
        absent = [label for label, options in required
                  if not any(option in body for option in options)]
        if absent:
            missing_roots.append("%s lacks %s" % (name, ", ".join(absent)))
    check(not missing_roots,
          "every user-facing install table lists all four default roots (%s)"
          % ("; ".join(missing_roots) or "all present"))

    # A coverage number written in prose rots the moment a check is added; this
    # bundle got it wrong four times. Declaring it is only safe when something
    # verifies it, so every document that states the number is compared against
    # the real total. The scope was two READMEs until USAGE-EXAMPLE.md shipped
    # saying "179 项" in the same release that made it 189 -- the number had
    # simply moved to a file nothing was watching. Any document that mentions
    # the count now has to mention the right one.
    # All files are folded into one check so that this last section keeps
    # contributing exactly one check -- see the note in [15].
    total = len(checks_run) + 1  # this check is the last one
    problems = []
    # (file, patterns, whether the file must state a count at all). The two
    # READMEs must; the guides may stay quiet, but if they speak they must be
    # right -- a mandatory number in a walkthrough would be noise, a wrong one
    # is a defect.
    declared_in = (
        ("README.md", (r"自检 \*\*(\d+)\*\* 项",), True),
        ("README.en.md", (r"(\d+)\s+(?:self-)?checks?\b",), True),
        ("USAGE.md", (r"\*\*(\d+)\s*项\*\*检查",), False),
        ("USAGE-EXAMPLE.md", (r"#\s*(\d+)\s*项",), False),
    )
    for name, patterns, required in declared_in:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            if required:
                problems.append("%s is missing" % name)
            continue
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        numbers = set()
        for pattern in patterns:
            for match in re.finditer(pattern, body):
                numbers.add(int(match.group(1)))
        if not numbers:
            if required:
                problems.append("%s declares no count" % name)
        elif numbers != {total}:
            problems.append("%s says %s" % (name, "/".join(str(n) for n in sorted(numbers))))
    check(not problems,
          "every document's declared count matches the real total "
          "(total must be %d -- the TOTAL, not the passing count; %s)"
          % (total, "; ".join(problems) or "all agree"))


    print("")
    if failures:
        print("%d of %d check(s) failed" % (len(failures), len(checks_run)))
        return 1
    print("all checks passed — bundle is intact (%d checks)" % len(checks_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
