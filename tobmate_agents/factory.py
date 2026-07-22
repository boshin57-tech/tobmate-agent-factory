from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from agents import Agent, Runner

from tobmate_agents.common import ROOT, WORKSPACE, load_context, load_project_config, model_name

load_dotenv(ROOT / ".env")

def make_agent(name: str, instructions: str) -> Agent:
    return Agent(
        name=name,
        model=model_name(),
        instructions=instructions,
    )

def build_agents(context: str) -> dict[str, Agent]:
    base = f"""
You are working on the TOBMATE Blockchain Architecture.
Use the following binding project context.

{context}

Never violate the Master Constitution.
Write in Korean with precise English technical terms.
Return only the requested artifact.
"""

    planner = make_agent("Chief Planner", base + """
Create a detailed work plan for the assigned chapter.
Split the chapter into non-overlapping section batches.
For each batch provide:
- section range
- section titles
- dependencies
- required objects
- state machines
- invariants
- cross-reference candidates
Return valid JSON only.
""")

    writer = make_agent("Protocol Writer", base + """
Draft the assigned section batch as implementation-ready architecture.
Maintain exact numbering.
Avoid ceremonial repetition.
Include concrete objects, fields, states, transition rules, authorization,
failure handling, events, audit records, and invariants where relevant.
Return Markdown only.
""")

    reviewer = make_agent("Constitution Reviewer", base + """
Review a draft against the Master Constitution and style guide.
Find:
- ownership violations
- reserve violations
- numbering errors
- duplicate content
- undefined terms
- invalid cross-references
- missing failure states
- missing audit requirements
Return valid JSON with severity, location, issue, and correction.
""")

    editor = make_agent("Revision Editor", base + """
Revise the supplied draft using the supplied review.
Preserve valid content and numbering.
Resolve every critical and high-severity issue.
Return corrected Markdown only.
""")

    integrator = make_agent("Chief Integrator", base + """
Merge approved batches into one canonical chapter.
Remove duplicate headings and duplicated paragraphs.
Preserve all valid section numbers.
Add a concise chapter completion matrix.
Do not renumber sections unless explicitly instructed.
Return final Markdown only.
""")

    return {
        "planner": planner,
        "writer": writer,
        "reviewer": reviewer,
        "editor": editor,
        "integrator": integrator,
    }

async def run_agent(agent: Agent, prompt: str) -> str:
    result = await Runner.run(agent, prompt)
    return str(result.final_output)
def checkpoint_path(chapter: str, batch_name: str) -> Path:
    safe_batch_name = batch_name.replace("/", "_").replace(" ", "_")
    return WORKSPACE / "checkpoints" / f"{chapter}_{safe_batch_name}.json"


def save_batch_checkpoint(
    chapter: str,
    batch_name: str,
    approved_path: Path,
) -> None:
    path = checkpoint_path(chapter, batch_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "chapter": chapter,
        "batch": batch_name,
        "status": "completed",
        "approved_path": str(approved_path),
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

async def write_batch(agents: dict[str, Agent], chapter: dict[str, Any], batch: dict[str, Any]) -> Path:
    prompt = f"""
CHAPTER:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

BATCH:
{json.dumps(batch, ensure_ascii=False, indent=2)}

Draft this batch.
"""
    draft = await run_agent(agents["writer"], prompt)
    draft_path = WORKSPACE / "drafts" / f'{chapter["code"]}_{batch["section_start"]}_{batch["section_end"]}.md'
    draft_path.write_text(draft, encoding="utf-8")

    review_prompt = f"""
Review this draft.

CHAPTER:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

DRAFT:
{draft}
"""
    review = await run_agent(agents["reviewer"], review_prompt)
    review_path = WORKSPACE / "reviews" / f'{chapter["code"]}_{batch["section_start"]}_{batch["section_end"]}.json'
    review_path.write_text(review, encoding="utf-8")

    edit_prompt = f"""
Correct the draft using the review.

DRAFT:
{draft}

REVIEW:
{review}
"""
    corrected = await run_agent(agents["editor"], edit_prompt)
    corrected_path = WORKSPACE / "drafts" / f'{chapter["code"]}_{batch["section_start"]}_{batch["section_end"]}_approved.md'
    corrected_path.write_text(corrected, encoding="utf-8")
   
   
    batch_name = f'{batch["section_start"]}_{batch["section_end"]}'

    save_batch_checkpoint(
        chapter["code"],
        batch_name,
        corrected_path,
    )
   

    return corrected_path

async def run_chapter(chapter_code: str) -> Path:
    cfg = load_project_config()
    chapter = next(c for c in cfg["target_chapters"] if c["code"] == chapter_code)
    context = load_context()
    agents = build_agents(context)

    plan_prompt = f"""
Plan this chapter:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

Use batches of approximately 10 sections.
The first section must define purpose and scope.
The final batch must contain completion invariants and transition to the next chapter.
Return a JSON object with a "batches" array.
Each batch must include section_start, section_end, title, topics, dependencies.
"""
    raw_plan = await run_agent(agents["planner"], plan_prompt)
    plan_path = WORKSPACE / "final" / f"{chapter_code}_plan.json"
    plan_path.write_text(raw_plan, encoding="utf-8")

    try:
        plan = json.loads(raw_plan)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Planner did not return valid JSON. See {plan_path}") from e

    max_parallel = int(__import__("os").getenv("MAX_PARALLEL_AGENTS", "6"))
    semaphore = asyncio.Semaphore(max_parallel)

    async def guarded(batch):
        async with semaphore:
            return await write_batch(agents, chapter, batch)

    approved_paths = await asyncio.gather(*(guarded(b) for b in plan["batches"]))
    merged_input = "\n\n".join(p.read_text(encoding="utf-8") for p in approved_paths)

    final_prompt = f"""
Merge the following approved batches into the canonical Chapter {chapter_code}.

CHAPTER METADATA:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

APPROVED BATCHES:
{merged_input}
"""
    final = await run_agent(agents["integrator"], final_prompt)
    final_path = WORKSPACE / "final" / f"{chapter_code}_{chapter['title'].replace(' ', '_')}.md"
    final_path.write_text(final, encoding="utf-8")
    return final_path

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", default="3O")
    args = parser.parse_args()
    path = asyncio.run(run_chapter(args.chapter))
    print(f"Created: {path}")
