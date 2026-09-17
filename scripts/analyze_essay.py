#!/usr/bin/env python3
"""IELTS essay pre-analysis.

Computes the objective, countable facts about an essay (word count, sentence
length distribution, paragraph balance, lexical variety, linking-device
density, register flags, high-frequency error patterns) so that a grader can
locate problems instead of guessing at them.

This script does NOT score the essay. Word counts and error flags are inputs to
judgement, never a band score.

Standard library only. Python 3.8+.

Usage:
    python3 analyze_essay.py essay.txt
    python3 analyze_essay.py essay.txt --task 2 --out stats.md
    python3 analyze_essay.py essay.txt --json
    cat essay.txt | python3 analyze_essay.py - --task 1
"""

import argparse
import json
import os
import re
import sys

WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")

STOPWORDS = set("""
a an the and or but if while because so that this these those it its it's is are was were be been being
of in on at to for with by from as into about over after before under between during without within
i you he she they we me him her them us my your his their our mine yours theirs
have has had do does did not no nor very more most much many some any each every all both few less
there here when where which who whom whose what how than then thus also however therefore
can could may might must shall should will would
one two three first second third
""".split())

# Linking devices grouped by the logical relation they claim to mark.
LINK_GROUPS = {
    "addition": ["moreover", "furthermore", "in addition", "additionally", "besides", "what's more", "what is more"],
    "contrast": ["however", "nevertheless", "nonetheless", "on the other hand", "in contrast", "on the contrary",
                 "by contrast", "whereas", "although", "though", "even though", "despite", "in spite of"],
    "cause_effect": ["therefore", "consequently", "as a result", "thus", "hence", "accordingly", "due to",
                     "owing to", "because of", "leads to", "results in"],
    "sequence": ["firstly", "first of all", "secondly", "thirdly", "finally", "lastly", "last but not least",
                 "to begin with", "next", "then", "subsequently"],
    "example": ["for example", "for instance", "such as", "namely", "to illustrate", "a case in point"],
    "conclusion": ["in conclusion", "to conclude", "in summary", "to sum up", "on balance", "all in all",
                   "overall", "in short"],
}

# Register violations: informal items that should not appear in academic writing.
INFORMAL = ["a lot of", "lots of", "kids", "stuff", "things", "guy", "guys", "gonna", "wanna",
            "ok", "okay", "really", "get", "got", "big", "good", "bad", "nowadays", "so so",
            "kind of", "sort of", "a bit", "pretty much", "huge"]

# Pattern probes: (code, label, regex, note)
ERROR_PROBES = [
    ("LR-PLU", "不可数/抽象名词误加复数",
     r"\b(informations|advices|researches|knowledges|equipments|furnitures|homeworks|softwares|traffics|moneys)\b",
     "不可数名词无复数形式"),
    ("LR-COLL", "冠词 + 不可数名词",
     r"\b(make|makes|made|making|do|does|did|doing|conduct|conducts|conducted|take|takes|took|"
     r"get|gets|got|give|gives|gave|provide|provides|provided)\s+(a|an)\s+"
     r"(progress|research|homework|work|training|equipment|information|advice|knowledge|news|"
     r"furniture|traffic|money|software|evidence|baggage|luggage|accommodation|feedback)\b",
     "不可数名词不能加 a/an：make progress、conduct research、give advice"),
    ("LR-COLL", "learn knowledge 类搭配",
     r"\b(learn|learned|learnt|learning)\s+(a\s+lot\s+of\s+|much\s+|some\s+)?(knowledge|information|experience)\b",
     "acquire / gain knowledge；experience 用 gain"),
    ("LR-COLL", "介词搭配",
     r"\b(depend(s|ed|ing)?\s+of|discuss(es|ed|ing)?\s+about|pay(s|ed|ing)?\s+attention\s+on|"
     r"in\s+the\s+other\s+hand|according\s+to\s+my\s+opinion|concentrate\s+in)\b",
     "depend on / discuss sth / pay attention to / on the other hand / in my opinion"),
    ("LR-CHING", "中式模板套句",
     r"(with\s+the\s+(rapid\s+)?development\s+of\s+(society|economy|science|technology)|"
     r"more\s+and\s+more|every\s+coin\s+has\s+two\s+sides|last\s+but\s+not\s+least|"
     r"as\s+the\s+say(ing)?\s+goes)",
     "换具体动因或具体权衡表述"),
    ("LR-CHING", "although/because 与 but/so 连用",
     r"\b(although|though)\b[^.!?]{0,120}?\bbut\b|\bbecause\b[^.!?]{0,120}?\bso\b",
     "英文中二者只保留一个"),
    ("GRA-PREP", "常见介词误用",
     r"\b(married\s+with|arrive\s+to|consist\s+of\s+in|interested\s+for|suffer\s+from\s+of)\b",
     "核对介词搭配"),
    ("LR-REG", "学术文中出现 I think / I very like",
     r"\b(I\s+think|I\s+very\s+like|I\s+very\s+much\s+like)\b",
     "In my view / I would argue that"),
]

# Determiners that legitimately precede a singular countable noun.
DETERMINERS = set("""
the a an this that these those my our your his her its their each every no any some
one another such which whose both all either neither half
""".split())

BARE_SINGULAR_RE = re.compile(
    r"(?<![.\w])(?:([A-Za-z]+)\s+)?"
    r"(Government|Society|City|Student|Company|Family|Parent|University|Country|Person|Child|"
    r"Teacher|School|Consumer|Employer|Employee|Resident|Tourist)\s+"
    r"(should|must|need|needs|has|have|is|are|will|can|plays|play|provides|provide|brings|bring)\b",
    re.IGNORECASE,
)


def find_bare_singulars(text):
    """Locate singular countable nouns used with no determiner at all.

    "The government has" and "a student is" are correct, so the word before the
    noun is inspected and determiner-led uses are skipped. Abstract nouns such as
    "education" or "technology" are deliberately absent from the noun list
    because they are normally uncountable and need no article.
    """
    hits = []
    for match in BARE_SINGULAR_RE.finditer(text):
        preceding = (match.group(1) or "").lower()
        if preceding in DETERMINERS:
            continue
        hits.append(match.group(0).strip())
    return hits

# Sentence-initial discourse markers that legitimately sit before a comma and
# must not be mistaken for the first clause of a comma splice.
LEADING_MARKERS = (
    "firstly|secondly|thirdly|fourthly|finally|lastly|first of all|to begin with|next|then|"
    "moreover|furthermore|in addition|additionally|besides|what is more|"
    "however|nevertheless|nonetheless|on the other hand|on the contrary|by contrast|in contrast|"
    "therefore|consequently|as a result|thus|hence|accordingly|"
    "for example|for instance|such as|namely|to illustrate|"
    "in conclusion|to conclude|in summary|to sum up|on balance|all in all|in short|overall|"
    "in my opinion|in my view|from my perspective|personally|also|still|instead|meanwhile"
)

FINITE_VERB_RE = re.compile(
    r"\b(is|are|was|were|be|been|being|has|have|had|do|does|did|will|would|can|could|may|might|"
    r"must|should|makes?|takes?|gives?|leads?|causes?|helps?|allows?|provides?|requires?|means?|"
    r"shows?|brings?|creates?|increases?|reduces?|becomes?|needs?|wants?|uses?|gets?)\b",
    re.IGNORECASE,
)

COMMA_PRONE_RE = re.compile(
    r"([^.!?\n]{0,140}?),\s+(it|they|this|these|there|he|she|we)\s+"
    r"(is|are|was|were|has|have|had|can|will|would|do|does|did)\b",
    re.IGNORECASE,
)


# A clause that opens with a subordinator is dependent, so the comma after it
# separates a dependent clause from a main clause and is correct English.
SUBORDINATOR_PREFIX_RE = re.compile(
    r"^(although|though|even though|while|whereas|because|since|if|unless|when|whenever|as|"
    r"so that|in order that|provided that|in case|until|before|after|once|even if|whether|that)\b",
    re.IGNORECASE,
)


def find_comma_splices(text):
    """Heuristically locate comma splices, rejecting dependent clauses.

    "Firstly, it can help ..." is a legitimate comma, and so is "Although X, Y",
    so the clause before the comma must survive after stripping a leading
    discourse marker, must not open with a subordinator, and must still contain
    a finite verb.
    """
    hits = []
    for match in COMMA_PRONE_RE.finditer(text):
        left = match.group(1).strip()
        if SUBORDINATOR_PREFIX_RE.match(left):
            continue
        stripped = re.sub(r"^(%s)\s*,?\s*" % LEADING_MARKERS, "", left, flags=re.IGNORECASE).strip()
        if len(WORD_RE.findall(stripped)) < 3:
            continue
        if not FINITE_VERB_RE.search(stripped):
            continue
        hits.append(match.group(0).strip())
    return hits


# --- Argument-support instruments -------------------------------------------
# A separate axis from error detection. An essay can be error-free and still
# contain no reasoning at all; these counters make that visible.

EVIDENCE_RE = re.compile(
    r"\b(research|studies|survey|surveys|data|statistics|statistic|evidence|findings|"
    r"figures|percentage|per cent|percent)\b|%|\baccording to\b",
    re.IGNORECASE,
)
EXAMPLE_RE = re.compile(
    r"\b(for example|for instance|such as|namely|to illustrate|a case in point)\b",
    re.IGNORECASE,
)
CAUSAL_RE = re.compile(
    r"\b(because|since|as a result|owing to|due to|leads? to|results? in|which means|"
    r"gives? rise to)\b",
    re.IGNORECASE,
)
HEDGE_RE = re.compile(
    r"\b(may|might|can|could|likely|possibly|probably|perhaps|usually|generally|often|"
    r"sometimes|relatively|somewhat|fairly|tend to|tends to|tended to|in some cases|"
    r"to some extent|it is possible|more or less)\b",
    re.IGNORECASE,
)
VAGUE_RE = re.compile(
    r"\b(positive effect|negative effect|positive impact|negative impact|positive development|"
    r"important|significant|various|a number of|several|many people|some people|aspects?|"
    r"factors?|something|things?|overall|on the whole)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*(?:s\b|%|st|nd|rd|th)?")


def count_specificity(text):
    """Count concrete particulars: figures and proper nouns.

    Generality is the default failure of fluent writing, so an essay with no
    numbers and no named entities anywhere is worth flagging. Decades ("1960s")
    and possessives of names ("Korea's") are handled explicitly, since a naive
    word-boundary scan misses both.
    """
    numbers = len(NUMBER_RE.findall(text))
    proper = 0
    for sentence in split_sentences(text):
        cores = []
        for token in sentence.split():
            core = token.strip("\"'(),.;:!?")
            for possessive in ("'s", "\u2019s"):
                if core.endswith(possessive):
                    core = core[: -len(possessive)]
            cores.append(core)
        for index, core in enumerate(cores):
            if len(core) < 2 or not core.isalpha() or not core[0].isupper() or core == "I":
                continue
            if index > 0:
                proper += 1
            elif index + 1 < len(cores) and cores[index + 1][:1].isupper():
                proper += 1  # sentence-initial half of a multi-word name
    return {"numbers": numbers, "proper_nouns": proper, "total": numbers + proper}


# --- Prompt relevance --------------------------------------------------------
# Off-topic responses cannot be detected from the essay alone: an off-topic
# essay is usually well written. These instruments compare the essay against the
# prompt's question parts and its distinctive vocabulary.

TASK_TYPES = [
    ("task1_academic",
     re.compile(r"summari[sz]e\s+the\s+information|the\s+(?:chart|graph|table|diagram|maps?|figures?)\s+below|"
                r"the\s+(?:two\s+)?(?:charts?|graphs?|maps?|tables?|diagrams?)\b.{0,40}\bshow", re.I),
     "Task 1 Academic 图表描述（必须有概述，只描述不论证）"),
    ("task1_gt",
     re.compile(r"write\s+a\s+letter|begin\s+your\s+letter|dear\s+sir\s+or\s+madam", re.I),
     "Task 1 General Training 书信（三个 bullet 全覆盖 + 语气一致）"),
    ("discussion_opinion",
     re.compile(r"discuss\s+(?:both|these)\s+(?:views?|sides?)\s+and\s+give\s+your\s+own\s+opinion", re.I),
     "讨论双方 + 给出自己的观点"),
    ("outweigh",
     re.compile(r"do\s+the\s+(?:advantages|benefits)\b.{0,60}?\boutweigh\s+the\s+(?:disadvantages|drawbacks)|"
                r"(?:advantages|benefits)\b.{0,60}?\boutweigh\b", re.I),
     "利弊权衡（必须给出比较标准与结论）"),
    ("opinion",
     re.compile(r"to\s+what\s+extent\s+do\s+you\s+(?:agree|disagree)|do\s+you\s+agree\s+or\s+disagree", re.I),
     "同意/不同意（必须给出立场与程度）"),
    ("problem_solution",
     re.compile(r"what\s+(?:are\s+the\s+)?(?:causes?|reasons?)|what\s+(?:measures?|solutions?|steps?)|"
                r"(?:causes?|reasons?).{0,60}(?:measures?|solutions?)", re.I),
     "原因 / 对策（两部分都要回应且相互对应）"),
    ("positive_negative",
     re.compile(r"(?:positive|negative)\s+(?:or\s+(?:positive|negative)\s+)?development", re.I),
     "正面/负面判断（必须给出判断并论证）"),
    ("advantages_disadvantages",
     re.compile(r"(?:advantages?|benefits?)\s+and\s+(?:disadvantages?|drawbacks?)", re.I),
     "优缺点（两面都要写）"),
]

OPINION_MARKERS = re.compile(
    r"\b(i\s+(?:think|believe|would\s+argue|am\s+convinced|agree|disagree|firmly)|"
    r"in\s+my\s+(?:view|opinion)|from\s+my\s+perspective|this\s+essay\s+argues|"
    r"my\s+(?:view|position)|it\s+is\s+my\s+view|i\s+would\s+contend)\b", re.I)
DEGREE_MARKERS = re.compile(
    r"\b(largely|partly|partially|completely|entirely|wholly|mostly|broadly|substantially|"
    r"to\s+(?:a\s+)?(?:certain|some)\s+extent|in\s+part)\b", re.I)
COMPARATIVE_MARKERS = re.compile(
    r"\b(outweigh|greater\s+than|more\s+significant|on\s+balance|to\s+a\s+greater\s+extent|"
    r"more\s+important\s+than|far\s+outweigh|net\s+benefit|stronger\s+case)\b", re.I)
SOLUTION_MARKERS = re.compile(
    r"\b(should|must|ought\s+to|measures?|solutions?|polic(?:y|ies)|governments?|authorities|"
    r"initiatives?|reforms?|investment)\b", re.I)

OVERVIEW_MARKERS = re.compile(
    r"\b(overall|in general|broadly speaking|in summary|on the whole|"
    r"it is clear that|it can be seen that|generally speaking)\b", re.IGNORECASE)

REQUIRED_COMPONENTS = {
    "task1_academic": [("概述句（Overall / In general …）", OVERVIEW_MARKERS)],
    "task1_gt": [("书信称呼（Dear …）", re.compile(r"^\s*dear\b", re.I | re.M)),
                 ("结尾敬语（Yours faithfully / sincerely …）", re.compile(r"\b(yours\s+faithfully|yours\s+sincerely|best\s+wishes|kind\s+regards)\b", re.I))],
    "discussion_opinion": [("自己的观点标记", OPINION_MARKERS)],
    "opinion": [("自己的观点标记", OPINION_MARKERS), ("程度表述（largely / to some extent…）", DEGREE_MARKERS)],
    "outweigh": [("比较结论（outweigh / greater than / on balance…）", COMPARATIVE_MARKERS)],
    "problem_solution": [("对策标记（should / measures / policy…）", SOLUTION_MARKERS)],
    "positive_negative": [("立场标记", OPINION_MARKERS)],
    "advantages_disadvantages": [("立场标记", OPINION_MARKERS)],
}

# Task-instruction and generic vocabulary, removed before comparing prompt
# vocabulary against the essay. Topic words (allowed, useful, students…) stay in.
PROMPT_FUNCTION_WORDS = set("""
think thinks thought believe believes believed opinion essay discuss discussion discussions
view views extent agree disagree advantage advantages disadvantage disadvantages benefit
benefits drawback drawbacks outweigh increasing number people question statement claim
reasons causes solutions measures example examples such
others other give gives giving own both sides side ways way rather trend nowadays
summarise summarize summarised below information selecting reporting relevant comparisons
illustrate show shows shown write letter begin main features chart graph table diagram maps
make makes made making
""".split()) | STOPWORDS


def stem(word):
    """Crude stemmer: enough to align study/studies/studied and subject/subjects."""
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[: -len(suffix)]
            break
    if w.endswith("y") and len(w) > 4:
        w = w[:-1] + "i"
    return w


# Which prompt types each `--task` value implies. A prompt that contradicts the
# flag means the report will apply the wrong branch -- e.g. Academic chart checks
# on a General Training letter -- so it must be reported rather than rendered.
EXPECTED_PROMPT_TYPES = {
    "1": {"task1_academic"},
    "1gt": {"task1_gt"},
    "2": {"discussion_opinion", "outweigh", "opinion", "problem_solution",
          "positive_negative", "advantages_disadvantages"},
}
TASK_FLAG_LABEL = {"1": "Task 1 Academic（图表）", "1gt": "Task 1 General Training（书信）",
                   "2": "Task 2"}
TYPE_LABEL = {"task1_academic": "Task 1 Academic（图表）", "task1_gt": "Task 1 General Training（书信）",
              "discussion_opinion": "Task 2（讨论+观点）", "outweigh": "Task 2（利弊权衡）",
              "opinion": "Task 2（同意/不同意）", "problem_solution": "Task 2（原因/对策）",
              "positive_negative": "Task 2（正面/负面）",
              "advantages_disadvantages": "Task 2（优缺点）"}


def find_contradictions(task, relevance):
    """Detect a `--task` flag that disagrees with the prompt.

    Running the wrong branch does not crash: it produces confident, wrong
    findings (an "overview found" verdict inside a letter, for example). So the
    contradiction has to be surfaced explicitly.
    """
    if not relevance:
        return []
    detected = {entry["type"] for entry in relevance["task_types"]}
    if not detected or detected == {"unclassified"}:
        return []
    expected = EXPECTED_PROMPT_TYPES.get(task, set())
    if detected & expected:
        return []
    flag = TASK_FLAG_LABEL.get(task, task)
    actual = "、".join(TYPE_LABEL.get(name, name) for name in sorted(detected))
    suggestion = {"1": "改用 --task 1gt", "1gt": "改用 --task 1", "2": "改用 --task 1（图表）或 --task 1gt（书信）"}
    return ["你指定的是 **%s**（`--task %s`），但题干看起来是 **%s**。"
            "第 7 节会按错误的判据检查，**该节结论不可用**。%s。"
            % (flag, task, actual, suggestion.get(task, "请确认 --task 取值"))]


def analyse_prompt_relevance(prompt, essay_text):
    """Compare the essay against the prompt's writing task and its vocabulary."""
    detected = []
    for name, pattern, label in TASK_TYPES:
        if pattern.search(prompt):
            detected.append({"type": name, "label": label})
    if not detected:
        detected.append({"type": "unclassified", "label": "未能自动识别题型"})

    components = []
    for entry in detected:
        for label, pattern in REQUIRED_COMPONENTS.get(entry["type"], []):
            components.append({
                "task": entry["type"],
                "label": label,
                "present": bool(pattern.search(essay_text)),
            })

    prompt_words = []
    for word in WORD_RE.findall(prompt):
        lowered = word.lower()
        if len(lowered) < 4 or lowered in PROMPT_FUNCTION_WORDS:
            continue
        if lowered not in prompt_words:
            prompt_words.append(lowered)

    essay_stems = {stem(w) for w in WORD_RE.findall(essay_text)}
    missing = []
    for word in prompt_words:
        if stem(word) in essay_stems:
            continue
        if len(word) >= 5:
            prefix = word[:5]
            if any(candidate.startswith(prefix) for candidate in essay_stems):
                continue
        missing.append(word)

    covered = len(prompt_words) - len(missing)
    coverage = round(covered / len(prompt_words), 3) if prompt_words else 1.0

    # Guard against a wrong --prompt (e.g. the essay passed by mistake). A
    # mistaken prompt would otherwise produce a confident false "off-topic"
    # verdict, which is worse than no verdict.
    prompt_word_count = len(tokenize_words(prompt))
    unclassified = detected[0]["type"] == "unclassified"
    suspect = None
    if prompt_word_count > 150:
        suspect = ("题目文本长达 %d 词（题干通常 20–80 词）——请确认 --prompt 指向的是题干，"
                   "而不是作文或其他文件" % prompt_word_count)
    elif unclassified and coverage < 0.55:
        suspect = ("题型未能识别，且关键词覆盖率仅 %.0f%%。这更可能是题干本身不典型，"
                   "或 --prompt 传错了文件，而非作文偏题——请人工确认后再下结论"
                   % (coverage * 100))

    return {
        "task_types": detected,
        "components": components,
        "prompt_keywords": prompt_words,
        "missing_keywords": missing,
        "coverage": coverage,
        "prompt_word_count": prompt_word_count,
        "suspect_prompt": suspect,
    }


def count_sentence_initial_connectors(sentences):
    """Count sentences that open with an explicit linking device.

    Raw device density does not separate mechanical linking from natural
    linking; the share of sentences that *open* with a device does.
    """
    count = 0
    for sentence in sentences:
        head = sentence.strip().lower()
        for devices in LINK_GROUPS.values():
            if any(head.startswith(device) for device in devices):
                count += 1
                break
    return count


# --- Task 1 instruments ----------------------------------------------------------
# Task 1 is a data-summary task, not an argument. The support-axis metrics used
# for Task 2 are actively misleading here: numbers are the task itself rather
# than evidence of reasoning, and the absence of examples and causal links is
# correct behaviour. These checks replace them.

TASK1_OPINION_MARKERS = re.compile(
    r"\b(i think|i believe|in my (?:view|opinion)|it seems to me|"
    r"should|must|ought to|need to|it is (?:very )?important|"
    r"the government|we (?:should|must|need))\b", re.IGNORECASE)
TASK1_CAUSE_MARKERS = re.compile(
    r"\b(because|because of|due to|owing to|the reason|this is why|"
    r"as a result of|is caused by|leads to)\b", re.IGNORECASE)
COMPARISON_MARKERS = re.compile(
    r"\b(more than|less than|fewer than|higher than|lower than|greater than|"
    r"compared (?:with|to)|in contrast|by contrast|whereas|while|"
    r"overtook|the highest|the lowest|the largest|the smallest|"
    r"twice|three times|similar|respectively|followed by)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PRESENT_WITH_YEAR_RE = re.compile(
    r"\b(?:19|20)\d{2}\b[^.]{0,80}?\b(is|are|shows?|stands?|remains?|accounts?)\b"
    r"(?!\s+(?:expected|projected|likely|predicted|forecast|due|set))",
    re.IGNORECASE)
PAST_FORM_RE = re.compile(
    r"\b(was|were|had|increased|decreased|rose|fell|declined|dropped|grew|remained|"
    r"peaked|reached|stood|accounted|doubled|halved|tripled|overtook|levelled)\b",
    re.IGNORECASE)
LETTER_GREETING_RE = re.compile(r"^\s*dear\s+(sir|madam|mr|mrs|ms|dr)\b", re.IGNORECASE)
LETTER_FAREWELL_RE = re.compile(
    r"\b(yours faithfully|yours sincerely|best wishes|kind regards|yours truly)\b", re.IGNORECASE)
LETTER_INFORMAL_RE = re.compile(
    r"\b(hey|hi there|gonna|wanna|cheers|mate|stuff|guys|btw)\b", re.IGNORECASE)


def analyse_task1(text, task):
    paragraphs = split_paragraphs(text)
    sentences = split_sentences(text)

    overview_sentence = ""
    for sentence in sentences:
        if OVERVIEW_MARKERS.search(sentence):
            overview_sentence = sentence
            break
    # An overview may also be written without any marker: a short early
    # paragraph that names the direction of the data but cites no figures.
    unmarked_overview = ""
    for paragraph in paragraphs[:3]:
        if re.search(r"\d", paragraph):
            continue
        if len(tokenize_words(paragraph)) < 8:
            continue
        if re.search(r"\b(increase|decrease|rise|rose|fall|fell|grow|decline|"
                     r"higher|lower|more|less|majority|minority|dominant)\b",
                     paragraph, re.IGNORECASE):
            unmarked_overview = paragraph
            break

    opinion_hits = sorted({match.group(0).lower()
                           for match in TASK1_OPINION_MARKERS.finditer(text)})
    cause_hits = sorted({match.group(0).lower()
                         for match in TASK1_CAUSE_MARKERS.finditer(text)})

    data_sentences = [s for s in sentences if re.search(r"\d", s)]
    compared = [s for s in data_sentences if COMPARISON_MARKERS.search(s)]
    mechanical_ratio = (round(1 - len(compared) / len(data_sentences), 2)
                        if data_sentences else 0.0)

    present_with_year = [s for s in sentences if PRESENT_WITH_YEAR_RE.search(s)]
    past_forms = len(PAST_FORM_RE.findall(text))
    # One past-tense data verb is enough to prove the essay mixes tenses; a
    # second-form threshold hid the error completely in the Task 1 probe.
    tense_mixing = len(present_with_year) >= 2 and past_forms >= 1

    letter = None
    if task == "1gt":
        greeting = LETTER_GREETING_RE.search(text)
        farewell = LETTER_FAREWELL_RE.search(text)
        formal_greeting = bool(greeting) and greeting.group(1).lower() in ("sir", "madam")
        letter = {
            "has_greeting": bool(greeting),
            "has_farewell": bool(farewell),
            "greeting_formal": formal_greeting,
            # "Dear Sir/Madam" pairs with "Yours faithfully"; a named recipient
            # pairs with "Yours sincerely".
            "closing_matches_greeting": bool(greeting and farewell) and (
                (formal_greeting and "faithfully" in farewell.group(0).lower())
                or (not formal_greeting and "sincerely" in farewell.group(0).lower())
            ),
            "informal_leaks": sorted({m.group(0).lower()
                                      for m in LETTER_INFORMAL_RE.finditer(text)}),
        }

    findings = []
    # A General Training letter is not a data summary: it has no overview to be
    # missing and nothing to compare. Applying the Academic checks to it told
    # letter writers their Task Achievement was capped at 5.0 for failing a
    # requirement their task never had.
    if task != "1gt":
        if not overview_sentence and not unmarked_overview:
            findings.append("❌ **没有找到概述（overview）** —— 这是 Task 1 最常见也最致命的失分点，"
                            "没有独立概述时 Task Achievement 上限 5.0。")
        if opinion_hits:
            findings.append("❌ 出现观点/建议类表达（Task 1 只描述，不评价、不建议）：%s"
                            % "、".join("`%s`" % item for item in opinion_hits))
        if cause_hits:
            findings.append("❌ 出现原因解释（Task 1 不需要解释原因）：%s"
                            % "、".join("`%s`" % item for item in cause_hits))
        if mechanical_ratio >= 0.6 and len(data_sentences) >= 4:
            findings.append("⚠️ 含数据的句子中 %.0f%% 是**纯报数**、没有比较或分组 → 倾向机械罗列，"
                            "Task Achievement 难进 7。" % (mechanical_ratio * 100))
        if tense_mixing:
            findings.append("❌ **时态混用**：图表是过去时间段，但 %d 句用了现在时（如 `%s`），"
                            "同时又有过去时形式 %d 处。"
                            % (len(present_with_year), present_with_year[0][:60], past_forms))
    if letter:
        if not letter["has_greeting"]:
            findings.append("❌ 书信缺少称呼（Dear ...）。")
        if not letter["has_farewell"]:
            findings.append("❌ 书信缺少结尾敬语（Yours faithfully / Yours sincerely …）。")
        if letter["has_greeting"] and letter["has_farewell"] and not letter["closing_matches_greeting"]:
            findings.append("❌ **称呼与结尾敬语不匹配**（Dear Sir/Madam 配 Yours faithfully；"
                            "具名收信人配 Yours sincerely）。")
        if letter["informal_leaks"]:
            findings.append("⚠️ 检出非正式表达，正式书信中应避免：%s"
                            % "、".join("`%s`" % item for item in letter["informal_leaks"]))

    return {
        "kind": "gt_letter" if task == "1gt" else "academic",
        "has_overview": bool(overview_sentence or unmarked_overview),
        "overview_sentence": overview_sentence,
        "unmarked_overview": unmarked_overview,
        "opinion_hits": opinion_hits,
        "cause_hits": cause_hits,
        "data_sentences": len(data_sentences),
        "compared_sentences": len(compared),
        "mechanical_ratio": mechanical_ratio,
        "comparison_markers": len(COMPARISON_MARKERS.findall(text)),
        "present_with_year": present_with_year,
        "past_forms": past_forms,
        "tense_mixing": tense_mixing,
        "letter": letter,
        "findings": findings,
    }

LINK_CONNECTORS_FOR_COMPLEXITY = [
    "although", "though", "even though", "while", "whereas", "because", "since", "unless",
    "if", "when", "which", "who", "that", "whose", "where", "as long as", "provided that",
    "in order to", "so that", "despite", "in spite of",
]


def read_source(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def tokenize_words(text):
    """Return word tokens with original sentence-independent casing."""
    return WORD_RE.findall(text)


def split_sentences(text):
    """Split into sentences without a full NLP pipeline.

    Abbreviations and decimals are protected with placeholders so that
    "e.g." and "3.5" do not create spurious sentence boundaries.
    """
    protected = text
    for index, abbr in enumerate(["e.g.", "i.e.", "etc.", "Mr.", "Mrs.", "Ms.", "Dr.", "vs.", "No."]):
        protected = protected.replace(abbr, "\u0000%d\u0000" % index)
    protected = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + "\x01" + m.group(2), protected)

    raw = SENTENCE_SPLIT_RE.split(protected.strip())
    sentences = []
    for chunk in raw:
        restored = chunk
        for index, abbr in enumerate(["e.g.", "i.e.", "etc.", "Mr.", "Mrs.", "Ms.", "Dr.", "vs.", "No."]):
            restored = restored.replace("\u0000%d\u0000" % index, abbr)
        restored = restored.replace("\x01", ".")
        restored = restored.strip()
        if restored:
            sentences.append(restored)
    return sentences


def split_paragraphs(text):
    blocks = re.split(r"\n\s*\n", text.strip())
    return [re.sub(r"\s+", " ", block).strip() for block in blocks if block.strip()]


def count_occurrences(text, needle):
    return len(re.findall(re.escape(needle), text, flags=re.IGNORECASE))


def analyse(text, task, prompt=None):
    words = tokenize_words(text)
    lower_words = [w.lower() for w in words]
    paragraphs = split_paragraphs(text)
    sentences = split_sentences(text)

    word_count = len(words)
    sentence_lengths = [len(tokenize_words(s)) for s in sentences]
    sentence_lengths = [n for n in sentence_lengths if n > 0]

    paragraph_word_counts = [len(tokenize_words(p)) for p in paragraphs]

    content_words = [w for w in lower_words if w not in STOPWORDS and len(w) > 2]
    ttr = round(len(set(lower_words)) / word_count, 3) if word_count else 0.0
    content_ttr = round(len(set(content_words)) / len(content_words), 3) if content_words else 0.0

    frequency = {}
    for word in content_words:
        frequency[word] = frequency.get(word, 0) + 1
    repeated = sorted(
        [{"word": w, "count": c} for w, c in frequency.items() if c >= 4],
        key=lambda item: (-item["count"], item["word"]),
    )[:15]

    link_hits = {}
    link_total = 0
    for group, devices in LINK_GROUPS.items():
        for device in devices:
            count = count_occurrences(text, device)
            if count:
                link_hits.setdefault(group, []).append({"device": device, "count": count})
                link_total += count

    informal_hits = []
    for item in INFORMAL:
        pattern = r"\b%s\b" % re.escape(item)
        count = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if count:
            informal_hits.append({"item": item, "count": count})
    informal_hits.sort(key=lambda item: -item["count"])

    probes = []
    for code, label, pattern, note in ERROR_PROBES:
        matches = [m.group(0).strip() for m in re.finditer(pattern, text, flags=re.IGNORECASE)]
        if matches:
            probes.append({
                "code": code,
                "label": label,
                "count": len(matches),
                "samples": matches[:4],
                "note": note,
            })

    splices = find_comma_splices(text)
    if splices:
        probes.append({
            "code": "GRA-RUN",
            "label": "疑似逗号拼接句",
            "count": len(splices),
            "samples": splices[:4],
            "note": "两个完整句不能用逗号连接；改分号、句号或从句",
        })

    bare_singulars = find_bare_singulars(text)
    if bare_singulars:
        probes.append({
            "code": "GRA-ART",
            "label": "可数名词单数裸用（启发式）",
            "count": len(bare_singulars),
            "samples": bare_singulars[:4],
            "note": "可数名词单数前通常需要限定词：The government / Governments",
        })
    probes.sort(key=lambda probe: (probe["code"], -probe["count"]))

    complexity_hits = 0
    for connector in LINK_CONNECTORS_FOR_COMPLEXITY:
        complexity_hits += count_occurrences(text, connector)

    passive_hits = len(re.findall(r"\b(is|are|was|were|been|being)\s+\w+(ed|en)\b", text, flags=re.IGNORECASE))

    mechanical = []
    if len(re.findall(r"  +", text)):
        mechanical.append("存在连续多个空格")
    if re.search(r"\s+[,.;:!?]", text):
        mechanical.append("标点前有空格")
    if re.search(r"[a-z][,.;:!?][A-Za-z]", text):
        mechanical.append("标点后缺空格")
    if re.search(r"\bi\b", text):
        mechanical.append("小写独立 i（应为 I）")
    if re.search(r"\b(\w+)\s+\1\b", text, flags=re.IGNORECASE):
        mechanical.append("相邻重复词（如 the the）")

    evidence_hits = [m.group(0).strip() for m in EVIDENCE_RE.finditer(text)]
    example_hits = [m.group(0).strip() for m in EXAMPLE_RE.finditer(text)]
    causal_hits = [m.group(0).strip() for m in CAUSAL_RE.finditer(text)]
    hedge_hits = [m.group(0).strip().lower() for m in HEDGE_RE.finditer(text)]
    vague_hits = [m.group(0).strip().lower() for m in VAGUE_RE.finditer(text)]
    specificity = count_specificity(text)
    initial_connectors = count_sentence_initial_connectors(sentences)

    hollow_signals = []
    if not evidence_hits:
        hollow_signals.append("证据/数据标记 0 处")
    if specificity["total"] == 0:
        hollow_signals.append("全文无任何具体细节（数字、年份、专有名词）")
    if len(hedge_hits) >= 6:
        hollow_signals.append("模糊限制语 %d 处（may/can/could/likely…）" % len(hedge_hits))
    if not example_hits:
        hollow_signals.append("无举例标记（for example / such as）")

    relevance = analyse_prompt_relevance(prompt, text) if prompt else None
    minimum = 150 if task in ("1", "1gt") else 250
    longest = sorted(
        [{"index": i + 1, "words": n, "text": sentences[i][:160]} for i, n in enumerate(sentence_lengths)],
        key=lambda item: -item["words"],
    )[:5]

    link_ratio = round(link_total / len(sentences), 2) if sentences else 0.0
    max_single_link = 0
    max_single_link_device = ""
    for devices in link_hits.values():
        for entry in devices:
            if entry["count"] > max_single_link:
                max_single_link = entry["count"]
                max_single_link_device = entry["device"]

    return {
        "task": task,
        "word_count": word_count,
        "minimum_words": minimum,
        "meets_word_count": word_count >= minimum,
        "paragraph_count": len(paragraphs),
        "paragraph_word_counts": paragraph_word_counts,
        "sentence_count": len(sentence_lengths),
        "avg_sentence_words": round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0.0,
        "longest_sentences": longest,
        "long_sentence_count": len([n for n in sentence_lengths if n > 35]),
        "type_token_ratio": ttr,
        "content_type_token_ratio": content_ttr,
        "repeated_content_words": repeated,
        "linking_total": link_total,
        "linking_per_sentence": link_ratio,
        "linking_groups": link_hits,
        "max_single_linking_device": {"device": max_single_link_device, "count": max_single_link},
        "informal_words": informal_hits,
        "error_probes": probes,
        "subordinator_count": complexity_hits,
        "passive_voice_count": passive_hits,
        "mechanical_issues": mechanical,
        "evidence_markers": len(evidence_hits),
        "evidence_samples": evidence_hits[:5],
        "example_markers": len(example_hits),
        "example_samples": example_hits[:5],
        "causal_markers": len(causal_hits),
        "causal_samples": causal_hits[:5],
        "hedges": len(hedge_hits),
        "hedge_words": sorted(set(hedge_hits)),
        "vague_expressions": len(vague_hits),
        "vague_samples": sorted(set(vague_hits))[:8],
        "specificity": specificity,
        "sentence_initial_connectors": initial_connectors,
        "sentence_initial_connector_ratio": (
            round(initial_connectors / len(sentences), 2) if sentences else 0.0
        ),
        "hollow_signals": hollow_signals,
        "task1": analyse_task1(text, task) if task in ("1", "1gt") else None,
        "relevance": relevance,
        "contradictions": find_contradictions(task, relevance),
        "text": text,
    }


def render_markdown(data):
    out = []
    add = out.append
    add("# 客观预分析\n")
    add("> 这些是**可数的事实**，用于定位问题，**不构成分数**。\n")

    add("## 1. 规模\n")
    add("| 指标 | 数值 | 判定 |")
    add("|---|---|---|")
    add("| 词数 | %d | %s（要求 ≥%d） |" % (
        data["word_count"],
        "✅ 达标" if data["meets_word_count"] else "❌ **不足**",
        data["minimum_words"],
    ))
    add("| 段数 | %d | %s |" % (
        data["paragraph_count"],
        "✅" if data["paragraph_count"] >= 4 else "⚠️ 少于 4 段，检查分段",
    ))
    add("| 句数 | %d | — |" % data["sentence_count"])
    add("| 平均句长 | %.1f 词 | %s |" % (
        data["avg_sentence_words"],
        "✅" if 12 <= data["avg_sentence_words"] <= 24 else "⚠️ 偏短或偏长",
    ))
    add("| >35 词的长句 | %d | %s |" % (
        data["long_sentence_count"],
        "✅ 无" if data["long_sentence_count"] == 0 else "⚠️ 长句易失控出错",
    ))
    add("")

    if data["paragraph_word_counts"]:
        add("**段落词数分布**：" + " / ".join(str(n) for n in data["paragraph_word_counts"]))
        counts = data["paragraph_word_counts"]
        if len(counts) >= 2 and max(counts) > 0 and min(counts) / max(counts) < 0.4:
            add("\n⚠️ 段落严重失衡（最短段不足最长段的 40%），影响 CC。")
        add("")

    if data.get("contradictions"):
        add("## ⚠️ 输入自相矛盾\n")
        for item in data["contradictions"]:
            add("- " + item)
        add("")
        add("下面第 7 节的结论建立在错误的判据上，**不要使用**；请用正确的 `--task` 重跑。")
        add("")

    add("## 2. 词汇\n")
    add("- 类符/形符比 (TTR)：**%.3f**（词数越多该值天然越低，仅供参考）" % data["type_token_ratio"])
    add("- 实词丰富度：**%.3f**" % data["content_type_token_ratio"])
    if data["repeated_content_words"]:
        add("- 高频重复实词（≥4 次，未做同义替换的候选）：")
        add("")
        add("| 词 | 次数 |")
        add("|---|---|")
        for item in data["repeated_content_words"]:
            add("| %s | %d |" % (item["word"], item["count"]))
    else:
        add("- ✅ 无实词重复 ≥4 次")
    add("")

    add("## 3. 衔接手段\n")
    add("- 连接词总数：**%d**，每句 **%.2f** 个" % (data["linking_total"], data["linking_per_sentence"]))
    add("- **以连接词开头的句子：%d / %d = %.0f%%**（比总密度更能区分'机械堆砌'与'自然衔接'）" % (
        data["sentence_initial_connectors"],
        data["sentence_count"],
        data["sentence_initial_connector_ratio"] * 100,
    ))
    if data["sentence_initial_connector_ratio"] >= 0.5:
        add("  - ⚠️ **过半句子以连接词开头 = 机械堆砌**。官方标准把机械使用连接词判为 CC 6 的特征，不是加分项。")
    elif data["sentence_initial_connector_ratio"] >= 0.35:
        add("  - ⚠️ 接近半数，注意是否存在连接词依赖。")
    else:
        add("  - ✅ 比例正常，衔接主要靠逻辑而非连接词。")
    if data["max_single_linking_device"]["count"] >= 4:
        add("  - ⚠️ `%s` 出现 **%d** 次，属机械重复。" % (
            data["max_single_linking_device"]["device"],
            data["max_single_linking_device"]["count"],
        ))
    if data["linking_groups"]:
        add("")
        add("| 逻辑关系 | 使用的连接词 |")
        add("|---|---|")
        for group, devices in sorted(data["linking_groups"].items()):
            rendered = "、".join("`%s`×%d" % (d["device"], d["count"]) for d in devices)
            add("| %s | %s |" % (group, rendered))
    add("")
    add("- 从属结构标记（从句/状语连接）出现 **%d** 次 → 复杂句尝试的证据" % data["subordinator_count"])
    add("- 被动语态疑似 **%d** 处（Task 1 流程图应显著高于 0）" % data["passive_voice_count"])
    add("")

    add("## 4. 语域与机械问题\n")
    if data["informal_words"]:
        add("⚠️ 检测到口语化/低语域用词（学术文中应避免）：")
        add("")
        add("| 词 | 次数 |")
        add("|---|---|")
        for item in data["informal_words"]:
            add("| %s | %d |" % (item["item"], item["count"]))
    else:
        add("✅ 未检测到常见口语化用词")
    add("")
    if data["mechanical_issues"]:
        add("机械问题：" + "；".join(data["mechanical_issues"]))
    else:
        add("✅ 无机械格式问题")
    add("")

    add("## 5. 高频错误模式探测（启发式，需人工确认）\n")
    if data["error_probes"]:
        add("| 代码 | 问题 | 次数 | 样例 | 修改方向 |")
        add("|---|---|---|---|---|")
        for probe in data["error_probes"]:
            samples = "；".join("`%s`" % s.replace("|", "\\|") for s in probe["samples"])
            add("| %s | %s | %d | %s | %s |" % (
                probe["code"], probe["label"], probe["count"], samples, probe["note"],
            ))
        add("")
        add("> 这些是**正则启发式**，会有误报和漏报。必须回到原文逐条确认后再写入报告。")
    else:
        add("✅ 未命中内置错误模式（不代表无错，只代表没有命中高频清单）")
    add("")

    add("## 6. 最长句（逐一核查是否失控）\n")
    add("| # | 词数 | 句子 |")
    add("|---|---|---|")
    for item in data["longest_sentences"]:
        sentence = item["text"].replace("|", "\\|").replace("\n", " ")
        add("| %d | %d | %s |" % (item["index"], item["words"], sentence))
    add("")

    add("## 7. " + ("Task 1 专项检查（按子类型分支）" if data.get("task1") else
                    "论证支撑度（独立于语法：语法干净也可能论证空洞）") + "\n")
    if data.get("task1"):
        task1 = data["task1"]
        is_letter = task1["kind"] == "gt_letter"
        if is_letter:
            add("> General Training Task 1 是**书信**，不是数据摘要：没有 overview 要求，"
                "也没有数据要比较。此处只检查书信专属项。\n")
            add("| 检查项 | 结果 | 判定 |")
            add("|---|---|---|")
            add("| 观点/建议类表达 | %d | %s |" % (
                len(task1["opinion_hits"]),
                "✅" if not task1["opinion_hits"] else "⚠️ 书信中避免空泛表态，要落到具体诉求",
            ))
        else:
            add("> Task 1 Academic 是**数据摘要**任务，不是论证任务。此处刻意不统计"
                "\"证据标记 / 举例标记 / 因果标记\"——在 Academic Task 1 里数字就是任务本身，"
                "而\"没有举例、没有因果\"恰恰是正确的。\n")
            add("| 检查项 | 结果 | 判定 |")
            add("|---|---|---|")
            add("| 概述（overview） | %s | %s |" % (
                "已找到" if task1["has_overview"] else "**未找到**",
                "✅" if task1["has_overview"] else "❌ **TA 上限 5.0**",
            ))
            add("| 含数据的句子 | %d 句 | — |" % task1["data_sentences"])
            add("| 其中做了比较/分组 | %d 句 | %s |" % (
                task1["compared_sentences"],
                "✅" if task1["mechanical_ratio"] < 0.6 else "⚠️ 纯报数比例过高",
            ))
            add("| 纯报数比例 | %.0f%% | %s |" % (
                task1["mechanical_ratio"] * 100,
                "✅" if task1["mechanical_ratio"] < 0.6 else "⚠️ 倾向机械罗列",
            ))
            add("| 比较类表达总数 | %d | %s |" % (
                task1["comparison_markers"],
                "✅" if task1["comparison_markers"] >= 3 else "⚠️ 偏少，Task 1 要求 make comparisons",
            ))
            add("| 观点/建议类表达 | %d | %s |" % (
                len(task1["opinion_hits"]),
                "✅" if not task1["opinion_hits"] else "❌ Task 1 不应出现观点",
            ))
            add("| 原因解释类表达 | %d | %s |" % (
                len(task1["cause_hits"]),
                "✅" if not task1["cause_hits"] else "❌ Task 1 不应解释原因",
            ))
            add("| 时态 | %s | %s |" % (
                "混用" if task1["tense_mixing"] else "未检出混用",
                "✅" if not task1["tense_mixing"] else "❌ 过去时间段却用现在时",
            ))
        add("")
        if not is_letter and task1["overview_sentence"]:
            add("- 概述句：`%s`" % task1["overview_sentence"][:160])
        if not is_letter and task1["unmarked_overview"]:
            add("- 无标记但疑似概述的段落：`%s`" % task1["unmarked_overview"][:160])
        if task1["letter"]:
            letter = task1["letter"]
            add("")
            add("**General Training 书信检查**")
            add("")
            add("| 检查项 | 结果 | 判定 |")
            add("|---|---|---|")
            add("| 称呼 | %s | %s |" % ("有" if letter["has_greeting"] else "无",
                                       "✅" if letter["has_greeting"] else "❌"))
            add("| 结尾敬语 | %s | %s |" % ("有" if letter["has_farewell"] else "无",
                                          "✅" if letter["has_farewell"] else "❌"))
            add("| 称呼与敬语匹配 | %s | %s |" % (
                "匹配" if letter["closing_matches_greeting"] else "不匹配",
                "✅" if letter["closing_matches_greeting"] else "❌"))
        add("")
        if task1["findings"]:
            add("### ⚠️ 判定\n")
            for finding in task1["findings"]:
                add("- " + finding)
            add("")
            if is_letter:
                add("> **三个 bullet point 是否全覆盖**、语气是否始终一致——工具无法判断，"
                    "必须对照题干逐条人工确认。这是 GT 书信最致命的失分点。")
            else:
                add("> 图表数据是否读对、关键特征是否遗漏——工具无法判断，"
                    "必须对照图表人工确认。")
        else:
            if is_letter:
                add("✅ 未触发书信专项警报（称呼、敬语、匹配、语域均正常；"
                    "但 bullet 覆盖与语气一致性仍需人工确认）")
            else:
                add("✅ 未触发 Task 1 专项警报（overview、时态、无观点/原因均正常；"
                    "但数据是否读对仍需人工对照图表）")
        add("")
    else:
        add("| 指标 | 数值 | 判定 |")
        add("|---|---|---|")
        add("| 证据/数据标记（research / studies / data / survey / percentage） | %d | %s |" % (
            data["evidence_markers"],
            "✅" if data["evidence_markers"] >= 3 else "⚠️ 偏少",
        ))
        add("| 举例标记（for example / for instance / such as） | %d | %s |" % (
            data["example_markers"],
            "✅" if data["example_markers"] >= 1 else "⚠️ 无",
        ))
        add("| 因果解释标记（because / since / leads to / results in） | %d | %s |" % (
            data["causal_markers"],
            "✅" if data["causal_markers"] >= 3 else "⚠️ 偏少",
        ))
        add("| 模糊限制语（may / can / could / likely / usually …） | %d | %s |" % (
            data["hedges"],
            "✅" if data["hedges"] <= 5 else "⚠️ 偏多：无证据的模糊化是空洞，不是谨慎",
        ))
        add("| 具体细节（数字 / 年份 / 专有名词） | %d | %s |" % (
            data["specificity"]["total"],
            "✅" if data["specificity"]["total"] >= 2 else "❌ 为零：全文没有任何可核验的具体信息",
        ))
        add("| 空泛抽象表达（positive effect / important / a number of …） | %d | %s |" % (
            data["vague_expressions"],
            "⚠️ 偏多" if data["vague_expressions"] >= 6 else "✅",
        ))
        add("")
        if data["hedge_words"]:
            add("- 检出的模糊限制语：%s" % "、".join("`%s`" % w for w in data["hedge_words"]))
        if data["vague_samples"]:
            add("- 检出的空泛表达：%s" % "、".join("`%s`" % w for w in data["vague_samples"]))
        if data["evidence_samples"]:
            add("- 检出的证据标记：%s" % "、".join("`%s`" % w for w in data["evidence_samples"]))
        add("")

        error_probe_total = sum(probe["count"] for probe in data["error_probes"])
        if len(data["hollow_signals"]) >= 3:
            add("### ⚠️ 判定：论证支撑度不足\n")
            add("命中信号：%s" % "；".join(data["hollow_signals"]))
            add("")
            if error_probe_total == 0:
                add("**这是「语法干净但论证空洞」型作文**：错误探测零命中，但支撑标记缺失、"
                    "具体细节为零、模糊限制语偏多。全文的论点都停留在 *may/can* 层面的断言，"
                    "没有任何机制、例证或数据。")
                add("")
                add("**批改警示**：此类作文的 GRA 与 LR 往往明显高于 TR。不要因为语言干净就抬高总分——"
                    "四项必须独立判定，TR 该低就低。批改重心应完全放在论证上，语法只需确认无误。")
            else:
                add("论证支撑度不足，且同时存在语法错误（错误探测 %d 处命中），属复合型问题："
                    "两轴都要改，但 TR 的修复优先级高于语法。" % error_probe_total)
        else:
            add("✅ 论证支撑度未触发警报（仍需人工确认论点是否真的延展，指标只能排除最空洞的情况）")
            add("")
            add("> 本节的阈值为**少量样本校准**所得，用于触发人工复核而非下结论；"
                "触发不等于一定有问题，未触发也不等于一定没问题。")
            add("")
            add("> 本节的阈值为**少量样本校准**所得，用于触发人工复核而非下结论。")
        add("")

    relevance = data.get("relevance")
    if relevance is None:
        add("## 8. 题目相关度\n")
        add("⚠️ **未提供题目**，无法检查是否偏题（TR-OFF / TR-PART）。")
        add("")
        add("**偏题无法从作文本身看出来**——一篇跑题的作文往往语言干净、论证充分。")
        add("必须用 `--prompt <题目文件或题干>` 传入题目才能做这项检查，"
            "否则 TR / TA 不应评分。")
        add("")
        return "\n".join(out)

    add("## 8. 题目相关度（TR 的前置检查）\n")
    add("**识别到的题型**：" + "；".join(
        "%s（%s）" % (entry["type"], entry["label"]) for entry in relevance["task_types"]
    ))
    add("")
    add("**题型要求的写作动作**：")
    add("")
    add("| 题型 | 要求 | 是否出现 |")
    add("|---|---|---|")
    for component in relevance["components"]:
        add("| %s | %s | %s |" % (
            component["task"], component["label"], "✅" if component["present"] else "❌ **缺失**",
        ))
    add("")
    add("**题干关键词覆盖：%d / %d = %.0f%%**" % (
        len(relevance["prompt_keywords"]) - len(relevance["missing_keywords"]),
        len(relevance["prompt_keywords"]),
        relevance["coverage"] * 100,
    ))
    add("")
    if relevance["prompt_keywords"]:
        add("- 题干关键词：%s" % "、".join("`%s`" % w for w in relevance["prompt_keywords"]))
    if relevance["missing_keywords"]:
        add("- ❌ **题干中出现、全文完全未涉及**：%s" % "、".join(
            "`%s`" % w for w in relevance["missing_keywords"]
        ))
    add("")

    missing_component = [c for c in relevance["components"] if not c["present"]]
    coverage = relevance["coverage"]
    if relevance.get("suspect_prompt"):
        add("### ⚠️ 无法判定：传入的题目可疑\n")
        add(relevance["suspect_prompt"])
        add("")
        add("**本节的偏题结论不可用。** 请用 `--prompt` 传入题干原文后重新运行——"
            "错误的题目会产出错误的批改结论，比没有结论更危险。")
        add("")
        return "\n".join(out)
    if coverage < 0.4:
        add("### ⚠️ 判定：疑似偏题（TR-OFF）\n")
        add("题干关键词覆盖率仅 %.0f%%。**这些缺失词正是题目区别于相邻话题的标志**——"
            "全文不使用它们，通常意味着你回答的是另一个问题，而不是题目问的那一问。" % (coverage * 100))
        add("")
        add("**必须人工确认**：把题干拆成问题部分清单，逐条在作文里找对应段落。"
            "找不到的，就是漏答或偏题。注意：跑题的作文常常语言干净、论证充分，"
            "**不要因为它写得好就放过 TR**。")
    elif coverage < 0.55:
        add("### ⚠️ 提示：题干覆盖偏低（%.0f%%）\n" % (coverage * 100))
        add("缺失词较少但需确认：作文是否完整回应了题干的每一个问题部分，"
            "还是只回应了其中一个。")
    else:
        add("✅ 题干关键词覆盖良好，未见偏题信号（仍需人工核对问题部分是否逐条回应）")
    if missing_component:
        add("")
        add("❌ **题型要求的成分缺失**：" + "；".join(
            "%s（%s）" % (c["label"], c["task"]) for c in missing_component
        ))
        add("")
        add("缺失的成分不会因为语言好而免于扣分——例如漏给立场、漏给比较结论，"
            "是 TR 5–6 档位的直接特征。")
    add("")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="IELTS essay objective pre-analysis (does not score).")
    parser.add_argument("source", help="essay file path, or - for stdin")
    parser.add_argument("--task", default="2", choices=["1", "1gt", "2"],
                        help="1 = Academic Task 1 (150 words), 1gt = General Task 1 (150), 2 = Task 2 (250)")
    parser.add_argument("--out", help="write the Markdown report to this path")
    parser.add_argument("--prompt", help="the task prompt: a file path, or the prompt text itself. "
                                        "Required to check for off-topic responses (TR-OFF / TR-PART)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    args = parser.parse_args(argv)

    text = read_source(args.source)
    if not text.strip():
        parser.error("input is empty")

    prompt = None
    if args.prompt:
        candidate = args.prompt
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as handle:
                prompt = handle.read()
        else:
            prompt = candidate
        if not prompt.strip():
            parser.error("--prompt is empty")

    data = analyse(text, args.task, prompt)

    if args.json:
        payload = dict(data)
        payload.pop("text", None)
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        rendered = render_markdown(data)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        sys.stderr.write("wrote %s\n" % args.out)
    else:
        sys.stdout.write(rendered + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
