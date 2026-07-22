from __future__ import annotations
import asyncio
import json
from pathlib import Path
from tobmate_agents.factory import run_chapter
from tobmate_agents.common import ROOT, WORKSPACE, load_project_config

APPROVAL_DIR = WORKSPACE / "approved"
APPROVAL_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    cfg = load_project_config()
    report = []
    for chapter in cfg["target_chapters"]:
        code = chapter["code"]
        output = await run_chapter(code)
        approved_copy = APPROVAL_DIR / output.name
        approved_copy.write_text(output.read_text(encoding="utf-8"), encoding="utf-8")

        # Feed each completed chapter into the next chapter's context.
        source_copy = WORKSPACE / "source" / output.name
        source_copy.write_text(output.read_text(encoding="utf-8"), encoding="utf-8")

        report.append({
            "chapter": code,
            "title": chapter["title"],
            "output": str(output),
            "approved_copy": str(approved_copy),
            "status": "generated_pending_human_final_approval"
        })

    report_path = WORKSPACE / "reports" / "full_program_run.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report_path)

if __name__ == "__main__":
    asyncio.run(main())
