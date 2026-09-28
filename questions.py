"""The reflex layer. Every decision Lawrence makes before acting.

One batched Jev call per utterance, ~310ms. The design follows the
architecture in Andy Gao's demo: decide whether you were addressed, whether
you have finished speaking, what kind of action is wanted, and -- the part
that matters -- how irreversible it would be.
"""

from __future__ import annotations

NAME = "Lawrence"

# Anything at or above this on `stakes` gets spoken confirmation before it
# runs. Set low deliberately: the cost of confirming something harmless is a
# second of your time, the cost of not confirming something destructive is
# unbounded. Asymmetric costs deserve an asymmetric threshold.
CONFIRM_ABOVE = 0.35

# Below this on `addressed`, the utterance is discarded without acting. It is
# never sent anywhere else and never stored.
ADDRESSED_MIN = 0.60


def build(utterance: str) -> dict[str, dict]:
    return {
        # Semantic addressing, not a wake word. "Lawrence, open my notes" is
        # addressed; "Lawrence said the deal closed" is not. A string match
        # cannot tell those apart; this can.
        "addressed": {
            "type": "noul",
            "instructions": (
                f"This utterance is addressed to an assistant named {NAME}, as "
                "an instruction or question directed at it. Merely mentioning "
                f"the name {NAME} while talking about a person, or speaking to "
                "someone else in the room, is NOT addressing the assistant."
            ),
        },
        # How the demo acts before you finish a sentence: it asks whether the
        # sentence is finished, rather than waiting for silence.
        "complete": {
            "type": "noul",
            "instructions": (
                "This utterance is a complete instruction that can be acted on "
                "as it stands. An instruction cut off mid-sentence, or one that "
                "clearly expects more words before it makes sense, is not "
                "complete."
            ),
        },
        # The gate. Phrased around what would be hard to UNDO, not around what
        # sounds dramatic -- "delete" sounds worse than "send" but an email
        # cannot be recalled and a file can be restored.
        "stakes": {
            "type": "score",
            "instructions": (
                "If this instruction were carried out, how hard would it be to "
                "undo? Judge reversibility, not how alarming the words sound."
            ),
            "criteria": [
                "Read-only: looks something up, opens an app, reads a file. "
                "Changes nothing.",
                "Trivially reversible: creates a note or a draft, writes a file "
                "that can simply be deleted.",
                "Reversible with effort: overwrites existing work, moves or "
                "renames things, changes settings.",
                "Irreversible or reaches other people: sends a message or "
                "email, posts publicly, deletes permanently, spends money, or "
                "changes anything outside this machine.",
            ],
        },
        "intent": {
            "type": "choice",
            "instructions": "What is being asked for?",
            "criteria": {
                "open_app": "Open or switch to an application",
                "write_note": "Write or dictate text into a note or document",
                "search_web": "Look something up online",
                "run_task": "Run a longer piece of work, such as a search over job listings",
                "answer": "Answer a question conversationally, taking no action",
                "stop": "Cancel, stop talking, or go away",
                "unclear": "Cannot tell what is being asked",
            },
        },
    }
