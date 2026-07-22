from __future__ import annotations
from pathlib import Path
import os
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def load_project_config() -> dict:
    with open(ROOT / "config" / "project.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_context() -> str:
    constitution = read_text(ROOT / "prompts" / "master_constitution.md")
    style = read_text(ROOT / "prompts" / "style_guide.md")
    sources = []
    for p in sorted((WORKSPACE / "source").glob("**/*")):
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}:
            sources.append(f"\n# SOURCE: {p.name}\n{read_text(p)}")
    return constitution + "\n\n" + style + "\n\n" + "\n".join(sources)

def model_name() -> str:
    return os.getenv("TOBMATE_MODEL", "gpt-5.2")
