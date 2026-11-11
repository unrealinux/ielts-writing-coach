#!/usr/bin/env python3
"""Build the WorkBuddy skill package: a zip with one top-level skill folder.

WorkBuddy's market reads a different frontmatter shape than a Claude-style skill
(display_name / description_zh / examples_zh / top-level version / author), so this
script generates that SKILL.md from the repo one instead of keeping a second copy.
`metadata.version` stays the only source of truth.

Usage:
    python3 scripts/build_workbuddy.py              # author = xieyingfei (see LICENSE)
    python3 scripts/build_workbuddy.py --author "某某公司"

Output: dist/ielts-writing-coach-workbuddy-v<version>.zip
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = "ielts-writing-coach"
DIST = os.path.join(ROOT, "dist")

# Market copy. Keep the one-liner short: the detail page has separate long fields.
# shortcut: hand-written twice (zh/en), revisit only if the market ships a 素材 generator
MARKET = {
    "display_name": "雅思写作批改",
    "display_name_en": "IELTS Writing Coach",
    "description": "雅思写作批改：按四项评分标准逐句举证给分档，输出错误模式、定向改写与可分享报告（触发：雅思作文批改/雅思大作文/雅思小作文/作文估分/IELTS essay feedback）",
    "description_zh": "贴出题目与作文，得到 Task Achievement/Response、Coherence & Cohesion、Lexical Resource、Grammatical Range & Accuracy 四项各自的档位区间与证据、逐句错误清单与错误模式、句子级 before→after 改写，以及一份可分享的 Markdown 报告（可选带批注的 .docx）。只读本地文件，不代写整篇，报告标明「预估分，非官方成绩」。",
    "description_en": "Paste an IELTS Task 1 or Task 2 prompt and essay to get a criterion-by-criterion band range backed by sentence-level evidence, an error-pattern breakdown, targeted before/after rewrites, and a shareable Markdown report (or an annotated .docx).",
    "examples_zh": [
        "帮我批改这篇雅思大作文，目标是 7 分",
        "这篇 Task 1 图表作文能到几分？哪里最丢分",
        "把这几次批改的分数整理成趋势，告诉我下一步练什么",
    ],
    "examples_en": [
        "Grade this IELTS Task 2 essay — I'm aiming for band 7",
        "What band is this Task 1 report, and where am I losing marks?",
        "Show my band trend across the last five corrections and what to practise next",
    ],
}

# Repo-only tooling: needs README/USAGE/evals, or builds this zip, so it does not belong in it.
SKIP_SCRIPTS = {"selfcheck.py", "check_stdlib_only.py", "build_workbuddy.py"}
COPY_DIRS = ["references", "templates", "scripts", "examples"]
COPY_FILES = ["LICENSE", "NOTICE.md"]
REQUIRED_FIELDS = [
    "name", "display_name", "display_name_en", "description",
    "description_zh", "description_en", "version", "author",
]


def split_skill():
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as handle:
        raw = handle.read()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        sys.exit("SKILL.md: no YAML frontmatter block")
    return match.group(2)


def declared_version(frontmatter):
    match = re.search(r'^\s+version:\s*"([^"]+)"', frontmatter, re.MULTILINE)
    if not match:
        sys.exit("SKILL.md: metadata.version missing")
    return match.group(1)


def quote(value):
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_frontmatter(version, author):
    lines = ["---", "name: %s" % SKILL]
    for key in ("display_name", "display_name_en", "description",
                "description_zh", "description_en"):
        lines.append("%s: %s" % (key, quote(MARKET[key])))
    for key in ("examples_zh", "examples_en"):
        lines.append("%s:" % key)
        lines.extend("- %s" % quote(item) for item in MARKET[key])
    lines.append("version: %s" % quote(version))
    lines.append("author: %s" % quote(author))
    lines.append("---")
    return "\n".join(lines) + "\n"


def stage(frontmatter, body):
    """Copy the runtime parts of the skill to a temp dir; return (root, package_root)."""
    root = tempfile.mkdtemp(prefix="workbuddy-")
    target = os.path.join(root, SKILL)
    os.makedirs(target)
    with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write(frontmatter + "\n" + body)
    for name in COPY_DIRS:
        source = os.path.join(ROOT, name)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(target, name),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    for name in COPY_FILES:
        source = os.path.join(ROOT, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(target, name))
    for name in SKIP_SCRIPTS:
        path = os.path.join(target, "scripts", name)
        if os.path.exists(path):
            os.remove(path)
    return root, target


def zip_package(target, version):
    os.makedirs(DIST, exist_ok=True)
    path = os.path.join(DIST, "%s-workbuddy-v%s.zip" % (SKILL, version))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, _, files in os.walk(target):
            for name in sorted(files):
                full = os.path.join(folder, name)
                archive.write(full, os.path.relpath(full, os.path.dirname(target)))
    return path


def verify(path, version):
    """Assert the package is uploadable: one root folder, parsable frontmatter, nothing dangling."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        roots = {name.split("/")[0] for name in names}
        assert roots == {SKILL}, "zip must contain exactly one root folder, got %s" % roots
        text = archive.read(SKILL + "/SKILL.md").decode("utf-8")
    front = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert front, "packaged SKILL.md has no frontmatter"
    for field in REQUIRED_FIELDS:
        assert re.search(r"^%s:\s*\S" % field, front.group(1), re.MULTILINE), \
            "packaged frontmatter missing %s (WorkBuddy rejects the zip)" % field
    assert re.search(r'^version:\s*"%s"' % re.escape(version), front.group(1), re.MULTILINE), \
        "packaged version drifted from metadata.version"
    referenced = set(re.findall(r"(?:references|templates|scripts)/[A-Za-z0-9_.-]+\.(?:md|py)",
                                text))
    missing = sorted(item for item in referenced if SKILL + "/" + item not in names)
    assert not missing, "SKILL.md points at files the package does not ship: %s" % missing
    return len(names), len(referenced)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--author", default="xieyingfei",
                        help="must match the certified 入驻 subject, or review fails")
    args = parser.parse_args()

    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as handle:
        version = declared_version(handle.read())
    root, target = stage(build_frontmatter(version, args.author), split_skill())
    try:
        path = zip_package(target, version)
        files, referenced = verify(path, version)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("%s\n  version %s | %d files | %d referenced resources | %d KB"
          % (path, version, files, referenced, os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main()
