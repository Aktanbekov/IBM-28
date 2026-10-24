"""Refresh the auto-generated sections of README.md.

Runs in CI after every push to main (see .github/workflows/readme.yml), and can be run locally:
    python scripts/update_readme.py

It only rewrites text between <!-- AUTO:<NAME>:START --> and <!-- AUTO:<NAME>:END --> markers.
Output depends only on the repo state, so re-running it without new commits changes nothing.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def run(*cmd: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def git(*args: str) -> str:
    return run("git", *args)[1]


def test_summary() -> str:
    code, out = run(sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider")
    last = out.splitlines()[-1] if out else "no output"
    summary = re.sub(r"\s+in\s+[\d.]+s.*$", "", last.strip("= "))  # drop timing so output is stable
    return f"{'passing' if code == 0 else 'FAILING'} ({summary})"


def status_section() -> str:
    sha = git("log", "-1", "--format=%h")
    date = git("log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M %Z")
    authors = git("log", "--format=%an").splitlines()
    contributors = ", ".join(sorted(set(a for a in authors if a and "[bot]" not in a)))
    commits = len([line for line in git("log", "--format=%h").splitlines() if line])
    return "\n".join([
        "| | |",
        "|---|---|",
        f"| Last updated | {date} (commit `{sha}`) |",
        f"| Tests | {test_summary()} |",
        f"| Commits | {commits} |",
        f"| Contributors | {contributors} |",
    ])


def changelog_section(limit: int = 15) -> str:
    log = git("log", f"-{limit}", "--no-merges", "--format=%ad\t%an\t%s", "--date=short")
    rows = []
    for line in log.splitlines():
        date, author, subject = line.split("\t", 2)
        if "auto-update README" in subject:
            continue
        rows.append(f"| {date} | {author} | {subject.replace('|', '/')} |")
    return "\n".join(["## Recent changes", "", "| Date | Author | Change |", "|---|---|---|", *rows])


def replace_section(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- AUTO:{name}:START -->)(.*?)(<!-- AUTO:{name}:END -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"README.md is missing the AUTO:{name} markers")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text)


def main() -> None:
    text = README.read_text()
    text = replace_section(text, "STATUS", status_section())
    text = replace_section(text, "CHANGELOG", changelog_section())
    README.write_text(text)
    print("README.md auto sections refreshed")


if __name__ == "__main__":
    main()
