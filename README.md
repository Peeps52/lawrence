# Lawrence

An always-listening butler for macOS. Local transcription, one fast decision,
then it acts — or asks first, if asking is warranted.

```
whisper.cpp (local, resident)  →  Jev (one batched decision)  →  osascript
```

```
  "Lawrence, open my notes"
    addressed 0.96 · complete 0.75 · stakes 0.00 (0.0/3) · open_app · 526ms
    → Opening Notes.

  "Lawrence said the deal closed yesterday"
    addressed 0.18 · complete 0.17 · stakes 0.07 (0.2/3) · unclear · 438ms
    → not addressed to me; discarded

  "Lawrence, send an email to the partner declining the meeting"
    addressed 0.88 · complete 0.67 · stakes 1.00 (3.0/3) · run_task · 483ms
    → CONFIRMATION REQUIRED
```

## Three ideas worth stealing

**Semantic addressing, not a wake word.** A string match cannot tell
*"Lawrence, open my notes"* from *"Lawrence said the deal closed"*. A typed
decision can, and does — 0.96 against 0.18 above. This matters because the
best assistant names are ordinary human names, and a wake word forbids them.

**Completeness as a decision, not a silence timer.** Asking *"has this
instruction finished?"* lets it act on *"Lawrence, open—"* the moment the
sentence resolves, instead of waiting out a pause. Cheap, and it is what makes
these assistants feel fast.

**Stakes, phrased around reversibility.** Not "is this dangerous" but *"how
hard would this be to undo?"* — because "delete" sounds worse than "send"
while an email cannot be recalled and a file can be restored. Anything scoring
above 0.35 stops and asks out loud.

## Safety, such as it is

`execute()` implements three verbs: open an app, write a note, run a search.
Nothing that sends, deletes, posts or spends is behind a flag or a
confirmation — **it is not implemented at all**, so a misclassification has
nowhere to go. Confirmation is the second line of defence, not the only one.

Audio never leaves the machine. whisper.cpp transcribes locally and the text
is discarded unless Jev scores it as addressed. What is sent, when it is sent,
is one short utterance and nothing else.

It is still a permanently open microphone. That is a real thing to decide on,
not a footnote.

## Setup

```bash
brew install whisper-cpp
curl -L -o ~/.claude/voices/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
export OPENROUTER_API_KEY=...        # or TYPESAFE_API_KEY
python3 lawrence.py --once "Lawrence, open my notes" --dry-run   # no microphone
python3 lawrence.py --dry-run                                     # listen, execute nothing
python3 lawrence.py                                               # live
```

Optional: [Piper](https://github.com/rhasspy/piper) with `en_GB-alan-medium`
for local neural speech. Falls back to the macOS `say` voice.

## Measured on an M4

| stage | latency |
|---|---|
| whisper.cpp, model resident | ~311 ms |
| Jev decision, warm | ~310–520 ms |
| osascript | ~10 ms |
| **end to end** | **~750 ms** |

Cost is $0.000029 per utterance Jev sees.

A cold whisper process takes ~19 seconds before its first word. That is Metal
shader compilation, paid once at startup — which is exactly why the model is
held resident rather than spawned per phrase. Measuring the cold path and
concluding whisper is slow is an easy and wrong conclusion; inference itself
is 311 ms.

`ggml-tiny.en.bin` roughly halves transcription latency at some accuracy cost.

MIT.
