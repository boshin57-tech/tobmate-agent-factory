from pathlib import Path
import subprocess

from af_core.repository.analyzer import RepositoryAnalyzer
from af_core.repository.context_builder import ContextBuilder


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.name", "AF Test")
    git(path, "config", "user.email", "af@example.com")

    (path / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="0.1.0"\n',
        encoding="utf-8",
    )
    (path / "planner.py").write_text(
        "def build_plan():\n    return []\n",
        encoding="utf-8",
    )

    tests = path / "tests"
    tests.mkdir()
    (tests / "test_planner.py").write_text(
        "def test_plan():\n    assert True\n",
        encoding="utf-8",
    )

    ignored = path / ".venv"
    ignored.mkdir()
    (ignored / "secret.py").write_text(
        "TOKEN = 'do-not-read'\n",
        encoding="utf-8",
    )

    git(path, "add", "pyproject.toml", "planner.py", "tests")
    git(path, "commit", "-m", "initial")
    return path


def test_context_builder_selects_relevant_files(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    analysis = RepositoryAnalyzer().analyze(repo)

    package = ContextBuilder().build(
        analysis=analysis,
        objective="Implement planner tests",
        constraints=["Do not overwrite existing changes"],
    )

    paths = {
        item.path
        for item in package.relevant_files
    }

    assert "planner.py" in paths
    assert "tests/test_planner.py" in paths
    assert "pyproject.toml" in paths
    assert all(".venv" not in path for path in paths)
    assert package.total_bytes > 0
    assert package.constraints == [
        "Do not overwrite existing changes"
    ]


def test_context_builder_respects_size_limit(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    large = repo / "large_planner.py"
    large.write_text("x" * 500, encoding="utf-8")

    analysis = RepositoryAnalyzer().analyze(repo)

    package = ContextBuilder(
        max_file_bytes=100,
        max_total_bytes=1000,
    ).build(
        analysis=analysis,
        objective="planner",
        explicit_files=["large_planner.py"],
    )

    assert "large_planner.py" in package.omitted_files
