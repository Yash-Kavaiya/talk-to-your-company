"""Generate the narration, one WAV per line of script.json, and record each line's length.

    python narration/generate.py kokoro [id ...]       # local Kokoro voice through `hyperframes tts`
    python narration/generate.py elevenlabs [id ...]   # needs ELEVENLABS_API_KEY with text-to-speech permission
    python narration/generate.py retime                # re-measure the files already in assets/vo

The key is read from the environment only. It is never written to a file.
Voices: KOKORO_VOICE (default af_heart), ELEVENLABS_VOICE (a voice id, default Rachel).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "vo"
URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
MODEL = "eleven_multilingual_v2"
# every line becomes a 48 kHz mono WAV, trimmed of leading and trailing silence
TRIM = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05"


def elevenlabs(lines: list[dict], i: int, target: Path, key: str, voice: str) -> None:
    body = {"text": lines[i]["text"], "model_id": MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}}
    if i > 0:
        body["previous_text"] = lines[i - 1]["text"]
    if i + 1 < len(lines):
        body["next_text"] = lines[i + 1]["text"]
    request = urllib.request.Request(URL.format(voice=voice), data=json.dumps(body).encode(),
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
    mp3 = target.with_suffix(".mp3")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            mp3.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"ElevenLabs refused the request ({exc.code}): {exc.read().decode(errors='replace')[:300]}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af", f"{TRIM},areverse,{TRIM},areverse",
                    "-ar", "48000", "-ac", "1", str(target)], check=True)
    mp3.unlink()


def kokoro(text: str, target: Path, voice: str) -> None:
    raw = target.with_suffix(".raw.wav")
    subprocess.run(["npx", "--yes", "hyperframes@0.8.141", "tts", text, "--voice", voice, "--output", str(raw)],
                   check=True, stdout=subprocess.DEVNULL, shell=os.name == "nt")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"{TRIM},areverse,{TRIM},areverse",
                    "-ar", "48000", "-ac", "1", str(target)], check=True)
    raw.unlink()


def seconds(path: Path) -> float:
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def main() -> None:
    provider = sys.argv[1] if len(sys.argv) > 1 else "kokoro"
    only = set(sys.argv[2:])
    OUT.mkdir(parents=True, exist_ok=True)
    voice = os.environ.get("ELEVENLABS_VOICE", "21m00Tcm4TlvDq8ikWAM")
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if provider == "elevenlabs" and not key:
        sys.exit("ELEVENLABS_API_KEY is not set. Set it in the environment, then run this again.")
    lines = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    kokoro_voice = os.environ.get("KOKORO_VOICE", "af_heart")
    previous = json.loads((HERE / "timing.json").read_text()) if (HERE / "timing.json").exists() else {}
    if provider == "kokoro":
        timing = {"provider": "kokoro (local)", "voice": kokoro_voice, "lines": {}}
    elif provider == "elevenlabs":
        timing = {"provider": "elevenlabs", "model": MODEL, "voice": voice, "lines": {}}
    else:
        timing = {**previous, "lines": {}}
    for i, line in enumerate(lines):
        target = OUT / f"{line['id']}.wav"
        if provider == "elevenlabs" and (not only or line["id"] in only):
            elevenlabs(lines, i, target, key, voice)
        elif provider == "kokoro" and (not only or line["id"] in only):
            kokoro(line["text"], target, kokoro_voice)
        if not target.exists():
            continue
        timing["lines"][line["id"]] = round(seconds(target), 2)
        print(f"{timing['lines'][line['id']]:6.2f} s  {line['id']}")
    (HERE / "timing.json").write_text(json.dumps(timing, indent=2))
    print(f"total {sum(timing['lines'].values()):.1f} s of narration")


if __name__ == "__main__":
    main()
