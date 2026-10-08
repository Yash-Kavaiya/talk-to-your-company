"""Generate the narration, one WAV per line of script.json, and record each line's length.

    python narration/generate.py deepgram     # needs DEEPGRAM_API_KEY in the environment
    python narration/generate.py draft        # local stand-in voice, only for timing a draft
    python narration/generate.py retime       # re-measure the files already in assets/vo

The key is read from the environment only (on Windows also from the user-level variable set by
`setx`). It is never written to a file. Voice: DEEPGRAM_VOICE, default aura-2-thalia-en.
"""
import json
import os
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "vo"
URL = "https://api.deepgram.com/v1/speak?model={voice}&encoding=linear16&container=wav&sample_rate=48000"


def deepgram_key() -> str:
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key and os.name == "nt":  # set with `setx` after this shell started
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
                key = winreg.QueryValueEx(env, "DEEPGRAM_API_KEY")[0]
        except OSError:
            key = ""
    if not key:
        sys.exit("DEEPGRAM_API_KEY is not set. Set it in the environment, then run this again.")
    return key


def deepgram(text: str, target: Path, key: str, voice: str) -> None:
    request = urllib.request.Request(URL.format(voice=voice), data=json.dumps({"text": text}).encode(),
                                     headers={"Authorization": f"Token {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"Deepgram refused the request ({exc.code}): {exc.read().decode(errors='replace')[:300]}")


def repair(path: Path) -> None:
    """Deepgram streams WAV with a placeholder length in the header; rewrite it with the real one."""
    raw = path.read_bytes()
    fmt, data = raw.index(b"fmt "), raw.index(b"data")
    channels, rate = struct.unpack("<HI", raw[fmt + 10:fmt + 16])
    bits = struct.unpack("<H", raw[fmt + 22:fmt + 24])[0]
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(bits // 8)
        f.setframerate(rate)
        f.writeframes(raw[data + 8:])


def draft(text: str, target: Path) -> None:
    subprocess.run(f'npx --yes hyperframes@0.8.123 tts "{text}" --voice af_heart --output "{target}"',
                   shell=True, check=True, stdout=subprocess.DEVNULL)


def seconds(path: Path) -> float:
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def main() -> None:
    provider = sys.argv[1] if len(sys.argv) > 1 else "deepgram"
    OUT.mkdir(parents=True, exist_ok=True)
    key = deepgram_key() if provider == "deepgram" else ""
    voice = os.environ.get("DEEPGRAM_VOICE", "aura-2-thalia-en")
    previous = json.loads((HERE / "timing.json").read_text()) if (HERE / "timing.json").exists() else {}
    if provider == "retime":
        timing = {"provider": previous.get("provider", "deepgram"), "voice": previous.get("voice", voice), "lines": {}}
    else:
        timing = {"provider": provider, "voice": voice if provider == "deepgram" else "kokoro af_heart (draft)", "lines": {}}
    for line in json.loads((HERE / "script.json").read_text(encoding="utf-8")):
        target = OUT / f"{line['id']}.wav"
        if provider == "deepgram":
            deepgram(line["text"], target, key, voice)
        elif provider == "draft":
            draft(line["text"], target)
        if provider != "draft":
            repair(target)
        timing["lines"][line["id"]] = round(seconds(target), 2)
        print(f"{timing['lines'][line['id']]:6.2f} s  {line['id']}")
    (HERE / "timing.json").write_text(json.dumps(timing, indent=2))
    print(f"total {sum(timing['lines'].values()):.1f} s of narration ({timing['voice']})")


if __name__ == "__main__":
    main()
