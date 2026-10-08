#!/usr/bin/env python3
"""T19: does the LLM pick the right tool? 15 questions, pass mark 13.

    LLM=local python3 scripts/eval_tool_calling.py      # on the Jetson
    python3 scripts/eval_tool_calling.py                 # MockLLM, anywhere
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.llm import LLM, MockLLM  # noqa: E402
from app.agent.prompts import system_prompt  # noqa: E402
from app.agent.tools import TOOL_SCHEMAS, Session  # noqa: E402
from app.config import Settings, Site, load_site  # noqa: E402

PASS_MARK = 13
# (question, tool that must be among the first calls; None = must answer without a tool)
QUESTIONS: list[tuple[str, Optional[str]]] = [
    ("Give me a status of both plants.", "live_state"),
    ("How many people are on Plant 1 right now?", "live_state"),
    ("What is happening on floor 3?", "live_state"),
    ("Show me Plant 2, floor 3.", "focus_view"),
    ("Take me to the first floor of plant one.", "focus_view"),
    ("Zoom in on Plant 2.", "focus_view"),
    ("Any safety issues in the last ten minutes?", "query_events"),
    ("Were there any near misses on Plant 1 in the last hour?", "query_events"),
    ("Has anyone entered a restricted zone today?", "query_events"),
    ("Is anybody missing a helmet on Plant 2?", "query_events"),
    ("What is the worker near the conveyor doing right now?", "look"),
    ("Describe what you see on Plant 1 floor 2.", "look"),
    ("Show me event 4.", "show_event"),
    ("Write the incident report for that.", "write_report"),
    ("What is the weather in Paris today?", None),
]


def score(llm: LLM, site: Site) -> list[tuple[str, Optional[str], list[str], bool]]:
    """Rows of (question, expected tool, tools called, correct) for a session viewing P2/F1 with event 4 last."""
    session = Session(focus_plant="P2", focus_floor="F1", last_event_id=4)
    rows = []
    for question, expected in QUESTIONS:
        messages = [{"role": "system", "content": system_prompt(site, session)}, {"role": "user", "content": question}]
        called = [c.name for c in llm.chat(messages, TOOL_SCHEMAS).tool_calls]
        correct = (expected in called) if expected else not called
        rows.append((question, expected, called, correct))
    return rows


def main() -> None:
    settings = Settings.from_env()
    site = load_site(settings.site_path)
    if settings.llm == "local":
        from app.agent.llm import LocalLLM

        llm: LLM = LocalLLM(settings.models_dir, device=settings.device)
    else:
        llm = MockLLM(site)
    rows = score(llm, site)
    for question, expected, called, correct in rows:
        print(f"{'ok  ' if correct else 'MISS'} {question}  expected={expected} called={called}")
    right = sum(r[3] for r in rows)
    print(f"\n{llm.name}: {right}/{len(rows)} (pass mark {PASS_MARK})")
    sys.exit(0 if right >= PASS_MARK else 1)


if __name__ == "__main__":
    os.environ.setdefault("LLM", "mock")
    main()
