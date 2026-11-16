#!/usr/bin/env python3
"""Repository hygiene checks for tg-companion-audit.

Five checks, no dependencies, Windows and POSIX:

  links     broken relative links in *.md (inline, image, HTML href/src,
            reference definitions); anchors and external schemes are skipped
  paths     drive-letter absolute paths in tracked text files
  assets    .glb / .bin artifacts anywhere in the tree
  tables    Markdown tables whose rows do not match the header column count
  tone      clickbait words in Markdown headings
  identity  leftover placeholder author or mailbox in *.md

Anchored on what would actually be published: paths matched by ``.gitignore``
are excluded from the text checks, and a binary artifact that is present but
ignored is reported as a warning rather than a failure.

A line containing ``check_repo:ignore`` is skipped by the line-based checks.
A file whose first five lines contain ``check_repo:ignore-file`` is skipped
entirely (useful for a document that must show a local path on purpose).

Usage:
    python scripts/check_repo.py [--root PATH] [--verbose]

Exit code 0 when clean, 1 when any finding is reported.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "evidence",
    "dist",
    "build",
}

TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".py",
    ".svg",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".ps1",
    ".bat",
    ".mm",
    ".m",
    ".h",
    ".hpp",
    ".cpp",
    ".swift",
    ".html",
    ".css",
}

TEXT_NAMES = {"LICENSE", "NOTICE", "CODEOWNERS", ".gitignore", ".gitattributes", "Makefile"}

MARKDOWN_SUFFIXES = {".md", ".markdown"}

FORBIDDEN_ASSETS = {".glb", ".bin"}

FENCE_RE = re.compile(r"^\s*(```|~~~)")
INDENT_CODE_RE = re.compile(r"^(?:\t| {4,})\S")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
INLINE_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)")
HTML_LINK_RE = re.compile(r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(\S+)")
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
SEPARATOR_CELL_RE = re.compile(r"^:?-{1,}:?$")

# A single letter, a colon, then a path separator. The lookbehind keeps
# URL schemes such as https, git, file out of the match.
WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z]:[\\/]")

BANNED_HEADING_RE = re.compile(r"\b(0-day|zero-day|critical|rce|hack\w*)\b", re.IGNORECASE)

PLACEHOLDERS = (
    # split so this file does not itself look like a leaked address to a grep
    "contact@" + "example.com",
    "independent security research",
)

SKIPPED_SCHEMES = {
    "http",
    "https",
    "mailto",
    "ftp",
    "ftps",
    "ssh",
    "git",
    "tel",
    "tg",
    "data",
    "javascript",
    "irc",
    "xmpp",
}

Finding = tuple  # (category, path: Path, line: int, message: str)


# --------------------------------------------------------------------------
# tree walking
# --------------------------------------------------------------------------

def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        yield path


def is_text_file(path: Path) -> bool:
    if path.name in TEXT_NAMES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def read_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    return text.splitlines()


def ignored_line(line: str) -> bool:
    return "check_repo:ignore" in line


def ignored_file(lines: list[str]) -> bool:
    return any("check_repo:ignore-file" in line for line in lines[:5])


def strip_fences(lines: list[str]):
    """Yield (lineno, line, is_code) with fenced and indented code flagged."""
    fence = None
    for index, line in enumerate(lines, start=1):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            yield index, line, True
            continue
        if fence is not None:
            yield index, line, True
            continue
        yield index, line, bool(INDENT_CODE_RE.match(line))


def load_gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return []
    patterns: list[str] = []
    for line in read_lines(path):
        entry = line.strip()
        if not entry or entry.startswith("#") or entry.startswith("!"):
            continue
        patterns.append(entry.rstrip("/"))
    return patterns


def is_ignored(rel_posix: str, patterns: list[str]) -> bool:
    """Small subset of gitignore: name patterns, anchored paths, globs."""
    parts = rel_posix.split("/")
    for pattern in patterns:
        anchored = pattern.lstrip("/")
        if "/" in anchored:
            if rel_posix == anchored or rel_posix.startswith(anchored + "/"):
                return True
            if fnmatch.fnmatch(rel_posix, anchored):
                return True
        else:
            for part in parts:
                if fnmatch.fnmatch(part, anchored):
                    return True
    return False


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_links(root: Path, md_files: list[Path]):
    findings: list[Finding] = []
    for path in md_files:
        lines = read_lines(path)
        if ignored_file(lines):
            continue
        for lineno, line, in_fence in strip_fences(lines):
            if in_fence or ignored_line(line):
                continue
            targets = []
            for match in INLINE_LINK_RE.finditer(line):
                targets.append(match.group(1))
            for match in HTML_LINK_RE.finditer(line):
                targets.append(match.group(1))
            match = REF_DEF_RE.match(line)
            if match:
                targets.append(match.group(1))

            for raw in targets:
                target = raw.strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1].strip()
                if not target or target.startswith("#"):
                    continue
                if target.startswith("//"):
                    continue
                parsed = urllib.parse.urlparse(target)
                if parsed.scheme.lower() in SKIPPED_SCHEMES:
                    continue
                if parsed.scheme and len(parsed.scheme) > 1:
                    # unknown scheme, not a relative path
                    continue
                local = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0])
                if not local:
                    continue
                if local.startswith("/"):
                    candidate = root / local.lstrip("/")
                else:
                    candidate = path.parent / local
                try:
                    exists = candidate.exists()
                except OSError:
                    exists = False
                if not exists:
                    findings.append(
                        (
                            "links",
                            path,
                            lineno,
                            f"relative target does not exist: {target}",
                        )
                    )
    return findings


def check_windows_paths(root: Path, files: list[Path]):
    findings: list[Finding] = []
    for path in files:
        if not is_text_file(path):
            continue
        lines = read_lines(path)
        if ignored_file(lines):
            continue
        for lineno, line in enumerate(lines, start=1):
            if ignored_line(line):
                continue
            match = WINDOWS_PATH_RE.search(line)
            if match:
                excerpt = line.strip()
                if len(excerpt) > 100:
                    excerpt = excerpt[:97] + "..."
                findings.append(
                    (
                        "paths",
                        path,
                        lineno,
                        f"drive-letter path in text: {excerpt}",
                    )
                )
    return findings


def check_assets(files: list[Path]):
    findings: list[Finding] = []
    for path in files:
        if path.suffix.lower() in FORBIDDEN_ASSETS:
            findings.append(
                (
                    "assets",
                    path,
                    0,
                    f"binary model artifact present: {path.name}",
                )
            )
    return findings


def split_cells(row: str) -> list[str]:
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    if not stripped:
        return []
    return CELL_SPLIT_RE.split(stripped)


def check_tables(root: Path, md_files: list[Path]):
    findings: list[Finding] = []
    for path in md_files:
        lines = read_lines(path)
        if ignored_file(lines):
            continue
        rows = [(lineno, line) for lineno, line, in_fence in strip_fences(lines) if not in_fence]

        index = 0
        while index < len(rows):
            lineno, line = rows[index]
            if not line.lstrip().startswith("|"):
                index += 1
                continue

            block_start = index
            block = []
            while index < len(rows) and rows[index][1].lstrip().startswith("|"):
                block.append(rows[index])
                index += 1

            if len(block) < 2:
                continue

            header_no, header_line = block[0]
            if ignored_line(header_line):
                continue
            header_cells = split_cells(CODE_SPAN_RE.sub("x", header_line))
            expected = len(header_cells)
            if expected < 2:
                continue

            sep_no, sep_line = block[1]
            sep_cells = split_cells(CODE_SPAN_RE.sub("x", sep_line))
            looks_like_table = sep_cells and all(
                SEPARATOR_CELL_RE.match(cell.strip()) for cell in sep_cells if cell.strip()
            )
            if not looks_like_table:
                continue
            if len(sep_cells) != expected:
                findings.append(
                    (
                        "tables",
                        path,
                        sep_no,
                        f"separator has {len(sep_cells)} columns, header has {expected}",
                    )
                )

            for lineno, row in block[2:]:
                if ignored_line(row):
                    continue
                cells = split_cells(CODE_SPAN_RE.sub("x", row))
                if len(cells) != expected:
                    findings.append(
                        (
                            "tables",
                            path,
                            lineno,
                            f"{len(cells)} columns, header at line {header_no} has {expected}",
                        )
                    )
            _ = block_start
    return findings


def check_headings(root: Path, md_files: list[Path]):
    findings: list[Finding] = []
    for path in md_files:
        lines = read_lines(path)
        if ignored_file(lines):
            continue
        for lineno, line, in_fence in strip_fences(lines):
            if in_fence or ignored_line(line):
                continue
            match = HEADING_RE.match(line)
            if not match:
                continue
            text = match.group(2)
            hits = sorted({hit.group(0).lower() for hit in BANNED_HEADING_RE.finditer(text)})
            if hits:
                findings.append(
                    (
                        "tone",
                        path,
                        lineno,
                        "clickbait term(s) in heading: "
                        + ", ".join(f"'{hit}'" for hit in hits)
                        + f" -- {text.strip()}",
                    )
                )
    return findings


def check_identity(root: Path, md_files: list[Path]):
    findings: list[Finding] = []
    for path in md_files:
        lines = read_lines(path)
        if ignored_file(lines):
            continue
        for lineno, line in enumerate(lines, start=1):
            if ignored_line(line):
                continue
            lowered = line.lower()
            for placeholder in PLACEHOLDERS:
                if placeholder in lowered:
                    findings.append(
                        (
                            "identity",
                            path,
                            lineno,
                            f"placeholder identity still present: {placeholder}",
                        )
                    )
    return findings


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

CATEGORY_TITLES = {
    "links": "broken relative links",
    "paths": "absolute drive-letter paths",
    "assets": "binary model artifacts",
    "tables": "Markdown table column counts",
    "tone": "clickbait words in headings",
    "identity": "placeholder identity in *.md",
}

CATEGORY_ORDER = ["links", "paths", "assets", "tables", "tone", "identity"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Repository hygiene checks.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: parent of the scripts directory)",
    )
    parser.add_argument("--verbose", action="store_true", help="print scanned file counts")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}")
        return 2

    files = list(iter_files(root))
    patterns = load_gitignore(root)

    def rel_of(path: Path) -> str:
        return path.relative_to(root).as_posix()

    ignored_files = [p for p in files if is_ignored(rel_of(p), patterns)]
    published = [p for p in files if not is_ignored(rel_of(p), patterns)]
    md_files = [p for p in published if p.suffix.lower() in MARKDOWN_SUFFIXES]

    findings: list[Finding] = []
    findings += check_links(root, md_files)
    findings += check_windows_paths(root, published)
    findings += check_tables(root, md_files)
    findings += check_headings(root, md_files)
    findings += check_identity(root, md_files)

    artifact_findings = check_assets(files)
    warnings = [f for f in artifact_findings if is_ignored(rel_of(f[1]), patterns)]
    findings += [f for f in artifact_findings if not is_ignored(rel_of(f[1]), patterns)]

    print("=" * 66)
    print(f"check_repo.py :: {root.name}")
    print(
        f"scanned: {len(files)} files "
        f"({len(ignored_files)} gitignored), {len(md_files)} Markdown"
    )
    print("=" * 66)

    for category in CATEGORY_ORDER:
        bucket = [f for f in findings if f[0] == category]
        if not bucket:
            if args.verbose:
                print(f"[ok]   {CATEGORY_TITLES[category]}")
            continue
        print(f"[FAIL] {CATEGORY_TITLES[category]}: {len(bucket)}")
        for _, path, lineno, message in bucket:
            rel = path.relative_to(root).as_posix()
            where = f"{rel}:{lineno}" if lineno else rel
            print(f"       {where}  {message}")

    if warnings:
        print(f"[WARN] binary artifacts present but gitignored: {len(warnings)}")
        for _, path, _lineno, message in warnings:
            print(f"       {rel_of(path)}  {message} (not published)")

    if args.verbose:
        for category in CATEGORY_ORDER:
            bucket = [f for f in findings if f[0] == category]
            if bucket:
                print(f"[..]   {CATEGORY_TITLES[category]}: {len(bucket)} finding(s)")

    total = len(findings)
    print("-" * 66)
    if total == 0:
        print("problems: 0")
        return 0
    print(f"problems: {total}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
