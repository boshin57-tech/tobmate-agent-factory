from __future__ import annotations
from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / "workspace" / "final"
REPORTS = ROOT / "workspace" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

REQUIRED_TERMS = [
    "Purpose", "Object", "State", "Validation", "Authorization",
    "Audit", "Invariant", "Failure", "Recovery", "Move", "Rust"
]

def inspect(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    unresolved = sorted(set(re.findall(r"\[REFERENCE_REQUIRED[^\]]*\]", text)))
    missing_terms = [t for t in REQUIRED_TERMS if t.lower() not in text.lower()]
    headings = re.findall(r"(?m)^#+\s+(.+)$", text)
    duplicates = sorted({h for h in headings if headings.count(h) > 1})
    return {
        "file": str(path),
        "characters": len(text),
        "unresolved_references": unresolved,
        "missing_required_concepts": missing_terms,
        "duplicate_headings": duplicates,
        "critical_gap": bool(unresolved or missing_terms)
    }

def main():
    results = [inspect(p) for p in sorted(FINAL.glob("3*.md"))]
    summary = {
        "files_checked": len(results),
        "critical_files": sum(1 for r in results if r["critical_gap"]),
        "results": results
    }
    out = REPORTS / "completion_gap_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
