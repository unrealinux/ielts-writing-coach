# IELTS Writing Coach — an agent skill for essay correction

[中文说明](README.md) ｜ **English**

An agent skill that corrects IELTS Writing Task 1 and Task 2 essays: a four-criterion
band estimate where **every deduction quotes the student's own text**, an error-pattern
breakdown, targeted rewrites, and a shareable report — plus a `.docx` with **real Word
comments**.

Zero dependencies (Python standard library only), offline, and byte-reproducible.

**Version 1.14.0**

---

## What it does

| | |
|---|---|
| **Four-criterion estimate** | Task Response / Achievement, Coherence & Cohesion, Lexical Resource, Grammatical Range & Accuracy — each scored independently, each with quoted evidence |
| **37 error codes** | `GRA-ART` (articles), `LR-COLL` (collocation), `TR-UNDEV` (underdeveloped argument) … clustered into an **error pattern**, not a list of one-off corrections |
| **Real Word comments** | A `.docx` with comments anchored to the exact phrases, nested-comment support, and margin tags (`Articles · 冠词`) — written directly as OOXML, no `python-docx` |
| **Progress tracking** | Per-criterion trend across essays, the arithmetic of how much the next half band costs, and which error codes keep coming back |
| **Report audit** | Checks whether one defect was charged to two criteria — double-charging depresses the band systematically |
| **Calibration log** | A template you fill in per essay plus `scripts/calibrate.py`, so you can measure whether the estimate runs high or low **on your own essays**. It refuses to state a direction below 5 paired scores, and says plainly that it is not a blinded test |
| **Three independent axes** | error density (grammar), argument support, and prompt relevance are read separately and **never compensate for each other** |

### The one thing it is opinionated about

Fluent writing hides empty argument. Three essays used as test fixtures scored
**6.0 / 6.5 / 7.0 overall** while their Task Response went **6.0 → 5.5 → 5.0**: the better
the language, the harder the content problem is to notice. The skill is built to catch that
— it refuses to inflate a score because the grammar is clean, and says so explicitly in the
report.

## Install

```bash
unzip ielts-writing-coach-skill-v1.14.0.zip -d ~/.agents/skills/
python3 ~/.agents/skills/ielts-writing-coach/scripts/selfcheck.py    # 190 checks
```

Or clone into the same place:

```bash
git clone https://github.com/unrealinux/ielts-writing-coach.git \
  ~/.agents/skills/ielts-writing-coach
```

The skill is discovered from any of: `<project>/.agents/skills/`, `~/.agents/skills/`,
`~/.dsh/skills/`. **No restart needed** — a running harness watches the skill roots.

## Use

Just describe the task. The only two things that must be supplied are **the prompt** and
**the essay**:

```
Correct this IELTS Task 2 essay.

Prompt: Some people believe that university education should be free for all students.
        Others think students should pay for their own tuition.
        Discuss both views and give your own opinion.

Essay: <paste the essay>
```

Without the prompt, Task Response is **not** scored — an off-topic essay is perfectly
readable, so relevance cannot be judged from the essay alone.

Ask for the Word file when you want it:

```
Generate a .docx with comments for this essay
```

## See the output before installing

`examples/` contains a finished correction report and the `.docx` it produces, so you can
judge the output without running anything.

## How it is verified

| | |
|---|---|
| **190 self-checks** | file integrity, parsing, aggregation, DOCX structure and idempotency, task-type branching, version consistency, licence detectability, link integrity, CI-versus-docs consistency |
| **19 evaluation cases** | grammar-error, empty-argument, off-topic, Task 1 chart, GT letter |
| **Independent DOCX readers** | macOS `textutil` parses it; `qlmanage` **renders** it through Apple's layout engine |
| **CI** | self-check runs on Python 3.8 – 3.13, plus a guard that fails if any script imports anything outside the standard library |

## Boundaries — please read

- **Scores are estimates, not official results.** Real scoring is done by trained examiners.
- **It does not read charts or images.** Task 1 data accuracy must be checked by hand against
  the figure; the report says so explicitly.
- **Heuristics have false positives and negatives.** Every automated flag is labelled
  "confirm manually" in the output.
- **Thresholds are calibrated on a handful of samples.** They trigger human review; they are
  not validated cut-offs.
- **Not tested in Microsoft Word.** The document body renders correctly in Apple's engine and
  the comment markup is structurally valid, but no Word licence was available to confirm how
  Word itself displays the comments.
- **Only writing is covered** — not Speaking, Listening or Reading.
- Not affiliated with, endorsed by, or an official product of IELTS, the British Council,
  IDP or Cambridge.

## Repository layout

```
SKILL.md              the instruction set the agent loads
USAGE.md              full user guide (Chinese)
USAGE-EXAMPLE.md      a full worked walkthrough of one essay (Chinese, real output)
RELEASING.md          what to change before publishing
LICENSE / NOTICE.md   MIT text, plus attribution and trademark notes
references/           the judgement rules (scoring, band descriptors, task guides, codes)
templates/            the report template, and the calibration log a user fills in
scripts/              analyze_essay, report_to_docx, track_progress, audit_report,
                      calibrate, ielts_codes, check_stdlib_only, selfcheck
evals/                19 evaluation cases and their fixtures
examples/             a finished report and its .docx
.github/workflows/    the CI that holds the 3.8+ / stdlib-only promises
```

## Licence

MIT — see [`LICENSE`](LICENSE). Attribution and the IELTS trademark notice are in
[`NOTICE.md`](NOTICE.md).
