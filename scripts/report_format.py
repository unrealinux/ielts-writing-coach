#!/usr/bin/env python3
"""Read a correction report's score card. One implementation, two callers.

    python3 - <<'PY'
    import report_format
    print(report_format.read_score_card(text))
    PY

Why this is a module rather than a dozen lines in each script: the score card
changed shape once already, and the two readers (`track_progress.py` and
`report_to_docx.py`) must never disagree about what a report says. The earlier
layout was

    | 项目 | 预估分 | 一句话依据 |

and the current one is

    | 项目 | 预估区间 | 中点 | 一句话依据 |

The trap is that a reader which just takes "the first number in column 2" reads
`5.5-6.5` as **5.5** -- the lower bound, not the midpoint -- and then reports it
as the essay's score with no error. So the column is located by its header, and
a range cell is never used as the score.

Standard library only. Python 3.8+.
"""

import re

# Column headers, most specific first. `中点` is the tracking anchor; `预估分`
# is the older single-number layout, kept so existing reports still parse.
SCORE_HEADERS = (r"中点", r"位置", r"预估分", r"分数", r"得分", r"score", r"band")

# A cell matching one of these is a range, never a score, even if it also
# matches a score pattern.
RANGE_HEADERS = (r"区间", r"范围", r"range")

REASON_HEADERS = (r"一句话依据", r"依据", r"理由", r"说明", r"原因", r"reason", r"note")

CRITERION_PATTERNS = (
    ("TR", r"task\s*(response|achievement)|任务(回应|完成)"),
    ("CC", r"coherence|连贯|衔接"),
    ("LR", r"lexical|词汇"),
    ("GRA", r"grammatical|语法"),
)

OVERALL_PATTERNS = (r"总分", r"整体", r"总成绩", r"总体", r"overall")

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def find_section(text, keywords):
    """Return the body of the first heading whose text matches any keyword."""
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
            continue
        if len(match.group(1)) <= level:
            return "\n".join(lines[start:index])
    return "\n".join(lines[start:]) if start is not None else ""


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


def clean(cell):
    return cell.replace("*", "").replace("`", "").strip()


def parse_score(value):
    """The first plausible band in a cell, or None. Never called on a range."""
    match = re.search(r"\d+(?:\.\d+)?", value.replace("*", ""))
    if not match:
        return None
    score = float(match.group(0))
    return score if 0 < score <= 9 else None


def _match_column(header, patterns, exclude=()):
    for pattern in patterns:
        for index, cell in enumerate(header):
            text = clean(cell)
            if any(re.search(rule, text, re.IGNORECASE) for rule in exclude):
                continue
            if re.search(pattern, text, re.IGNORECASE):
                return index
    return None


def resolve_columns(rows):
    """Locate the label / range / score / reason columns from the header row.

    Falls back to positional layout only when no header is recognisable, and
    then refuses to treat a range-looking cell as a score -- guessing there
    would silently turn `5.5-6.5` into 5.5.
    """
    header = [clean(cell) for cell in rows[0]] if rows else []
    score = _match_column(header, SCORE_HEADERS, exclude=RANGE_HEADERS)
    span = _match_column(header, RANGE_HEADERS)
    reason = _match_column(header, REASON_HEADERS)

    if score is None or reason is None:
        # Header not recognised: assume the historical layout, but only for a
        # column that does not look like a range.
        body = rows[1:] if rows else []
        if score is None:
            for index in range(1, len(header)):
                values = [row[index] for row in body if len(row) > index]
                if values and all(re.fullmatch(r"\*{0,2}\d(?:\.\d)?\*{0,2}", v.strip())
                                  for v in values):
                    score = index
                    break
        if reason is None:
            reason = len(header) - 1
            # A trailing column that holds numbers is not a reason column.
            values = [row[reason] for row in body if len(row) > reason]
            if values and all(parse_score(v) is not None for v in values):
                reason = None
    return {"score": score, "range": span, "reason": reason}


def read_score_card(text):
    """Return the parsed score card, or None when there is not one.

    Keys: scores {criterion: float}, ranges {criterion: str}, overall,
    overall_range, reasons {criterion: str}, overall_note, uses_range.
    """
    block = find_section(text, [r"分数卡", r"评分卡", r"score\s*card"])
    if not block:
        return None
    rows = [row for row in table_rows(block) if len(row) >= 2]
    if len(rows) < 2:
        return None
    columns = resolve_columns(rows)
    if columns["score"] is None:
        return None

    def cell(row, index):
        return clean(row[index]) if index is not None and len(row) > index else ""

    scores, ranges, reasons = {}, {}, {}
    overall = None
    overall_range = ""
    overall_note = ""
    for row in rows[1:]:
        label = clean(row[0])
        if not label:
            continue
        key = None
        for candidate, pattern in CRITERION_PATTERNS:
            if re.search(pattern, label, re.IGNORECASE):
                key = candidate
                break
        is_overall = any(re.search(pattern, label, re.IGNORECASE)
                         for pattern in OVERALL_PATTERNS)
        if key is None and not is_overall:
            continue
        if key is not None and key in scores:
            continue
        value = parse_score(cell(row, columns["score"]))
        if value is None:
            # A criterion row whose score cell is not a number means this is not
            # a score card, so the whole section is rejected rather than
            # half-read.
            return None
        span = cell(row, columns["range"])
        note = cell(row, columns["reason"])
        if is_overall:
            if overall is None:
                overall, overall_range, overall_note = value, span, note
        else:
            scores[key] = value
            ranges[key] = span
            reasons[key] = note
    if len(scores) < 4:
        return None
    return {
        "scores": scores,
        "ranges": ranges,
        "reasons": reasons,
        "overall": overall,
        "overall_range": overall_range,
        "overall_note": overall_note,
        "uses_range": bool(overall_range or any(ranges.values())),
    }
