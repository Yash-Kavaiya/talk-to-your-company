# Talk-to-your-Company

Voice copilot plus live 3D twin for a company with 2 plants x 3 floors. Runs entirely on one
NVIDIA Jetson Thor container. Built for the Globant Physical AI Hackathon (demo Friday of Week 2).

## How we work (spec-driven)

1. `specs/spec.md` says WHAT and why. `specs/plan.md` says HOW. `specs/tasks.md` says in what order.
2. Work on exactly one task ID from `specs/tasks.md` at a time. Read its spec and plan sections first.
3. Write or update tests for the task's "done when" line before or with the code.
4. Run `pytest -q` before declaring a task done. Then tick the task in `specs/tasks.md`.
5. If code needs to differ from the spec or plan, stop and propose the spec change first.
   Never let code and specs drift.
6. Do not add features that are not in the spec. Scope is frozen; the cut order is in tasks.md.

## Hard constraints of the target machine (do not violate)

- No sudo, no apt, no Docker. Only `pip install --user`.
- NEVER install, upgrade or pin `torch`, `torchvision` or `numpy`. Before adding any dependency run
  `pip install --dry-run <pkg> 2>&1 | grep "^Would install"`; if any of those three appear, stop and ask.
- The app must listen on `0.0.0.0:8000`. Only that port is published.
- Code lives in `/workspace`, models and datasets in `/cache`, nothing important in `/tmp`.
- 8 CPU cores, 15 GB RAM, one GPU shared with other teams. Budget memory (see plan.md section 8).
- No secrets or tokens in files. No client or personal data; public or synthetic footage only.
- All inference is local. No cloud AI calls at runtime (this is the point of the demo).

## Run modes

Every heavy component has a mock so the whole app runs on a laptop without a GPU.

    PERCEPTION=mock|real   LLM=mock|local   ASR=mock|local   TTS=mock|local

- Laptop dev: all mock. `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Jetson: all real. `scripts/preflight.sh && scripts/run.sh`

## Conventions

- Python 3, FastAPI, pydantic models for every message that crosses a boundary.
- Frontend: plain ES modules, Three.js vendored in `web/vendor/`, no bundler, no framework.
- Site layout (plants, floors, cameras, zones) comes only from `config/site.yaml`. Never hard-code it.
- Small modules, type hints, no clever abstractions. This is a 5-day build.
- Tests: `pytest`, mock mode only, must pass without a GPU.
