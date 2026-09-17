#!/usr/bin/env python3
"""The shared error-code table for the IELTS writing skills.

One code has three faces, and every script needs the same mapping:

    code    GRA-ART          machine key used in reports and for counting
    tag     Articles         short English margin note, for Word comments
    zh      冠词              one-word Chinese label, for Chinese output

Keeping this in one module stops the tracking report and the .docx builder from
drifting apart on what `LR-COLL` is called. Scripts import it defensively: if a
user copies a single script out of the bundle, the lookups degrade to the raw
code instead of failing.

Standard library only. Python 3.8+.
"""

# code -> (margin tag, Chinese label)
CODES = {
    # Grammatical Range and Accuracy
    "GRA-SVA": ("Agreement", "主谓一致"),
    "GRA-TENSE": ("Tense", "时态"),
    "GRA-ART": ("Articles", "冠词"),
    "GRA-PLU": ("Singular/plural", "名词单复数"),
    "GRA-PREP": ("Preposition", "介词"),
    "GRA-FRAG": ("Fragment", "残句"),
    "GRA-RUN": ("Run-on", "粘连句/逗号拼接"),
    "GRA-WO": ("Word order", "语序"),
    "GRA-CLAUSE": ("Clause", "从句结构"),
    "GRA-VOICE": ("Voice", "语态"),
    "GRA-COMP": ("Comparison", "比较结构"),
    "GRA-PUNC": ("Punctuation", "标点"),
    # Lexical Resource
    "LR-COLL": ("Collocation", "搭配"),
    "LR-WF": ("Word form", "词形"),
    "LR-WW": ("Word choice", "选词"),
    "LR-SP": ("Spelling", "拼写"),
    "LR-REG": ("Informal", "语域"),
    "LR-REP": ("Repetition", "重复"),
    "LR-CHING": ("Chinglish", "中式英语"),
    "LR-IDIOM": ("Cliche", "习语误用"),
    # Coherence and Cohesion
    "CC-REF": ("Reference", "指代"),
    "CC-LINK": ("Linking", "连接词"),
    "CC-PARA": ("Paragraphing", "分段"),
    "CC-PROG": ("Flow", "信息推进"),
    "CC-TOPIC": ("Topic sentence", "中心句"),
    # Task Response (Task 2)
    "TR-OFF": ("Off-topic", "偏题"),
    "TR-PART": ("Missed part", "漏答要点"),
    "TR-UNDEV": ("Underdeveloped", "论证不足"),
    "TR-GEN": ("Vague", "空泛"),
    "TR-INCON": ("Position shifts", "立场不一致"),
    "TR-TEMPLATE": ("Template", "模板化"),
    # Task Achievement (Task 1)
    "TA-OVER": ("No overview", "缺概述"),
    "TA-DATA": ("Data error", "数据错误"),
    "TA-FEAT": ("Key feature missed", "关键特征遗漏"),
    "TA-OPINION": ("Opinion in Task 1", "加入观点"),
    "TA-BULLET": ("Bullet missed", "漏 bullet"),
    "TA-TONE": ("Tone", "语气不一致"),
}


def is_code(value):
    return value in CODES


def tag_for(code):
    """Return the short margin tag, or the code itself when unknown."""
    entry = CODES.get(normalize_code(code))
    return entry[0] if entry else (code or "")


def zh_for(code):
    """Return the one-word Chinese label, or an empty string when unknown."""
    entry = CODES.get(normalize_code(code))
    return entry[1] if entry else ""


def normalize_code(value):
    """Pull a canonical code out of a report cell.

    Reports legitimately annotate a code (`LR-WW（精确度）`, `TA-OVER*`). The
    annotation is useful to a human reader and noise to a lookup, so it is
    stripped here rather than at every call site.
    """
    if not value:
        return ""
    text = value.upper()
    if text in CODES:
        return text
    import re
    match = re.search(r"\b(GRA|LR|CC|TR|TA)-([A-Z]{2,8})\b", text)
    return "%s-%s" % (match.group(1), match.group(2)) if match else ""
