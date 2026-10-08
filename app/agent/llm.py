"""The `LLM` interface with its two backends: `MockLLM` (keyword router) and `LocalLLM` (VLM on the GPU)."""
from __future__ import annotations

import io
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from app.agent.prompts import VISION_PROMPT, tool_instructions
from app.config import Site


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM(Protocol):
    name: str

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        """One model turn: either tool calls or the final answer text."""

    def look(self, image_jpeg: Optional[bytes], question: str, context: str) -> str:
        """Answer a question about one camera frame."""


def parse_tool_calls(text: str) -> tuple[list[ToolCall], str]:
    """Extract `<tool_call>{json}</tool_call>` blocks: (calls, the text that is left)."""
    calls = []
    for raw in re.findall(r"<tool_call>(.*?)</tool_call>", text, flags=re.DOTALL):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            arguments = data.get("arguments") or {}
            calls.append(ToolCall(data["name"], arguments if isinstance(arguments, dict) else {}))
    rest = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
    return calls, rest


# ---------------------------------------------------------------- mock

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
            "first": 1, "ground": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6}
_TYPE_WORDS = {
    "near_miss": ("near miss", "near misses"),
    "restricted_zone": ("restricted zone entry", "restricted zone entries"),
    "no_helmet": ("missing helmet", "missing helmets"),
    "crowding": ("crowding event", "crowding events"),
}
_REPORT = re.compile(r"\breport\b")
_VISION = re.compile(r"\b(doing|wearing|carrying|holding|look at|do you see|can you see|describe)\b")
_EVENTS = re.compile(r"\b(safety|issues?|incidents?|events?|near[- ]miss(es)?|restricted|helmets?|ppe|hard hats?|"
                     r"crowd(ing|ed)?|alerts?|violations?|accidents?)\b")
_WHO = re.compile(r"\b(who|whose|identify|which (person|worker|employee))\b")
_PERSON = re.compile(r"\b(person|worker|employee|he|she|they|him|her|them|someone|guy|man|woman)\b")
_ABOUT_PERSON = re.compile(r"\b(how long|before|again|history|previous(ly)?|first time|authori[sz]ed|allowed|"
                           r"supervisor|manager|details|shift|department|role|job|where)\b")
_NAVIGATE = re.compile(r"\b(show|go to|take me|fly|zoom|focus|open|switch to|move to)\b")
_STATUS = re.compile(r"\b(status|how many|people|persons?|workers?|vehicles?|forklifts?|happening|going on|"
                     r"overview|summary|busy|count)\b")


def _number(word: Optional[str]) -> Optional[int]:
    if not word:
        return None
    return int(word) if word.isdigit() else _NUMBERS.get(word)


def _digits(identifier: str) -> str:
    return re.sub(r"\D", "", identifier)


def _count(n: int, one: str, many: str) -> str:
    return f"{n if n else 'no'} {one if n == 1 else many}"


def _place(plant_name: str, floor: Optional[str]) -> str:
    return f"{plant_name}, floor {_digits(floor) or floor}" if floor else plant_name


class MockLLM:
    """Keyword router that calls the same tools as the real model. Fallback required by NFR3."""

    name = "mock"

    def __init__(self, site: Site, directory: Optional[Any] = None) -> None:
        self.site = site
        self.directory = directory  # app.identity.Directory, to recognise employee names in questions

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        results = [(m["name"], json.loads(m["content"])) for m in messages[last_user + 1:] if m["role"] == "tool"]
        if results:
            return LLMReply(text=self._compose(results, messages[last_user]["content"].lower()))
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        view = re.search(r"Current view: (\w+)(?:/(\w+))?", system)
        event = re.search(r"Last event id: (\d+)", system)
        view_plant, view_floor = (view.group(1), view.group(2)) if view and view.group(1) != "none" else (None, None)
        return self._route(messages[last_user]["content"], view_plant, view_floor, int(event.group(1)) if event else None)

    def look(self, image_jpeg: Optional[bytes], question: str, context: str) -> str:
        return (f"The tracker shows {context}. The vision model is mocked on this machine, "
                f"so I can't see finer detail than that.")

    # ---- routing ----

    def _route(self, text: str, view_plant: Optional[str], view_floor: Optional[str], last_event: Optional[int]) -> LLMReply:
        question, text = text.strip(), text.lower()
        plant, floor = self._parse_place(text)
        named_event = re.search(r"\bevent\s*(?:number\s*|#)?(\d+)", text)
        event_id = int(named_event.group(1)) if named_event else last_event

        if _REPORT.search(text):
            if event_id is None:
                return LLMReply(text="I don't have an event selected. Ask me about safety issues first, or click a marker.")
            return LLMReply(tool_calls=[ToolCall("write_report", {"event_id": event_id})])
        if named_event or (re.search(r"\b(that|this|the) (event|incident|one)\b", text) and _NAVIGATE.search(text)
                           and last_event is not None):
            return LLMReply(tool_calls=[ToolCall("show_event", {"event_id": event_id})])
        named = self.directory.find(text) if self.directory else None
        if named:
            return LLMReply(tool_calls=[ToolCall("identify_person", {"name": named.name})])
        if _WHO.search(text) or (_PERSON.search(text) and _ABOUT_PERSON.search(text)):
            return LLMReply(tool_calls=[ToolCall("identify_person", {"event_id": event_id} if event_id is not None else {})])
        if _VISION.search(text):
            plant, floor = plant or view_plant, floor or (view_floor if not plant or plant == view_plant else None)
            if not plant or not floor:
                return LLMReply(text="Which plant and floor should I look at?")
            return LLMReply(tool_calls=[ToolCall("look", {"plant": plant, "floor": floor, "question": question})])

        calls = []
        if plant:
            calls.append(ToolCall("focus_view", {"plant": plant, **({"floor": floor} if floor else {})}))
        place = {k: v for k, v in (("plant", plant), ("floor", floor)) if v}
        if _EVENTS.search(text):
            args: dict[str, Any] = {**place, "minutes_back": self._parse_minutes(text)}
            event_type = self._parse_type(text)
            if event_type:
                args["type"] = event_type
            return LLMReply(tool_calls=calls + [ToolCall("query_events", args)])
        if _NAVIGATE.search(text) or _STATUS.search(text) or plant or floor:
            if not plant and floor and view_plant and _NAVIGATE.search(text):
                place["plant"] = view_plant
                calls.append(ToolCall("focus_view", dict(place)))
            return LLMReply(tool_calls=calls + [ToolCall("live_state", place)])
        return LLMReply(text="I can't see that. I can tell you about people, vehicles and safety events on the plant floors.")

    def _parse_place(self, text: str) -> tuple[Optional[str], Optional[str]]:
        plant_id = floor_id = None
        number = None
        m = re.search(r"\bplant\s*(?:number\s*)?(\w+)", text) or re.search(r"\bp(\d+)\b", text)
        if m:
            number = _number(m.group(1))
        for p in self.site.plants:
            if p.name.lower() in text or (number is not None and _digits(p.id) == str(number)):
                plant_id = p.id
                break
        m = (re.search(r"\bfloor\s*(?:number\s*)?(\w+)", text) or re.search(r"\b(\w+)\s+floor\b", text)
             or re.search(r"\bf(\d+)\b", text))
        number = _number(m.group(1)) if m else None
        if number is None:
            m = re.search(r"\b(first|ground|second|third|fourth|fifth|sixth)\s+floor\b", text)
            number = _number(m.group(1)) if m else None
        if number is not None:
            floors = self.site.plant(plant_id).floors if plant_id else [f for _, f in self.site.floors()]
            floor_id = next((f.id for f in floors if _digits(f.id) == str(number)), None)
        return plant_id, floor_id

    @staticmethod
    def _parse_minutes(text: str) -> float:
        if "today" in text:
            return 24 * 60
        m = re.search(r"\b(?:last|past)\s+(?:(\w+)\s+)?(minute|min|hour|day)s?\b", text)
        if not m:
            return 10
        amount = _number(m.group(1)) if m.group(1) else 1
        if amount is None:
            return 10
        return amount * {"minute": 1, "min": 1, "hour": 60, "day": 24 * 60}[m.group(2)]

    @staticmethod
    def _parse_type(text: str) -> Optional[str]:
        for event_type, pattern in (("near_miss", r"near[- ]miss"), ("restricted_zone", r"restricted"),
                                    ("no_helmet", r"helmet|ppe|hard hat"), ("crowding", r"crowd")):
            if re.search(pattern, text):
                return event_type
        return None

    # ---- answers from tool results ----

    def _compose(self, results: list[tuple[str, dict[str, Any]]], question: str = "") -> str:
        by_name = {name: result for name, result in results if "error" not in result}
        if not by_name:
            return f"I can't see that: {results[0][1]['error']}."
        if "identify_person" in by_name:
            return self._compose_person(by_name["identify_person"], question)
        if "write_report" in by_name:
            r = by_name["write_report"]
            return f"The incident report for event {r['event_id']} is in the side panel. Severity is {r['severity']}."
        if "look" in by_name:
            return by_name["look"]["answer"]
        if "show_event" in by_name:
            e = by_name["show_event"]
            return (f"Event {e['id']} is a {_TYPE_WORDS[e['type']][0]} on {_place(e['plant_name'], e['floor'])} "
                    f"at {e['time'][:5]}. {e['summary']}")
        if "query_events" in by_name:
            return self._compose_events(by_name["query_events"])
        if "live_state" in by_name:
            return self._compose_state(by_name["live_state"], focused="focus_view" in by_name)
        f = by_name["focus_view"]
        return f"Showing {_place(f['plant_name'], f['floor'])}."

    @staticmethod
    def _compose_person(r: dict[str, Any], question: str) -> str:
        e, incident, now = r["employee"], r["incident"], r["now"]
        name = e["name"]
        timing = ""
        if incident and incident["entered_at"]:
            stay = (f"has been inside for {incident['seconds_in_zone']} seconds" if incident["still_inside"]
                    else f"stayed {incident['seconds_in_zone']} seconds")
            allowed = "" if incident["authorised"] else " without authorisation"
            timing = (f"{name} entered restricted zone {incident['zone']} on "
                      f"{_place(incident['plant_name'], incident['floor'])} at {incident['entered_at'][:5]}{allowed} and {stay}.")
        elif incident:
            timing = (f"The {_TYPE_WORDS[incident['type']][0]} was on {_place(incident['plant_name'], incident['floor'])} "
                      f"at {incident['time'][:5]}.")
        where = (f"{name} is on {_place(now['plant_name'], now['floor'])} right now." if now
                 else f"I can't see {name} on any camera right now.")
        others = r["other_incidents_24h"]
        history = (f"{name} has {_count(others, 'other incident', 'other incidents')} in the last 24 hours."
                   if others else f"This is {name}'s only incident in the last 24 hours.")
        if re.search(r"\bwhere\b", question):
            return f"{where} {timing}".strip()
        if re.search(r"\b(before|again|history|previous(ly)?|first time)\b", question):
            return f"{history} {timing}".strip()
        if re.search(r"\bhow long\b", question):
            return timing or where
        if re.search(r"\b(supervisor|manager|authori[sz]ed|allowed)\b", question):
            zones = ", ".join(e["authorised_zones"]) or "no restricted zones"
            return f"{name} reports to {e['supervisor']} and is authorised for {zones}."
        intro = f"That is {name}, {e['role'].lower()} in {e['department']} on the {e['shift'].lower()} shift, badge {e['id']}."
        return f"{intro} {timing or where}"

    def _compose_events(self, r: dict[str, Any]) -> str:
        plant = self.site.plant(r["plant"]) if r["plant"] else None
        scope = f" on {_place(plant.name, r['floor'])}" if plant else (f" on floor {_digits(r['floor'])}" if r["floor"] else "")
        minutes = r["minutes_back"]
        window = f"{minutes:g} minutes" if minutes < 120 else f"{minutes / 60:g} hours"
        if not r["count"]:
            return f"I can't see any safety events{scope} in the last {window}."
        kinds = ", ".join(_count(n, *_TYPE_WORDS[t]) for t, n in r["by_type"].items())
        latest = r["events"][0]
        return (f"I found {_count(r['count'], 'safety event', 'safety events')}{scope} in the last {window}: {kinds}. "
                f"The latest was on {_place(latest['plant_name'], latest['floor'])} at {latest['time'][:5]}: {latest['summary']}")

    @staticmethod
    def _compose_state(r: dict[str, Any], focused: bool) -> str:
        def counts(row: dict[str, Any]) -> str:
            return (f"{_count(row['people'], 'person', 'people')}, {_count(row['vehicles'], 'vehicle', 'vehicles')} "
                    f"and {_count(row['open_events'], 'open event', 'open events')}")

        if not r["floors"]:
            return "I can't see that."
        if len(r["floors"]) == 1:
            row = r["floors"][0]
            return f"{'Here is ' if focused else ''}{_place(row['plant_name'], row['floor'])}. It has {counts(row)}."
        return " ".join(f"{total['plant_name']} has {counts(total)}." for total in r["totals"].values())


# ---------------------------------------------------------------- local

class LocalLLM:
    """One vision-language model for text reasoning and for `look` (plan section 8).

    Loaded through the pre-installed NVIDIA PyTorch with `transformers`. Raises on any problem so
    that startup can fall back to `MockLLM`.
    """

    name = "local"

    def __init__(self, models_dir: Path, model_id: Optional[str] = None, device: str = "cuda") -> None:
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.device = device
        self.model_id = model_id or os.environ.get("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        self._torch = torch
        self._lock = threading.Lock()
        self.processor = AutoProcessor.from_pretrained(self.model_id, cache_dir=str(models_dir))
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_id, torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            cache_dir=str(models_dir)).to(device).eval()
        self._generate([{"role": "user", "content": [{"type": "text", "text": "Say ok."}]}], 4)  # pre-warm

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        text = self._generate(_to_chat(messages, tools), 220)
        calls, rest = parse_tool_calls(text)
        return LLMReply(tool_calls=calls) if calls else LLMReply(text=rest)

    def look(self, image_jpeg: Optional[bytes], question: str, context: str) -> str:
        if image_jpeg is None:
            return "I can't see that floor right now."
        return self._ask_image(image_jpeg, VISION_PROMPT.format(context=context, question=question), 60)

    def try_look(self, image_jpeg: bytes, prompt: str) -> Optional[str]:
        """Like `look` with a raw prompt, but returns None instead of waiting when the model is busy."""
        if not self._lock.acquire(blocking=False):
            return None
        self._lock.release()
        return self._ask_image(image_jpeg, prompt, 4)

    def _ask_image(self, image_jpeg: bytes, prompt: str, max_new_tokens: int) -> str:
        from PIL import Image

        image = Image.open(io.BytesIO(image_jpeg)).convert("RGB")
        content = [{"type": "image", "image": image}, {"type": "text", "text": prompt}]
        return self._generate([{"role": "user", "content": content}], max_new_tokens)

    def _generate(self, chat: list[dict[str, Any]], max_new_tokens: int) -> str:
        with self._lock, self._torch.inference_mode():
            inputs = self.processor.apply_chat_template(
                chat, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
            ).to(self.device)
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            new_tokens = output[0][inputs["input_ids"].shape[1]:]
            return self.processor.decode(new_tokens, skip_special_tokens=True).strip()


def _to_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agent-loop messages to plain system/user/assistant turns with tool calls and results as text."""
    chat: list[dict[str, Any]] = []
    for m in messages:
        role, text = m["role"], m.get("content") or ""
        if role == "system" and tools:
            text += tool_instructions(tools)
        elif role == "assistant" and m.get("tool_calls"):
            text = "\n".join(f"<tool_call>{json.dumps(c)}</tool_call>" for c in m["tool_calls"])
        elif role == "tool":
            role, text = "user", f"<tool_response name=\"{m['name']}\">{text}</tool_response>"
        if chat and chat[-1]["role"] == role == "user":
            chat[-1]["content"][0]["text"] += "\n" + text
        else:
            chat.append({"role": role, "content": [{"type": "text", "text": text}]})
    return chat
