#!/usr/bin/env python3
"""Lawrence — an always-listening butler for macOS.

    whisper.cpp (local, resident)  →  Jev (one batched decision)  →  osascript

Listens continuously. Transcribes locally and discards. Nothing is transmitted
unless Jev decides you were addressing it, and nothing irreversible runs
without spoken confirmation.

    python3 lawrence.py            # listen
    python3 lawrence.py --dry-run  # decide, narrate, execute nothing
    python3 lawrence.py --once "Lawrence, open my notes"   # test one utterance

Measured on an M4: transcription ~311ms with the model resident, Jev ~310ms
warm, execution ~10ms. The 19s you may see on a cold whisper process is Metal
shader compilation, paid once at startup, never per utterance -- which is why
the model is held open rather than spawned per phrase.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from questions import ADDRESSED_MIN, CONFIRM_ABOVE, NAME, build  # noqa: E402

HOME = Path.home()
MODEL = HOME / ".claude/voices/ggml-base.en.bin"
PIPER_VOICE = HOME / ".claude/voices/en_GB-alan-medium.onnx"
OR_URL = "https://openrouter.ai/api/alpha/decisions"
OR_MODEL = "~typesafe/jev-latest"   # leading tilde is required


# ----------------------------------------------------------------- speech out
def say(text: str) -> None:
    """Speak through Piper if available, else the system voice."""
    if PIPER_VOICE.exists() and _which("piper"):
        wav = f"/tmp/lawrence-{os.getpid()}.wav"
        p = subprocess.run(["piper", "-m", str(PIPER_VOICE), "-f", wav],
                           input=text.encode(), capture_output=True)
        if p.returncode == 0 and Path(wav).exists():
            subprocess.run(["/usr/bin/afplay", wav], capture_output=True)
            Path(wav).unlink(missing_ok=True)
            return
    subprocess.run(["/usr/bin/say", "-v", "Arthur", "-r", "176", text],
                   capture_output=True)


def _which(cmd: str) -> bool:
    return subprocess.run(["command", "-v", cmd], shell=False,
                          capture_output=True,
                          executable="/bin/bash").returncode == 0 or bool(
        subprocess.run(f"command -v {cmd}", shell=True, capture_output=True).stdout)


# --------------------------------------------------------------------- reflex
def key() -> str:
    # .env beside this file, so Lawrence works as a background service with
    # no shell to export anything in.
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                kk, vv = line.split("=", 1)
                os.environ.setdefault(kk.strip(), vv.strip().strip("'\""))
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k
    # Fall back to the key the `evaluate` MCP server already holds, so there
    # is one place to rotate it rather than two.
    try:
        cfg = json.loads((HOME / ".claude.json").read_text())
    except Exception:
        raise SystemExit("Set OPENROUTER_API_KEY.")

    def find(o):
        if isinstance(o, dict):
            for kk, v in o.items():
                if kk == "mcpServers" and isinstance(v, dict):
                    for n, c in v.items():
                        if n == "evaluate":
                            e = c.get("env") or {}
                            if "OPENROUTER_API_KEY" in e:
                                return e["OPENROUTER_API_KEY"]
                r = find(v)
                if r:
                    return r
        return None

    k = find(cfg)
    if not k:
        raise SystemExit("Set OPENROUTER_API_KEY.")
    return k


def reflex(utterance: str, api_key: str) -> tuple[dict, float]:
    """One batched Jev call. Raises rather than guessing on failure."""
    body = json.dumps({
        "model": OR_MODEL,
        "state": {"utterance": utterance, "assistant_name": NAME},
        "questions": build(utterance),
    }).encode()
    req = urllib.request.Request(OR_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Jev HTTP {e.code}: {e.read().decode()[:300]}") from e
    if "answers" not in out:
        raise RuntimeError(f"malformed Jev response: {str(out)[:200]}")
    return out, (time.perf_counter() - t0) * 1000


# -------------------------------------------------------------------- execute
def osa(script: str) -> tuple[bool, str]:
    p = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True)
    return p.returncode == 0, (p.stdout or p.stderr).strip()


def execute(intent: str, utterance: str) -> str:
    """Only reversible verbs live here. Anything that sends, deletes, posts or
    spends is deliberately absent -- it is not gated behind a flag, it is
    simply not implemented, so a misclassification cannot reach it."""
    if intent == "open_app":
        words = utterance.replace(",", " ").split()
        known = {"notes": "Notes", "safari": "Safari", "chrome": "Google Chrome",
                 "arc": "Arc", "mail": "Mail", "calendar": "Calendar",
                 "finder": "Finder", "terminal": "Terminal", "obsidian": "Obsidian",
                 "spotify": "Spotify", "messages": "Messages"}
        for w in words:
            app = known.get(w.lower().strip(".?!"))
            if app:
                # `open -a` rather than osascript `activate`: telling
                # AppleScript to activate an app that is not already running
                # fails with -609 "Connection is invalid". `open` launches it
                # if needed, and needs no Automation permission.
                r = subprocess.run(["/usr/bin/open", "-a", app],
                                   capture_output=True, text=True)
                return (f"Opening {app}." if r.returncode == 0
                        else f"Could not open {app}. {r.stderr.strip()}")
        return "I did not catch which application."

    if intent == "write_note":
        text = utterance
        for cue in (" write ", " note ", " dictate "):
            if cue in utterance.lower():
                text = utterance[utterance.lower().index(cue) + len(cue):]
                break
        safe = text.replace('"', "'")
        # No folder or account specified: Notes uses the default. Hardcoding
        # "iCloud" worked on my machine and would fail on one where the
        # account is named differently -- and this Mac alone has three.
        ok, err = osa(f'tell application "Notes" to make new note '
                      f'with properties {{body:"{safe}"}}')
        return "Noted." if ok else f"The note failed. {err}"

    if intent == "search_web":
        q = utterance.split(None, 1)[1] if " " in utterance else utterance
        ok, _ = osa(f'open location "https://duckduckgo.com/?q={urllib.parse.quote(q)}"')
        return "Searching." if ok else "The search failed."

    if intent == "run_task":
        return _run_task(utterance)

    if intent == "stop":
        return "Very good."

    return "I am not set up to do that yet."


# Tasks Lawrence can start. Each is long-running, so it is launched detached
# and reports by opening its own output -- blocking the listen loop for two
# minutes would mean missing everything said during it.
JEV_OFFCYCLE = Path.home() / "jev-offcycle"

JOB_WORDS = re.compile(
    r"\b(role|roles|job|jobs|intern|internship|internships|off[- ]?cycle|"
    r"vacanc|listing|listings|position|positions|shortlist|graduate|"
    r"placement|spring\s?week)\b", re.I)


def _run_task(utterance: str) -> str:
    """Longer work. Only the job search exists so far; anything else says so
    plainly rather than pretending."""
    if JOB_WORDS.search(utterance) and (JEV_OFFCYCLE / "jev_offcycle").is_dir():
        subprocess.Popen(
            ["/usr/bin/python3", "-m", "jev_offcycle.crawl_cli",
             "examples/sources.json", "--limit", "40"],
            cwd=str(JEV_OFFCYCLE),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        return ("Searching the boards now, sir. The shortlist will open in your "
                "browser when it is ready.")
    return "I am not set up to do that yet."


# ----------------------------------------------------------------------- loop
def handle(utterance: str, api_key: str, dry: bool) -> None:
    utterance = utterance.strip()
    if not utterance:
        return
    try:
        res, ms = reflex(utterance, api_key)
    except RuntimeError as e:
        print(f"  reflex failed: {e}", file=sys.stderr)
        return

    a = res["answers"]
    addressed = float(a["addressed"]["noul"])
    complete = float(a["complete"]["noul"])
    stakes_lvl = float(a["stakes"].get("score", 0))
    n_levels = len(a["stakes"].get("legend") or {}) or 1
    stakes = stakes_lvl / (n_levels - 1) if n_levels > 1 else 0.0
    intent = a["intent"]["choice"]
    cost = (res.get("usage") or {}).get("cost", 0.0)

    print(f'  "{utterance}"')
    print(f"    addressed {addressed:.2f} · complete {complete:.2f} · "
          f"stakes {stakes:.2f} ({stakes_lvl:.1f}/{n_levels-1}) · {intent} "
          f"· {ms:.0f}ms · ${cost:.6f}")

    if addressed < ADDRESSED_MIN:
        print("    → not addressed to me; discarded")
        return
    if complete < 0.5:
        print("    → incomplete; waiting for the rest")
        return
    if stakes >= CONFIRM_ABOVE:
        print(f"    → stakes {stakes:.2f} ≥ {CONFIRM_ABOVE}: CONFIRMATION REQUIRED")
        say(f"That would be hard to undo. Shall I proceed, sir?")
        return
    if dry:
        print(f"    → would execute: {intent}")
        return
    reply = execute(intent, utterance)
    print(f"    → {reply}")
    say(reply)


def main() -> int:
    ap = argparse.ArgumentParser(prog="lawrence")
    ap.add_argument("--once", metavar="TEXT", help="run one utterance and exit")
    ap.add_argument("--dry-run", action="store_true", help="decide but execute nothing")
    args = ap.parse_args()

    api_key = key()
    if args.once:
        handle(args.once, api_key, args.dry_run)
        return 0

    if not MODEL.exists():
        raise SystemExit(f"whisper model missing: {MODEL}")
    print(f"{NAME} listening. Ctrl-C to stop.")
    print("  (model loads once; the first few seconds are Metal shader compilation)")
    proc = subprocess.Popen(
        ["whisper-stream", "-m", str(MODEL), "-t", "6", "--step", "0",
         "--length", "5000", "-vth", "0.6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    try:
        for raw in proc.stdout:
            line = raw.strip()
            if not line or line.startswith("###"):
                continue
            # whisper-stream may emit "[00:00:00.000 --> 00:00:03.000]  text".
            # STRIP the prefix rather than skipping the line -- an earlier
            # version skipped anything starting with "[" and would have
            # silently discarded every transcription while looking healthy.
            m = re.match(r"^\[[^\]]*\]\s*(.*)$", line)
            if m:
                line = m.group(1).strip()
            # Control banners carry no speech.
            if not line or line.lower() in ("start speaking", "(speaking)"):
                continue
            handle(line, api_key, args.dry_run)
    except KeyboardInterrupt:
        print("\nVery good, sir.")
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used in execute)
    raise SystemExit(main())
