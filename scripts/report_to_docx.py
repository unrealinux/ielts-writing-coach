#!/usr/bin/env python3
"""Turn a Markdown correction report into a .docx with real Word comments.

Word comments are not decorative: a student can click them, accept or reject
them, and print a copy that a teacher can read. A Markdown report is
write-only by comparison. This script closes that gap without adding a
dependency: it writes the OOXML package directly with `zipfile`, so the only
requirement is the standard library.

Input is the pair the skill already produces:
    --essay   the student's essay (plain text, one paragraph per blank line)
    --report  the Markdown report written by this skill

The error list supplies short anchored comments, and the "句子升级" section
supplies the italic rewrites inserted after the affected paragraph. Anything
that cannot be located verbatim in the essay is reported as unanchored rather
than attached to the wrong text.

Output is byte-identical for identical input, so it can be diffed and re-run.

Standard library only. Python 3.8+.

Usage:
    python3 report_to_docx.py --essay my.txt --report my.md
    python3 report_to_docx.py --essay my.txt --report my.md --out MyEssay.docx
    python3 report_to_docx.py --validate-only MyEssay.docx
"""

import argparse
import os
import re
import sys
import zipfile

try:
    import xml.etree.ElementTree as ET
except ImportError:  # pragma: no cover
    ET = None

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

try:
    from ielts_codes import normalize_code, tag_for, zh_for
except ImportError:  # a single script copied out of the bundle
    def normalize_code(value):
        return value or ""

    def tag_for(value):
        return value or ""

    def zh_for(value):
        return ""

COMMENT_AUTHOR = "IELTS Writing Coach"
COMMENT_INITIALS = "IWC"

# Scores use Times New Roman; Word's default fonts would look wrong in a
# document that a teacher may read.
BODY_FONT = "Times New Roman"


# --- XML primitives --------------------------------------------------------------

def esc(text):
    """Escape text for XML content and drop characters XML 1.0 forbids."""
    cleaned = []
    for char in text:
        code = ord(char)
        # XML 1.0 valid characters. The astral planes (0x10000-0x10FFFF) are
        # valid and hold every emoji: stopping at 0xFFFD silently deleted them.
        if (code in (0x9, 0xA, 0xD) or 0x20 <= code <= 0xD7FF
                or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF):
            cleaned.append(char)
    value = "".join(cleaned)
    return (value.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))


def rpr(bold=False, italic=False, color=None, size=None, style=None):
    """Build <w:rPr> in schema order: rStyle, rFonts, b, i, color, sz."""
    parts = []
    if style:
        parts.append('<w:rStyle w:val="%s"/>' % esc(style))
    parts.append('<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s"/>' % (BODY_FONT, BODY_FONT, BODY_FONT))
    if bold:
        parts.append("<w:b/>")
    if italic:
        parts.append("<w:i/>")
    if color:
        parts.append('<w:color w:val="%s"/>' % esc(color))
    if size:
        parts.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size))
    return "<w:rPr>%s</w:rPr>" % "".join(parts)


def run(text, **kwargs):
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr(**kwargs), esc(text))


def ppr(spacing_after=None, indent_left=None, justify=None, outline=None, keep_next=False):
    """Build <w:pPr> in schema order: keepNext, spacing, ind, jc, outlineLvl."""
    parts = []
    if keep_next:
        parts.append("<w:keepNext/>")
    if spacing_after is not None:
        parts.append('<w:spacing w:after="%d"/>' % spacing_after)
    if indent_left is not None:
        parts.append('<w:ind w:left="%d"/>' % indent_left)
    if justify:
        parts.append('<w:jc w:val="%s"/>' % justify)
    if outline is not None:
        parts.append('<w:outlineLvl w:val="%d"/>' % outline)
    return "<w:pPr>%s</w:pPr>" % "".join(parts) if parts else ""


def paragraph(runs_xml, **kwargs):
    return "<w:p>%s%s</w:p>" % (ppr(**kwargs), runs_xml)


def page_break():
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def table(rows, widths, header=True):
    """Render a bordered table. Explicit borders avoid needing a table style."""
    borders = "".join(
        '<w:%s w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>' % edge
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    out = ['<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
           '<w:tblBorders>%s</w:tblBorders></w:tblPr>' % borders]
    out.append("<w:tblGrid>%s</w:tblGrid>" % "".join(
        '<w:gridCol w:w="%d"/>' % width for width in widths))
    for row_index, cells in enumerate(rows):
        out.append("<w:tr>")
        for cell_index, cell in enumerate(cells):
            width = widths[cell_index] if cell_index < len(widths) else widths[-1]
            out.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>' % width)
            is_header = header and row_index == 0
            for line_index, line in enumerate(str(cell).split("\n")):
                out.append(paragraph(
                    run(line, bold=is_header, size=18),
                    spacing_after=40 if line_index else 40,
                ))
            out.append("</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    # Word requires a paragraph after a table at the end of a body or cell run.
    out.append(paragraph("", spacing_after=120))
    return "".join(out)


# --- Markdown report parsing -----------------------------------------------------

CRITERIA_ORDER = ["TR", "CC", "LR", "GRA"]
CRITERIA_PATTERNS = [
    ("TR", r"task\s*response|task\s*achievement|\bTR\b|\bTA\b|任务回应|任务达成"),
    ("CC", r"coherence|\bCC\b|连贯"),
    ("LR", r"lexical|\bLR\b|词汇"),
    ("GRA", r"grammatical|\bGRA\b|语法"),
]
CRITERIA_FULL = {
    "TR": "Task Response / Task Achievement",
    "CC": "Coherence & Cohesion",
    "LR": "Lexical Resource",
    "GRA": "Grammatical Range & Accuracy",
}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
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


def clean_markdown(value):
    """Strip the inline markup a report uses, keeping the readable text."""
    text = EMPHASIS_RE.sub("", value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def table_rows(block):
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        yield cells


def parse_score_card(text):
    block = find_section(text, [r"分数卡", r"评分卡", r"score\s*card"])
    if not block:
        return None
    scores = {}
    reasons = {}
    overall = None
    overall_note = ""
    for cells in table_rows(block):
        if len(cells) < 2:
            continue
        label = clean_markdown(cells[0])
        if re.search(r"总分|overall|总成绩", label, re.IGNORECASE):
            if overall is None:
                number = re.search(r"\d+(?:\.\d+)?", cells[1])
                overall = number.group(0) if number else None
                overall_note = clean_markdown(cells[2]) if len(cells) > 2 else ""
            continue
        for key, pattern in CRITERIA_PATTERNS:
            if key in scores or not re.search(pattern, label, re.IGNORECASE):
                continue
            number = re.search(r"\d+(?:\.\d+)?", cells[1])
            if number:
                scores[key] = number.group(0)
                reasons[key] = clean_markdown(cells[2]) if len(cells) > 2 else ""
    if len(scores) < 4:
        return None
    return {"scores": scores, "reasons": reasons, "overall": overall, "overall_note": overall_note}


def parse_error_list(text):
    """Read the error/defect list: position, original, code, fix, reason.

    Column layout is read from the header rather than assumed, because the
    template's `#` index column shifts every position by one and a report may
    legitimately drop it.
    """
    for heading in ERROR_LIST_HEADINGS:
        block = find_section(text, [heading])
        if not block:
            continue

        header = None
        raw_rows = []
        for cells in table_rows(block):
            cleaned = [clean_markdown(cell) for cell in cells]
            if header is None:
                header = cleaned
                continue
            raw_rows.append(cleaned)
        if not header or not raw_rows:
            continue

        def column(*names):
            for name in names:
                for index, title in enumerate(header):
                    if re.search(name, title, re.IGNORECASE):
                        return index
            return None

        index = {
            "where": column(r"位置", r"¶", r"段落", r"where", r"position", r"location"),
            "original": column(r"原文", r"原句", r"original", r"quote"),
            "code": column(r"代码", r"code"),
            "fix": column(r"修改", r"改为", r"fix", r"correction"),
            "reason": column(r"原因", r"说明", r"reason", r"why"),
        }
        if index["original"] is None or index["code"] is None:
            # Positional fallback: a leading index column, if present, offsets
            # everything by one.
            offset = 1 if re.fullmatch(r"#|\d*", header[0] or "") else 0
            for position, name in enumerate(["where", "original", "code", "fix", "reason"]):
                index[name] = position + offset

        rows = []
        for cells in raw_rows:
            def pick(name):
                position = index.get(name)
                if position is None or position >= len(cells):
                    return ""
                return cells[position]

            original = pick("original")
            code = pick("code")
            if not original and not code:
                continue
            rows.append({
                "where": pick("where"),
                "original": original,
                "code": code,
                "fix": pick("fix"),
                "reason": pick("reason"),
            })
        if rows:
            return rows
    return []


def parse_rewrites(text):
    """Read the before/after pairs from the sentence-upgrade section."""
    block = find_section(text, REWRITE_HEADINGS)
    if not block:
        return []
    pairs = []
    chunks = re.split(r"\n(?=#{2,6}\s)", block)
    for chunk in chunks:
        original = re.search(r"\*\*(?:原文|Original|Source)\*\*\s*\n((?:>.*\n?)+)",
                             chunk, re.IGNORECASE)
        rewrite = re.search(r"\*\*(?:改写|Rewrite|Rewritten|Improved)\*\*\s*\n((?:>.*\n?)+)",
                            chunk, re.IGNORECASE)
        if not rewrite:
            continue
        note = re.search(r"\*\*(?:改动说明|说明|Note|Why|Rationale)\*\*\s*[：:]?\s*(.+)",
                         chunk, re.IGNORECASE)
        pairs.append({
            "original": clean_markdown(_unquote(original.group(1))) if original else "",
            "rewrite": clean_markdown(_unquote(rewrite.group(1))),
            "note": clean_markdown(note.group(1)) if note else "",
        })
    return pairs


def _unquote(block):
    lines = [re.sub(r"^\s*>\s?", "", line) for line in block.splitlines()]
    return " ".join(line for line in lines if line.strip())


ERROR_LIST_HEADINGS = [r"错误清单", r"缺陷清单", r"错误列表",
                       r"error\s*list", r"error\s*table", r"defect\s*list"]
REWRITE_HEADINGS = [r"句子升级", r"改写对照", r"升级对照",
                    r"sentence\s*upgrades?", r"rewrites?", r"before\s*(?:and|/|→)\s*after"]
PATTERN_HEADINGS = [r"错误模式小结", r"缺陷模式小结", r"error\s*patterns?", r"recurring\s*patterns?"]
ACTION_HEADINGS = [r"下一步", r"next\s*steps?", r"action\s*(?:plan|items?)"]
# A report that talks about codes but yields no error rows means the section was
# not recognised, not that the essay was flawless.
CODE_MENTION_RE = re.compile(r"\b(?:GRA|LR|CC|TR|TA)-[A-Z]{2,8}\b")

MODEL_META_RE = re.compile(r"学习结构|不要背诵|以下演示|以下示范|仅供|注意：")
MODEL_HEADINGS = [r"目标分段示范", r"示范段落", r"范文段落", r"model paragraph", r"目标分示范"]


def parse_model_paragraph(text):
    """Read the teaching paragraph from the report's appendix.

    The appendix opens with an instruction line ("learn the structure, do not
    memorise it") that is also a blockquote, so quote lines carrying that
    instruction are dropped rather than shipped as if they were model prose.
    """
    block = find_section(text, MODEL_HEADINGS)
    if not block:
        return None

    quoted = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        content = re.sub(r"^\s*>\s?", "", line).strip()
        if not content or MODEL_META_RE.search(content):
            continue
        quoted.append(content)
    paragraph = clean_markdown(" ".join(quoted))

    why = []
    for cells in table_rows(block):
        if len(cells) < 2:
            continue
        first = clean_markdown(cells[0])
        if first in ("评分项", "项目", "评分维度"):
            continue
        why.append([first, clean_markdown(cells[1])])

    if not paragraph and not why:
        return None
    return {"paragraph": paragraph, "why": why}


def parse_meta(text):
    meta = {"date": "", "task": "", "topic": ""}
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if date_match:
        meta["date"] = date_match.group(1)
    task_match = re.search(r"task\s*([12])", text, re.IGNORECASE)
    if task_match:
        meta["task"] = "Task %s" % task_match.group(1)
    topic_match = re.search(r"^>\s*\*{0,2}题目\*{0,2}\s*[：:]\s*(.+)$", text, re.MULTILINE)
    if topic_match:
        meta["topic"] = clean_markdown(topic_match.group(1))
    return meta


def parse_paragraph_block(text, *headings):
    block = find_section(text, list(headings))
    if not block:
        return []
    lines = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith(">"):
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            continue
        lines.append(clean_markdown(re.sub(r"^[-*]\s*", "", stripped)))
    return [line for line in lines if line]


# --- Anchoring --------------------------------------------------------------------

def split_essay(text):
    """Split an essay into paragraphs, normalising internal whitespace."""
    blocks = re.split(r"\n\s*\n", text.strip())
    result = []
    for block in blocks:
        collapsed = re.sub(r"\s+", " ", block).strip()
        if collapsed:
            result.append(collapsed)
    return result


ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…)\s*")
# A report may merge several quotations into one cell, separated by " / ".
SLASH_RE = re.compile(r"\s+/\s+")
QUOTE_CHARS = "\"'“”‘’「」『』"


def anchor_candidates(fragment):
    """Turn a quoted report fragment into strings to search for, best first.

    A report may wrap the original in quotes, elide the middle
    (`"This essay will examine both ... before reaching a conclusion"`), or merge
    several quotations into one cell (`money / teaching quality`). None of those
    survive a verbatim search, so quotes are stripped and every separator-free
    segment is tried on its own, longest first -- the longest segment is the most
    specific thing that is actually present in the essay.
    """
    text = re.sub(r"\s+", " ", (fragment or "").strip()).strip(QUOTE_CHARS).strip()
    pieces = []
    for segment in ELLIPSIS_RE.split(text):
        pieces.extend(SLASH_RE.split(segment))

    segments = [piece.strip(QUOTE_CHARS).strip() for piece in pieces]
    segments = [segment for segment in segments if len(segment) >= 6]
    segments.sort(key=len, reverse=True)

    candidates = []
    for segment in segments:
        candidates.append(segment)
        words = segment.split()
        if len(words) > 12:
            candidates.append(" ".join(words[:12]))
        if len(words) > 7:
            candidates.append(" ".join(words[:7]))
    if not candidates and len(text) >= 6:
        candidates.append(text)
    return candidates


def _occurrences(haystack, needle):
    """Every start offset of needle in haystack, case-sensitive first."""
    found = []
    start = 0
    while True:
        position = haystack.find(needle, start)
        if position < 0:
            break
        found.append(position)
        start = position + 1
    if found:
        return found
    lowered, target, start = haystack.lower(), needle.lower(), 0
    while True:
        position = lowered.find(target, start)
        if position < 0:
            break
        found.append(position)
        start = position + 1
    return found


def locate(paragraphs, fragment, used):
    """Find a fragment in the essay.

    Each occurrence is considered, and one that has not been used yet wins. That
    matters when a mistake is repeated: two report rows quoting the same wrong
    phrase are two occurrences in the student's text, and both must be marked.
    When every occurrence is already taken the first one is returned, so two rows
    about the *same* place still merge into one comment.

    Returns (paragraph_index, start, end) or None. A report quotes the student's
    text verbatim, so this is a literal search; when nothing matches, the caller
    records the note as unanchored rather than attach it to other text.
    """
    fallback = None
    for needle in anchor_candidates(fragment):
        for index, paragraph in enumerate(paragraphs):
            for position in _occurrences(paragraph, needle):
                span = (index, position, position + len(needle))
                if (index, position) not in used:
                    return span
                if fallback is None:
                    fallback = span
    return fallback


def comment_lines(comment):
    """Compose one Word comment from its merged report rows.

    The shape deliberately mirrors a teacher's margin note: a short scannable
    tag first, then the correction, then the reasoning in small grey type. The
    tag is what makes a page readable at a glance -- seeing "Articles" five times
    down the margin communicates more than five sentences of explanation.

    Two report rows can quote the same phrase (a collocation problem and a
    register problem in the same words). Emitting two overlapping comment ranges
    for one span produces markup Word may repair away, so they are merged into a
    single comment that lists both findings.

    Returns a list of (text, kind) with kind in {"tag", "fix", "note"}.
    """
    lines = []
    for index, item in enumerate(comment["items"]):
        tag = tag_for(item["code"])
        label = zh_for(item["code"])
        heading = " · ".join(part for part in (tag, label) if part)
        if heading:
            lines.append((heading, "tag"))
        if item["fix"]:
            lines.append(("→ " + item["fix"], "fix"))
        if item["reason"]:
            lines.append((item["reason"], "note"))
        if index == 0 and item.get("where"):
            lines.append((item["where"], "note"))
    return lines or [("（无内容）", "note")]


def select_nestable(spans):
    """Keep the largest subset of spans that can be properly nested.

    Word renders nested comment ranges correctly, but a partial overlap
    (A=[0,10], B=[5,15]) has no valid XML shape. Rather than hand Word markup it
    may repair away, the offending span is dropped here and re-flagged as
    unanchored by the caller.
    """
    kept = []
    for span in sorted(spans, key=lambda item: (item["start"], -item["end"])):
        for other in kept:
            disjoint = span["end"] <= other["start"] or other["end"] <= span["start"]
            nested = ((other["start"] <= span["start"] and span["end"] <= other["end"])
                      or (span["start"] <= other["start"] and other["end"] <= span["end"]))
            if not (disjoint or nested):
                break
        else:
            kept.append(span)
    return kept


def build_paragraph_xml(paragraph_text, groups, rewrites, next_id):
    """Render one essay paragraph with its inline comment ranges.

    A stack walk emits opening and closing markers in document order, so a
    comment nested inside another stays properly nested instead of being lost.
    """
    spans = [
        {"start": group["span"][1], "end": group["span"][2], "group": group}
        for group in groups if group.get("span")
    ]
    kept = select_nestable(spans)
    kept_keys = {(span["start"], span["end"]) for span in kept}
    for span in spans:
        if (span["start"], span["end"]) not in kept_keys:
            for item in span["group"]["items"]:
                item["unanchored"] = True

    events = []
    for span in kept:
        events.append((span["start"], "open", span))
        events.append((span["end"], "close", span))

    def sort_key(event):
        position, kind, span = event
        length = span["end"] - span["start"]
        # Closes before opens at the same offset (abutting spans are not nested);
        # among opens the longest goes first, among closes the shortest does.
        return (position, 0 if kind == "close" else 1,
                length if kind == "close" else -length)

    events.sort(key=sort_key)

    pieces = []
    cursor = 0
    for position, kind, span in events:
        if position > cursor:
            pieces.append(run(paragraph_text[cursor:position]))
            cursor = position
        if kind == "open":
            comment_id = next_id[0]
            next_id[0] += 1
            span["group"]["id"] = comment_id
            pieces.append('<w:commentRangeStart w:id="%d"/>' % comment_id)
        else:
            comment_id = span["group"]["id"]
            pieces.append('<w:commentRangeEnd w:id="%d"/>' % comment_id)
            pieces.append('<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
                          '<w:commentReference w:id="%d"/></w:r>' % comment_id)
    if cursor < len(paragraph_text):
        pieces.append(run(paragraph_text[cursor:]))

    out = [paragraph("".join(pieces), spacing_after=160)]

    for rewrite in rewrites:
        out.append(paragraph(
            run("改写：", bold=True, italic=True, size=20, color="44546A")
            + run(rewrite["rewrite"], italic=True, size=20, color="44546A"),
            spacing_after=80, indent_left=360,
        ))
        if rewrite.get("note"):
            out.append(paragraph(
                run("改动说明：" + rewrite["note"], italic=True, size=18, color="7F7F7F"),
                spacing_after=200, indent_left=360,
            ))
    return "".join(out)


# --- Package parts ---------------------------------------------------------------

def build_styles():
    return XML_DECL + (
        '<w:styles xmlns:w="%s">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s"/><w:sz w:val="22"/><w:szCs w:val="22"/>'
        "</w:rPr></w:rPrDefault><w:pPrDefault/></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="character" w:styleId="CommentReference">'
        '<w:name w:val="Comment Reference"/><w:rPr><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
        "</w:styles>"
    ) % (W_NS, BODY_FONT, BODY_FONT, BODY_FONT)


def build_comments_xml(comments, timestamp):
    entries = []
    for comment in comments:
        runs = "".join(
            paragraph(run(text, size=18 if kind == "tag" else 16,
                          bold=(kind == "tag"),
                          color=None if kind != "note" else "808080"),
                      spacing_after=40)
            for text, kind in comment_lines(comment)
        )
        entries.append(
            '<w:comment w:id="%d" w:author="%s" w:date="%s" w:initials="%s">%s</w:comment>'
            % (comment["id"], esc(COMMENT_AUTHOR), timestamp, esc(COMMENT_INITIALS), runs)
        )
    return XML_DECL + '<w:comments xmlns:w="%s">%s</w:comments>' % (W_NS, "".join(entries))


def build_content_types(has_comments):
    overrides = [
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
    ]
    if has_comments:
        overrides.append(
            '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
    return XML_DECL + (
        '<Types xmlns="%s">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "%s</Types>"
    ) % (CT_NS, "".join(overrides))


def build_root_rels():
    return XML_DECL + (
        '<Relationships xmlns="%s">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    ) % PKG_REL_NS


def build_document_rels(has_comments):
    rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    if has_comments:
        rels.append('<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>')
    return XML_DECL + '<Relationships xmlns="%s">%s</Relationships>' % (PKG_REL_NS, "".join(rels))


def build_core_props(title, timestamp):
    return XML_DECL + (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>%s</dc:title><dc:creator>%s</dc:creator>"
        '<cp:lastModifiedBy>%s</cp:lastModifiedBy>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
        "</cp:coreProperties>"
    ) % (esc(title), esc(COMMENT_AUTHOR), esc(COMMENT_AUTHOR), timestamp, timestamp)


def build_document(body_paragraphs):
    return XML_DECL + (
        '<w:document xmlns:w="%s" xmlns:r="%s"><w:body>%s'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="709" '
        'w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>'
    ) % (W_NS, R_NS, "".join(body_paragraphs))


# --- Assembly ---------------------------------------------------------------------

def build_reviewed_docx(essay_text, report_text, out_path, title=None):
    paragraphs = split_essay(essay_text)
    if not paragraphs:
        raise ValueError("the essay is empty")

    meta = parse_meta(report_text)
    card = parse_score_card(report_text)
    errors = parse_error_list(report_text)
    rewrites = parse_rewrites(report_text)
    unparsed_error_list = not errors and bool(CODE_MENTION_RE.search(report_text))
    patterns = parse_paragraph_block(report_text, *PATTERN_HEADINGS)
    model = parse_model_paragraph(report_text)
    actions = parse_paragraph_block(report_text, *ACTION_HEADINGS)

    # Attach each rewrite to the paragraph that contains its original text.
    rewrites_by_paragraph = {}
    orphan_rewrites = []
    used = set()
    for rewrite in rewrites:
        source = rewrite["original"] or rewrite["rewrite"]
        found = locate(paragraphs, source, used)
        if found is None:
            orphan_rewrites.append(rewrite)
            continue
        index = found[0]
        used.add((found[0], found[1]))
        rewrites_by_paragraph.setdefault(index, []).append(rewrite)

    comments_by_paragraph = {}
    used_spans = set()
    for error in errors:
        anchor = error["original"]
        if not anchor or len(anchor) < 4:
            error["unanchored"] = True
            continue
        located = locate(paragraphs, anchor, used_spans)
        if located is None:
            error["unanchored"] = True
            continue
        index, start, end = located
        used_spans.add((index, start))
        groups = comments_by_paragraph.setdefault(index, [])
        for group in groups:
            if group["span"] == located:
                group["items"].append(error)  # same span: merge into one comment
                break
        else:
            groups.append({"span": located, "items": [error]})

    next_id = [1]
    body = []
    timestamp = (meta["date"] or "2026-01-01") + "T00:00:00Z"

    heading = title or "IELTS Writing 批改稿"
    body.append(paragraph(run(heading, bold=True, size=32), spacing_after=120, outline=0))
    subtitle = " ｜ ".join(part for part in [
        meta["date"], meta["task"],
        ("预估分 " + card["overall"]) if card and card.get("overall") else "",
    ] if part)
    if subtitle:
        body.append(paragraph(run(subtitle, size=20, color="7F7F7F"), spacing_after=80))
    if meta.get("topic"):
        body.append(paragraph(run("题目：" + meta["topic"], size=18, italic=True, color="7F7F7F"),
                              spacing_after=240))

    kept_groups = []
    for index, text_value in enumerate(paragraphs):
        body.append(build_paragraph_xml(
            text_value,
            comments_by_paragraph.get(index, []),
            rewrites_by_paragraph.get(index, []),
            next_id,
        ))
        kept_groups.extend(group for group in comments_by_paragraph.get(index, []) if "id" in group)

    body.append(page_break())
    body.append(paragraph(run("评分与反馈", bold=True, size=28), spacing_after=160, outline=1))
    body.append(paragraph(run("预估分，非官方成绩。批注与改写用于学习，不是考试评分。",
                              size=18, italic=True, color="7F7F7F"), spacing_after=200))

    if card:
        rows = [["项目", "预估分", "依据"]]
        for key in CRITERIA_ORDER:
            rows.append([CRITERIA_FULL[key], card["scores"][key], card["reasons"].get(key, "")])
        rows.append(["总分", card.get("overall") or "—", card.get("overall_note", "")])
        body.append(table(rows, [2400, 1100, 5460]))

    anchored = [error for error in errors if not error.get("unanchored")]
    unanchored = [error for error in errors if error.get("unanchored")]

    if kept_groups:
        tag_counts = {}
        for group in kept_groups:
            # One comment can carry several tags; each tag counts once per
            # comment, because the number must match the marks in the margin.
            for code in {normalize_code(item["code"]) for item in group["items"]}:
                if code:
                    tag_counts[code] = tag_counts.get(code, 0) + 1
        if tag_counts:
            body.append(paragraph(run("批注标签统计", bold=True, size=24), spacing_after=80, outline=2))
            body.append(paragraph(
                run("Word 批注里用的短标签。按次数排序——扫一遍就知道哪个问题在重复。",
                    size=18, italic=True, color="7F7F7F"), spacing_after=120))
            rows = [["标签", "含义", "批注数"]]
            for code, count in sorted(tag_counts.items(), key=lambda pair: (-pair[1], pair[0])):
                rows.append([tag_for(code), zh_for(code) or code, str(count)])
            body.append(table(rows, [3200, 3200, 1400]))
            body.append(paragraph(
                run("只统计**已锚定到原文**的批注：同一处被多行错误引用时合并计一次，"
                    "定位失败的不计入。因此与报告里的「按代码统计」可能有出入——"
                    "报告记的是错误数，这里记的是页边标注数。",
                    size=16, italic=True, color="808080"), spacing_after=200))

    if errors:
        body.append(paragraph(run("问题清单", bold=True, size=24), spacing_after=120, outline=2))
        rows = [["标签（代码）", "原文", "修改"]]
        for error in anchored + unanchored:
            marker = "" if not error.get("unanchored") else "（未锚定）"
            tag = tag_for(error["code"])
            code = normalize_code(error["code"])
            label = "%s（%s）" % (tag, code) if tag and code and tag != code else (error["code"] or "—")
            rows.append([label + marker, error["original"] or "—", error["fix"]])
        body.append(table(rows, [2400, 3200, 3360]))

    if patterns:
        body.append(paragraph(run("错误模式小结", bold=True, size=24), spacing_after=120, outline=2))
        for line in patterns:
            body.append(paragraph(run("• " + line, size=20), spacing_after=80, indent_left=180))

    if actions:
        body.append(paragraph(run("下一步", bold=True, size=24), spacing_after=120, outline=2))
        for line in actions:
            body.append(paragraph(run("• " + line, size=20), spacing_after=80, indent_left=180))

    if orphan_rewrites:
        body.append(paragraph(run("未能定位到原文的改写（未插入正文）", bold=True, size=22),
                              spacing_after=120, outline=2))
        for rewrite in orphan_rewrites:
            body.append(paragraph(run("• " + rewrite["rewrite"], size=18, italic=True, color="7F7F7F"),
                                  spacing_after=80, indent_left=180))

    if model and model["paragraph"]:
        body.append(paragraph(run("目标分段示范", bold=True, size=24), spacing_after=120, outline=2))
        body.append(paragraph(
            run("学习结构，不要背诵。", size=18, italic=True, color="7F7F7F"), spacing_after=120))
        body.append(paragraph(run(model["paragraph"], size=20), spacing_after=120, indent_left=180))
        if model["why"]:
            body.append(table([["评分项", "体现"]] + model["why"], [2400, 6560]))

    if unanchored:
        body.append(paragraph(
            run("说明：%d 条批注无法在作文原文中逐字定位，已列在上方清单中而未锚定到正文——"
                "把批注挂到错误的位置比不挂更糟。" % len(unanchored), size=18, italic=True,
                color="7F7F7F"), spacing_after=160))

    all_comments = sorted(kept_groups, key=lambda group: group["id"])
    document_xml = build_document(body)
    has_comments = bool(all_comments)
    comments_xml = build_comments_xml(all_comments, timestamp) if has_comments else None

    parts = [
        ("[Content_Types].xml", build_content_types(has_comments)),
        ("_rels/.rels", build_root_rels()),
        ("docProps/core.xml", build_core_props(title or "IELTS Writing Review", timestamp)),
        ("word/document.xml", document_xml),
        ("word/styles.xml", build_styles()),
        ("word/_rels/document.xml.rels", build_document_rels(has_comments)),
    ]
    if comments_xml is not None:
        parts.append(("word/comments.xml", comments_xml))

    write_package(out_path, parts, timestamp)
    return {
        "paragraphs": len(paragraphs),
        "comments": len(all_comments),
        "unanchored": len(unanchored),
        "rewrites": sum(len(value) for value in rewrites_by_paragraph.values()),
        "orphan_rewrites": len(orphan_rewrites),
        "has_score_card": card is not None,
        "has_model_paragraph": bool(model and model["paragraph"]),
        # A report row quoting real essay text should be locatable. If none of
        # them are, the two files almost certainly are not a pair.
        "quotable_rows": len([error for error in errors
                              if len(error.get("original") or "") >= 12]),
        "unparsed_error_list": unparsed_error_list,
    }


def write_package(path, parts, timestamp):
    """Write the zip with fixed timestamps so rebuilds are byte-identical."""
    year, month, day = (int(part) for part in timestamp[:10].split("-"))
    info_date = (year, month, day, 0, 0, 0)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts:
            info = zipfile.ZipInfo(name, date_time=info_date)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))


# --- Validation -------------------------------------------------------------------

REQUIRED_PARTS = ["[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"]


def validate_docx(path):
    """Check the package the way an independent reader would.

    The point is to fail here rather than in Word: comments that reference a
    missing id, or a relationship that is absent, produce a repair prompt that
    silently drops the student's feedback.
    """
    problems = []
    if ET is None:
        return ["xml.etree is unavailable; cannot validate"]
    if not os.path.isfile(path):
        return ["no such file: %s" % path]

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        return ["not a zip package: %s" % error]

    with archive:
        bad = archive.testzip()
        if bad:
            problems.append("corrupt member: %s" % bad)
        names = set(archive.namelist())
        for required in REQUIRED_PARTS:
            if required not in names:
                problems.append("missing part: %s" % required)

        trees = {}
        for name in sorted(names):
            if not name.endswith(".xml") and not name.endswith(".rels"):
                continue
            try:
                trees[name] = ET.fromstring(archive.read(name))
            except ET.ParseError as error:
                problems.append("%s is not well-formed XML: %s" % (name, error))
        if problems:
            return problems

        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        document = trees.get("word/document.xml")
        if document is None:
            return problems

        starts = document.findall(".//{%s}commentRangeStart" % W_NS)
        ends = document.findall(".//{%s}commentRangeEnd" % W_NS)
        refs = document.findall(".//{%s}commentReference" % W_NS)
        referenced = {node.get("{%s}id" % W_NS) for node in starts}
        ended = {node.get("{%s}id" % W_NS) for node in ends}
        referenced_refs = {node.get("{%s}id" % W_NS) for node in refs}

        has_comments_part = "word/comments.xml" in names
        if referenced and not has_comments_part:
            problems.append("%d comment range(s) but no word/comments.xml" % len(referenced))
        if has_comments_part and "comments+xml" not in content_types:
            problems.append("word/comments.xml exists but is not declared in [Content_Types].xml")

        rels_name = "word/_rels/document.xml.rels"
        if has_comments_part:
            if rels_name not in names:
                problems.append("comments.xml exists but document.xml.rels is missing")
            elif "comments.xml" not in archive.read(rels_name).decode("utf-8"):
                problems.append("document.xml.rels does not reference comments.xml")

        for comment_id in sorted(referenced):
            if comment_id not in ended:
                problems.append("commentRangeStart %s has no matching commentRangeEnd" % comment_id)
            if comment_id not in referenced_refs:
                problems.append("comment %s has no commentReference mark" % comment_id)
        for comment_id in sorted(ended - referenced):
            problems.append("commentRangeEnd %s has no matching commentRangeStart" % comment_id)

        if has_comments_part:
            comments_root = trees.get("word/comments.xml")
            declared = {node.get("{%s}id" % W_NS) for node in comments_root.findall("{%s}comment" % W_NS)}
            for comment_id in sorted(referenced - declared):
                problems.append("comment %s is referenced but not defined in comments.xml" % comment_id)
            for comment_id in sorted(declared - referenced):
                problems.append("comment %s is defined but never referenced" % comment_id)
            if not declared and referenced:
                problems.append("comments.xml defines no comments")

        # Comment ranges must wrap real text, never an empty span, and nested
        # ranges must close in the reverse order they opened.
        for parent in document.iter("{%s}p" % W_NS):
            stack = []
            for child in list(parent):
                if child.tag == "{%s}commentRangeStart" % W_NS:
                    stack.append([child.get("{%s}id" % W_NS), ""])
                elif child.tag == "{%s}commentRangeEnd" % W_NS:
                    target = child.get("{%s}id" % W_NS)
                    if not stack:
                        problems.append("commentRangeEnd %s closes nothing" % target)
                        continue
                    if stack[-1][0] != target:
                        problems.append(
                            "comment ranges are not properly nested: %s closes while %s is open"
                            % (target, stack[-1][0]))
                        continue
                    comment_id, covered = stack.pop()
                    if stack:
                        stack[-1][1] += covered
                    if not covered.strip():
                        problems.append("comment %s wraps no text" % comment_id)
                else:
                    for text_node in child.iter("{%s}t" % W_NS):
                        if stack:
                            stack[-1][1] += text_node.text or ""
            for comment_id, _ in stack:
                problems.append("commentRangeStart %s is never closed" % comment_id)

        body = document.find("{%s}body" % W_NS)
        if body is None or len(list(body)) == 0:
            problems.append("document body is empty")
        if document.findall(".//{%s}tbl" % W_NS) == []:
            problems.append("no table found (the score card is missing)")

        text_content = "".join(node.text or "" for node in document.iter("{%s}t" % W_NS))
        for label in ("Task Response", "Coherence", "Lexical Resource", "Grammatical Range"):
            if label not in text_content:
                problems.append("score page is missing the %r row" % label)

    return problems


# --- CLI --------------------------------------------------------------------------

def default_output(essay_path):
    base = os.path.basename(essay_path)
    stem = base[:-4] if base.lower().endswith(".txt") else base
    return os.path.join(os.path.dirname(os.path.abspath(essay_path)), stem + "(reviewed).docx")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a .docx with real Word comments from an essay and its correction report.")
    parser.add_argument("--essay", help="the student's essay (plain text)")
    parser.add_argument("--report", help="the Markdown correction report")
    parser.add_argument("--out", help="output .docx path (default: <essay>(reviewed).docx)")
    parser.add_argument("--title", help="document title")
    parser.add_argument("--validate-only", metavar="DOCX",
                        help="validate an existing .docx and exit")
    args = parser.parse_args(argv)

    if args.validate_only:
        problems = validate_docx(args.validate_only)
        if problems:
            for problem in problems:
                print("FAIL %s" % problem)
            return 1
        print("ok   %s is a valid package with consistent comments" % args.validate_only)
        return 0

    if not args.essay or not args.report:
        parser.error("--essay and --report are required unless --validate-only is used")
    for path in (args.essay, args.report):
        if not os.path.isfile(path):
            parser.error("no such file: %s" % path)

    with open(args.essay, "r", encoding="utf-8") as handle:
        essay_text = handle.read()
    with open(args.report, "r", encoding="utf-8") as handle:
        report_text = handle.read()

    out_path = args.out or default_output(args.essay)
    stats = build_reviewed_docx(essay_text, report_text, out_path, args.title)

    problems = validate_docx(out_path)
    sys.stdout.write("wrote %s\n" % out_path)
    sys.stdout.write("  essay paragraphs : %d\n" % stats["paragraphs"])
    sys.stdout.write("  Word comments    : %d\n" % stats["comments"])
    sys.stdout.write("  italic rewrites  : %d\n" % stats["rewrites"])
    sys.stdout.write("  model paragraph  : %s\n" % ("included" if stats["has_model_paragraph"] else "none in report"))
    if stats["unanchored"]:
        sys.stdout.write("  unanchored notes : %d (listed on the score page, not attached)\n"
                         % stats["unanchored"])
    if stats["orphan_rewrites"]:
        sys.stdout.write("  unplaced rewrites: %d\n" % stats["orphan_rewrites"])
    if not stats["has_score_card"]:
        sys.stdout.write("  WARNING: the report has no parsable score card; the score page will be sparse\n")

    # A report that names codes but yields no rows parsed only half-way; shipping
    # it would look successful and carry no annotations.
    if stats.get("unparsed_error_list"):
        try:
            os.remove(out_path)
        except OSError:
            pass
        sys.stdout.write("\nBUILD FAILED: the report mentions error codes but no error-list rows "
                         "could be read.\n")
        sys.stdout.write("  The section heading is probably not one this tool recognises.\n")
        sys.stdout.write("  Recognised error-list headings include: 错误清单 / 缺陷清单 / "
                         "Error List / Error Table\n")
        sys.stdout.write("  The partial .docx was removed; nothing was delivered.\n")
        return 1

    # Producing a comment-free document and exiting 0 hides the most likely user
    # error (wrong file pairing) behind a file that looks fine.
    if stats["comments"] == 0 and stats["quotable_rows"] > 0:
        try:
            os.remove(out_path)
        except OSError:
            pass
        sys.stdout.write("\nBUILD FAILED: 0 of %d quoted fragments were found in the essay.\n"
                         % stats["quotable_rows"])
        sys.stdout.write("  The report quotes text that does not occur in the essay you passed.\n")
        sys.stdout.write("  Most likely the two files are not a pair: wrong report, or the essay\n")
        sys.stdout.write("  was rewritten after it was reviewed.\n")
        sys.stdout.write("  essay : %s\n" % args.essay)
        sys.stdout.write("  report: %s\n" % args.report)
        sys.stdout.write("  The partial .docx was removed; nothing was delivered.\n")
        return 1

    if stats["comments"] and stats["unanchored"] > stats["comments"] * 2:
        sys.stdout.write("  WARNING: %d note(s) could not be located while only %d were anchored —\n"
                         % (stats["unanchored"], stats["comments"]))
        sys.stdout.write("           check that the essay and the report are a pair.\n")

    if problems:
        sys.stdout.write("VALIDATION FAILED:\n")
        for problem in problems:
            sys.stdout.write("  - %s\n" % problem)
        return 1
    sys.stdout.write("validation: ok\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
