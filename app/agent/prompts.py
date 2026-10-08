"""Prompts for the agent (plan section 6)."""
from __future__ import annotations

import json
from typing import Any

from app.agent.tools import Session
from app.config import Site

SYSTEM_RULES = """You are the voice copilot of a company's live 3D twin. You speak to a plant manager.
Rules:
- Answer in two sentences or fewer. Your answer is spoken aloud: no lists, no markdown.
- Always call a tool before stating any fact about the site. Never guess.
- If the tools return nothing useful, or the question is not about this site, say "I can't see that".
- When the user names a plant or floor, also call focus_view so the twin shows it.
- "that" or "it" refers to the last event id given below.
- Never say who someone is from how they look. Only identify_person may name a person."""

VISION_PROMPT = ("You are looking at one frame from a factory or warehouse camera. Answer the question in one "
                 "short sentence, only from what is visible. If it is not visible, say \"I can't see that\".\n"
                 "Tracker context: {context}\nQuestion: {question}")

HELMET_PROMPT = "Is the person in this image wearing a hard hat or safety helmet? Answer only yes or no."


def system_prompt(site: Site, session: Session) -> str:
    """Rules plus the site and the conversation context. MockLLM reads the last two lines too."""
    layout = "; ".join(f"{p.name} ({p.id}) floors {', '.join(f.id for f in p.floors)}" for p in site.plants)
    view = "none"
    if session.focus_plant:
        view = session.focus_plant + (f"/{session.focus_floor}" if session.focus_floor else "")
    last = session.last_event_id if session.last_event_id is not None else "none"
    return f"{SYSTEM_RULES}\nSite: {layout}.\nCurrent view: {view}\nLast event id: {last}"


def tool_instructions(schemas: list[dict[str, Any]]) -> str:
    """JSON-constrained tool calling parsed by us (plan section 8 fallback), independent of the model's template."""
    lines = [json.dumps(s, separators=(",", ":")) for s in schemas]
    return ("\n\nTools you can call:\n" + "\n".join(lines) +
            "\n\nTo call a tool, reply with only this, one line per call:\n"
            '<tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>\n'
            "You then receive the results in <tool_response> blocks and give the spoken answer as plain text.")
