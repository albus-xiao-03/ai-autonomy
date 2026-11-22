"""`aia trace`: requirement traceability report (docs/engine-plan.md §6).

Requirement IDs come from the `### XXX-NN — Title` headings of `SPEC.md (Part B)`. Tags:

- engine code (`aiautonomy/engines`): docstring `REQ: ID[, ID…]`
- engine tests (`tests/engines`): `@pytest.mark.req("ID", …)`
- frontend code (`aiautonomy/interfaces`): comment `// REQ: ID[, ID…]`
- frontend tests (`tests/interfaces`, `*.test.ts(x)` / `*.spec.ts(x)`): `@req ID[, ID…]`

Writes `docs/traceability.md`. Exit 1 when a tag names an unknown ID; with `--strict`, also
when a requirement lacks an implementation or a test reference.
"""

import argparse
import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from aiautonomy.engines.core.paths import repo_root

SPEC = Path("SPEC.md")
OUTPUT = Path("docs/traceability.md")
ENGINE_CODE = Path("aiautonomy/engines")
ENGINE_TESTS = Path("tests/engines")
FRONTEND_CODE = Path("aiautonomy/interfaces")
FRONTEND_TESTS = Path("tests/interfaces")
TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
SKIP_DIRS = frozenset({"node_modules", "dist", "__pycache__", ".venv"})
MAX_REFS = 8

_ID = r"[A-Z][A-Z0-9]*-\d+"
_ID_LIST = rf"{_ID}(?:\s*,\s*{_ID})*"
HEADING = re.compile(r"^### ([A-Z][A-Z0-9]*-\d+) — (.+?)\s*$", re.MULTILINE)
DOC_TAG = re.compile(rf"\bREQ:\s*({_ID_LIST})")
TEST_MARK = re.compile(r"pytest\.mark\.req\(([^)]*)\)")
QUOTED = re.compile(r"""["']([^"']*)["']""")
TS_CODE_TAG = re.compile(rf"//\s*REQ:\s*({_ID_LIST})")
TS_TEST_TAG = re.compile(rf"@req\s+({_ID_LIST})")
DEF_LINE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")


@dataclass(frozen=True, slots=True)
class Tag:
    req_id: str
    kind: str  # "impl" or "test"
    ref: str


@dataclass(slots=True)
class TraceReport:
    requirements: dict[str, str]
    impl: dict[str, list[str]] = field(default_factory=dict)
    tests: dict[str, list[str]] = field(default_factory=dict)
    unknown: list[Tag] = field(default_factory=list)

    def status(self, req_id: str) -> str:
        has_impl, has_test = bool(self.impl.get(req_id)), bool(self.tests.get(req_id))
        if has_impl and has_test:
            return "covered"
        if has_impl:
            return "implementation only"
        if has_test:
            return "tests only"
        return "missing"

    def counts(self) -> dict[str, int]:
        result = {"covered": 0, "implementation only": 0, "tests only": 0, "missing": 0}
        for req_id in self.requirements:
            result[self.status(req_id)] += 1
        return result


def split_ids(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_requirements(spec_text: str) -> dict[str, str]:
    """Requirement id → title, in specification order."""
    return {match[1]: match[2] for match in HEADING.finditer(spec_text)}


def _files(base: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.suffix in suffixes and path.is_file() and not SKIP_DIRS.intersection(path.parts):
            yield path


def _is_ts_test(path: Path) -> bool:
    return any(
        path.name.endswith(f".{kind}{suffix}")
        for kind in ("test", "spec")
        for suffix in TS_SUFFIXES
    )


def _docstring_tags(node: ast.AST, ref: str) -> list[Tag]:
    if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        return []
    doc = ast.get_docstring(node, clean=False)
    if not doc:
        return []
    return [
        Tag(req_id, "impl", ref)
        for match in DOC_TAG.finditer(doc)
        for req_id in split_ids(match[1])
    ]


def scan_engine_code(root: Path) -> list[Tag]:
    tags: list[Tag] = []
    for path in _files(root / ENGINE_CODE, (".py",)):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        tags.extend(_docstring_tags(tree, rel))

        def visit(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                    name = f"{prefix}{child.name}"
                    tags.extend(_docstring_tags(child, f"{rel}::{name}"))  # noqa: B023
                    visit(child, f"{name}.")

        visit(tree, "")
    return tags


def scan_engine_tests(root: Path) -> list[Tag]:
    tags: list[Tag] = []
    for path in _files(root / ENGINE_TESTS, (".py",)):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            for match in TEST_MARK.finditer(line):
                ref = rel
                if not line.lstrip().startswith("pytestmark"):
                    following = (DEF_LINE.match(later) for later in lines[index + 1 :])
                    name = next((found[1] for found in following if found), None)
                    ref = f"{rel}::{name}" if name else rel
                for value in QUOTED.findall(match[1]):
                    tags.extend(Tag(req_id, "test", ref) for req_id in split_ids(value))
    return tags


def scan_frontend(root: Path) -> list[Tag]:
    tags: list[Tag] = []
    for path in _files(root / FRONTEND_CODE, TS_SUFFIXES):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if _is_ts_test(path):
            tags.extend(
                Tag(req_id, "test", rel)
                for match in TS_TEST_TAG.finditer(text)
                for req_id in split_ids(match[1])
            )
        else:
            tags.extend(
                Tag(req_id, "impl", rel)
                for match in TS_CODE_TAG.finditer(text)
                for req_id in split_ids(match[1])
            )
    for path in _files(root / FRONTEND_TESTS, TS_SUFFIXES):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        tags.extend(
            Tag(req_id, "test", rel)
            for match in TS_TEST_TAG.finditer(text)
            for req_id in split_ids(match[1])
        )
    return tags


def build_report(root: Path) -> TraceReport:
    requirements = parse_requirements((root / SPEC).read_text(encoding="utf-8"))
    report = TraceReport(requirements=requirements)
    for tag in [*scan_engine_code(root), *scan_engine_tests(root), *scan_frontend(root)]:
        if tag.req_id not in requirements:
            report.unknown.append(tag)
            continue
        refs = (report.impl if tag.kind == "impl" else report.tests).setdefault(tag.req_id, [])
        if tag.ref not in refs:
            refs.append(tag.ref)
    return report


def _cell(refs: list[str]) -> str:
    if not refs:
        return "—"
    shown = [f"`{ref}`" for ref in sorted(refs)[:MAX_REFS]]
    if len(refs) > MAX_REFS:
        shown.append(f"(+{len(refs) - MAX_REFS} more)")
    return "<br>".join(shown)


def render_markdown(report: TraceReport) -> str:
    counts = report.counts()
    lines = [
        "# Requirement traceability",
        "",
        "Generated by `aia trace` from the requirement headings in `SPEC.md` (Part B) and the tags",
        "in the code and tests (docs/engine-plan.md §6). Do not edit by hand.",
        "",
        "| Requirements | Covered | Implementation only | Tests only | Missing |",
        "|---:|---:|---:|---:|---:|",
        f"| {len(report.requirements)} | {counts['covered']} | {counts['implementation only']} "
        f"| {counts['tests only']} | {counts['missing']} |",
        "",
        "| ID | Title | Implementation | Tests | Status |",
        "|---|---|---|---|---|",
    ]
    for req_id, title in report.requirements.items():
        lines.append(
            f"| {req_id} | {title.replace('|', '\\|')} | {_cell(report.impl.get(req_id, []))} "
            f"| {_cell(report.tests.get(req_id, []))} | {report.status(req_id)} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aia trace", description=__doc__.splitlines()[0])
    add_arguments(parser)
    return run(parser.parse_args(argv))


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strict", action="store_true", help="fail on uncovered requirements")
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--output", type=Path, default=None, help="default: docs/traceability.md")


def run(args: argparse.Namespace) -> int:
    root: Path = args.root or repo_root()
    report = build_report(root)
    output: Path = args.output or root / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(report), encoding="utf-8")
    counts = report.counts()
    print(
        f"traceability: {len(report.requirements)} requirements; {counts['covered']} covered, "
        f"{counts['implementation only']} implementation only, {counts['tests only']} tests "
        f"only, {counts['missing']} missing; wrote {output}"
    )
    failed = False
    for tag in report.unknown:
        print(f"error: unknown requirement {tag.req_id} tagged at {tag.ref}", file=sys.stderr)
        failed = True
    if not report.requirements:
        print(f"error: no requirement headings found in {root / SPEC}", file=sys.stderr)
        failed = True
    if args.strict:
        for req_id in report.requirements:
            status = report.status(req_id)
            if status != "covered":
                print(f"error: {req_id} is {status}", file=sys.stderr)
                failed = True
    return 1 if failed else 0
