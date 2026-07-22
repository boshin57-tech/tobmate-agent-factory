# TOBMATE Multi-Agent Factory

This repository turns the remaining TOBMATE Blockchain Architecture work into a repeatable multi-agent pipeline.

## Agent chain

1. Chief Planner
2. Parallel Protocol Writers
3. Constitution Reviewer
4. Revision Editor
5. Chief Integrator

The factory generates one chapter at a time while preserving the Master Constitution.

## 1. Install

Linux / macOS:

```bash
cd tobmate-agent-factory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
cd tobmate-agent-factory
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and add the API key.

## 2. Add the existing architecture

Export the completed Chapter 3N and related canonical material to Markdown or TXT and place it in:

```text
workspace/source/
```

At minimum, add:

```text
chapter_3n_complete.md
terminology.md
section_index.md
```

## 3. Run Chapter 3O

```bash
python run_factory.py --chapter 3O
```

Output:

```text
workspace/final/3O_Gold_Liquidity_Pool_Framework.md
```

Intermediate drafts and reviews are retained for audit.

## 4. Run later chapters

```bash
python run_factory.py --chapter 3P
python run_factory.py --chapter 3Q
python run_factory.py --chapter 3R
```

Do not run all chapters simultaneously until Chapter 3O has been reviewed and its canonical output added back to `workspace/source/`.

## Safe operating sequence

```text
Generate chapter
→ human spot-check
→ approve canonical chapter
→ copy approved chapter into workspace/source
→ generate next chapter
```

This prevents downstream agents from building on an unapproved draft.

## Recommended first production settings

```env
MAX_PARALLEL_AGENTS=4
```

Increase to 6 or 8 only after checking cost, rate limits, and output consistency.

## Critical rule

The agent factory accelerates drafting and validation. Final legal, financial, security, token-economics, and production-code approval must remain human-controlled.


## Full automatic program run

After Chapter 3N and all canonical source files are placed in `workspace/source/`:

```bash
python run_all_chapters.py
python gap_detector.py
```

`run_all_chapters.py` generates Chapters 3O–3W sequentially. Each generated chapter is copied
into the source context before the next chapter begins, preventing later chapters from ignoring
earlier decisions.

The final completeness report is:

```text
workspace/reports/completion_gap_report.json
```

A chapter is not considered complete while unresolved references, constitutional conflicts,
missing failure/recovery rules, or missing implementation mappings remain.
