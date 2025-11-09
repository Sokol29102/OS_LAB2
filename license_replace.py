#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Iterable


@dataclass(frozen=True)
class Header:
    raw: str   # full comment as in file
    body: str  # inner text without //, /* */, leading '*'
    style: str # "line" or "block"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def c_files(root: Path, recursive: bool) -> Iterable[Path]:
    return (p for p in (root.rglob("*.c") if recursive else root.glob("*.c")) if p.is_file())


def extract_header(src: str) -> Optional[Header]:
    i, n = 0, len(src)
    if src.startswith("\ufeff"):
        i += 1
    while i < n and src[i] in " \t\r\n":
        i += 1
    if i >= n:
        return None

    # // ... style
    if src.startswith("//", i):
        start = i
        body_lines, j = [], i
        while j < n and src.startswith("//", j):
            end = src.find("\n", j)
            if end == -1:
                line = src[j:]
                j = n
            else:
                line = src[j:end]
                j = end + 1
            body_lines.append(line[2:].lstrip())
        raw = src[start:j]
        body = "\n".join(body_lines).rstrip("\n")
        return Header(raw, body, "line")

    # /* ... */ style
    if src.startswith("/*", i):
        start = i
        end = src.find("*/", i + 2)
        if end == -1:
            return None
        end += 2
        raw = src[start:end]
        inner = raw[2:-2]
        lines = inner.splitlines()
        if lines and not lines[0].strip():
            lines = lines[1:]
        cleaned = []
        for ln in lines:
            s = ln.lstrip()
            if s.startswith("*"):
                s = s[1:].lstrip()
            cleaned.append(s)
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        body = "\n".join(cleaned).rstrip("\n")
        return Header(raw, body, "block")

    return None


def norm(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[=*#\-_/\\]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def format_body(body: str, style: str) -> str:
    lines = body.splitlines() or [body]
    if style == "line":
        return "\n".join("// " + ln if ln.strip() else "//" for ln in lines) + "\n"
    if style == "block":
        out = ["/*"]
        for ln in lines:
            out.append(" * " + ln if ln.strip() else " *")
        out.append(" */\n")
        return "\n".join(out)
    raise ValueError(style)


def replace_header(src: str, new_header: str) -> Tuple[str, bool]:
    h = extract_header(src)
    if not h:
        return new_header + src, True
    start = src.find(h.raw)
    end = start + len(h.raw)
    return src[:start] + new_header + src[end:].lstrip("\n"), True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Replace license headers in .c files using exemplar headers."
    )
    p.add_argument("--dir", required=True, type=Path, help="Directory with .c files")
    p.add_argument("--source-exemplar", required=True, type=Path,
                   help="File with OLD license header")
    p.add_argument("--target-exemplar", required=True, type=Path,
                   help="File with NEW license header")
    p.add_argument("--recursive", action="store_true",
                   help="Recurse into subdirectories")
    p.add_argument("--threshold", type=float, default=0.75,
                   help="Similarity threshold [0..1] (default: 0.75)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dir.is_dir():
        print(f"Not a directory: {args.dir}")
        return 2

    src_h = extract_header(read(args.source_exemplar))
    tgt_h = extract_header(read(args.target_exemplar))
    if not src_h:
        print("Source exemplar has no leading comment header.")
        return 2
    if not tgt_h:
        print("Target exemplar has no leading comment header.")
        return 2

    scanned = changed = 0
    for path in c_files(args.dir, args.recursive):
        scanned += 1
        text = read(path)
        fh = extract_header(text)
        if not fh:
            continue
        if sim(fh.body, src_h.body) < args.threshold:
            continue

        new_header = format_body(tgt_h.body, fh.style)
        new_text, _ = replace_header(text, new_header)
        write(path, new_text)
        changed += 1
        print(f"Updated: {path}")

    print(f"Done. Scanned={scanned}, Changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

