"""Conservative, read-only gate for public repository contents.

Not proof of anonymity: manual release review remains mandatory.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".gitignore", ".gitattributes", ".csv", ".html", ".css", ".js"}
ALLOW_CSV = ROOT / "fixtures" / "synthetic"
BLOCK_EXT = {".xlsx", ".xls", ".xlsm", ".xlsb", ".pdf", ".docx", ".doc", ".json", ".xml",
             ".zip", ".7z", ".rar", ".png", ".jpg", ".jpeg", ".db", ".sqlite", ".pem",
             ".pfx", ".key"}
REGEXES = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "PAN": re.compile(r"(?<![A-Z])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z])"),
    "GSTIN": re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b"),
    "CIN": re.compile(r"\b[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b"),
    "UDIN": re.compile(r"\b[0-9]{8}[A-Z0-9]{10}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def scan() -> list[str]:
    violations = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(ROOT)
        if len(p.read_bytes()) > 150_000:
            violations.append(f"{rel}: too large for a reviewed public source file")
        if p.suffix.lower() in BLOCK_EXT:
            violations.append(f"{rel}: binary/data file not approved for public repo")
            continue
        if p.suffix.lower() == ".csv" and p.parent != ALLOW_CSV:
            violations.append(f"{rel}: CSV outside synthetic fixtures")
            continue
        if p.suffix.lower() not in SUFFIXES and p.name not in (".gitignore", ".gitattributes"):
            violations.append(f"{rel}: unrecognised file type")
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except UnicodeError:
            violations.append(f"{rel}: non-text content")
            continue
        for kind, rx in REGEXES.items():
            if rx.search(body):
                violations.append(f"{rel}: potential {kind} detected")
    return violations


if __name__ == "__main__":
    problems = scan()
    for item in problems:
        print("BLOCK:", item)
    print("PUBLIC_GATE:", "PASS (manual review still required)" if not problems else "FAIL")
    sys.exit(bool(problems))
