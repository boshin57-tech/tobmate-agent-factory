from pathlib import Path
import subprocess

from af_core.repository.analyzer import RepositoryAnalyzer


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
    (path / "sample.py").write_text(
        "def value():\n    return 1\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def test_analyzer_detects_clean_repository(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    result = RepositoryAnalyzer().analyze(repo)

    assert result.repository_path == str(repo.resolve())
    assert result.head_commit
    assert result.tracked_file_count == 2
    assert "Python" in result.languages
    assert "pytest" in result.test_commands
    assert result.dirty is False


def test_analyzer_detects_dirty_repository(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")

    (repo / "sample.py").write_text(
        "def value():\n    return 2\n",
        encoding="utf-8",
    )

    result = RepositoryAnalyzer().analyze(repo)

    assert result.dirty is True
    assert any("sample.py" in item for item in result.dirty_files)
    assert result.risks
