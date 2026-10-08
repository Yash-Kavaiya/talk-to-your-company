"""Agent loop: user text -> LLM with tools -> run tools -> final answer (plan section 6)."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Awaitable, Callable

from app.agent.llm import LLM
from app.agent.prompts import system_prompt
from app.agent.tools import TOOL_SCHEMAS, Tools
from app.config import Site
from app.protocol import UiMsg

MAX_TOOL_ROUNDS = 3
HISTORY_TURNS = 6
CANT_SEE = "I can't see that."


def split_sentences(text: str) -> list[str]:
    """Sentences in speaking order, so each can go to speech synthesis as soon as it is complete."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text.strip())
    return [p for p in parts if p]


class Agent:
    def __init__(self, llm: LLM, tools: Tools, site: Site) -> None:
        self.llm = llm
        self.tools = tools
        self.site = site

    async def ask(self, text: str, send_ui: Callable[[UiMsg], Awaitable[None]]) -> str:
        """Answer one question. `ui` messages from tools go out through `send_ui` as they happen."""
        session = self.tools.session
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(self.site, session)},
            *session.history,
            {"role": "user", "content": text},
        ]
        answer = ""
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            tools = TOOL_SCHEMAS if round_number < MAX_TOOL_ROUNDS else []
            reply = await asyncio.to_thread(self.llm.chat, messages, tools)
            if not reply.tool_calls or not tools:
                answer = reply.text.strip()
                break
            messages.append({"role": "assistant", "content": "",
                             "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls]})
            for call in reply.tool_calls:
                result = await asyncio.to_thread(self.tools.call, call.name, call.arguments)
                messages.append({"role": "tool", "name": call.name, "content": json.dumps(result)})
                pending, self.tools.pending_ui = self.tools.pending_ui, []
                for ui in pending:
                    await send_ui(ui)
        answer = answer or CANT_SEE
        session.history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        del session.history[:-2 * HISTORY_TURNS]
        return answer
