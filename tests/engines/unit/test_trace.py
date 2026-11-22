from pathlib import Path

import pytest

from aiautonomy.engines import trace

# Tag patterns are assembled at runtime so that `aia trace` does not read this file's
# fixtures as tags of the real repository.
MARK = "pytest.mark." + "req"
CODE_TAG = "RE" + "Q:"
TEST_TAG = "@" + "req"


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    write(
        tmp_path,
        "specs/R1.md",
        "# Spec\n\n### AAA-01 — First thing\n\nText.\n\n### BBB-02 — Second | piped\n\n"
        "### CCC-03 — Third\n\n### DDD-04 — Fourth\n\n## Not a requirement\n",
    )
    write(
        tmp_path,
        "aiautonomy/engines/mod.py",
        f'"""Module.\n\n{CODE_TAG} AAA-01, BBB-02\n"""\n\n\nclass Thing:\n'
        f'    """A thing. {CODE_TAG} AAA-01"""\n\n    def act(self) -> None:\n'
        f'        """{CODE_TAG} CCC-03"""\n\n\n# {CODE_TAG} DDD-04 (a comment, not a docstring)\n',
    )
    write(
        tmp_path,
        "tests/engines/test_mod.py",
        f'import pytest\n\npytestmark = {MARK}("BBB-02")\n\n\n@{MARK}("AAA-01", "CCC-03")\n'
        "def test_one() -> None:\n    pass\n",
    )
    write(tmp_path, "aiautonomy/interfaces/app.ts", f"// {CODE_TAG} DDD-04\nexport const x = 1;\n")
    write(tmp_path, "aiautonomy/interfaces/app.test.ts", f"it('{TEST_TAG} AAA-01', () => {{}});\n")
    write(
        tmp_path, "tests/interfaces/app.spec.ts", f"test('shell {TEST_TAG} DDD-04', () => {{}});\n"
    )
    write(tmp_path, "aiautonomy/interfaces/node_modules/dep/index.ts", f"// {CODE_TAG} ZZZ-99\n")
    return tmp_path


def test_requirements_come_from_spec_headings(mini_repo: Path) -> None:
    requirements = trace.parse_requirements((mini_repo / "specs/R1.md").read_text())
    assert requirements == {
        "AAA-01": "First thing",
        "BBB-02": "Second | piped",
        "CCC-03": "Third",
        "DDD-04": "Fourth",
    }


def test_tags_are_collected_from_all_four_sources(mini_repo: Path) -> None:
    report = trace.build_report(mini_repo)
    assert report.impl == {
        "AAA-01": ["aiautonomy/engines/mod.py", "aiautonomy/engines/mod.py::Thing"],
        "BBB-02": ["aiautonomy/engines/mod.py"],
        "CCC-03": ["aiautonomy/engines/mod.py::Thing.act"],
        "DDD-04": ["aiautonomy/interfaces/app.ts"],
    }
    assert report.tests == {
        "BBB-02": ["tests/engines/test_mod.py"],
        "AAA-01": ["tests/engines/test_mod.py::test_one", "aiautonomy/interfaces/app.test.ts"],
        "CCC-03": ["tests/engines/test_mod.py::test_one"],
        "DDD-04": ["tests/interfaces/app.spec.ts"],
    }
    assert report.unknown == []
    assert {req: report.status(req) for req in report.requirements} == dict.fromkeys(
        report.requirements, "covered"
    )


def test_markdown_report_and_exit_codes(mini_repo: Path, tmp_path: Path) -> None:
    output = tmp_path / "out" / "traceability.md"
    assert trace.main(["--root", str(mini_repo), "--output", str(output), "--strict"]) == 0
    text = output.read_text()
    assert "| AAA-01 | First thing |" in text
    assert "Second \\| piped" in text
    write(
        mini_repo, "specs/R1.md", (mini_repo / "specs/R1.md").read_text() + "\n### EEE-05 — Gap\n"
    )
    assert trace.main(["--root", str(mini_repo), "--output", str(output)]) == 0
    assert trace.main(["--root", str(mini_repo), "--output", str(output), "--strict"]) == 1
    assert "| EEE-05 | Gap | — | — | missing |" in output.read_text()


def test_an_unknown_id_fails(mini_repo: Path, tmp_path: Path) -> None:
    write(mini_repo, "aiautonomy/interfaces/bad.ts", f"// {CODE_TAG} ZZZ-99\n")
    output = tmp_path / "traceability.md"
    assert trace.main(["--root", str(mini_repo), "--output", str(output)]) == 1


def test_this_repository_has_no_unknown_tags(tmp_path: Path) -> None:
    output = tmp_path / "traceability.md"
    assert trace.main(["--output", str(output)]) == 0
    rows = [
        line
        for line in output.read_text().splitlines()
        if line.startswith("| ") and "-" in line[2:9]
    ]
    assert len(rows) == 108
