"""Interaction logging → supervised-finetuning dataset.

Every LLM turn (system prompt, user message, model reply, and optional 👍/👎)
can be appended here as a JSONL record. Exported in the chat format an SFT /
LoRA finetuning job expects (``messages`` list), so the app's own traffic becomes
training data — the data-collection half of "basic finetuning methods".

    from data.feedback import log_interaction, export_sft
    log_interaction(system="...", user="make 2A lighter", assistant="...", reward=1)
    export_sft("data/sft_dataset.jsonl")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

_LOG_PATH = os.getenv("FEEDBACK_LOG", "data/interactions.jsonl")


@dataclass
class Interaction:
    system: str
    user: str
    assistant: str
    reward: int | None = None          # +1 / -1 / None from thumbs feedback
    tags: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


def log_interaction(
    *, system: str, user: str, assistant: str, reward: int | None = None,
    tags: list[str] | None = None, path: str | None = None,
) -> None:
    """Append one interaction as a JSONL line (best-effort, never raises)."""

    rec = Interaction(system=system, user=user, assistant=assistant, reward=reward, tags=tags or [])
    try:
        with open(path or _LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec)) + "\n")
    except Exception:
        pass


def load_interactions(path: str | None = None) -> list[dict[str, Any]]:
    p = path or _LOG_PATH
    if not os.path.exists(p):
        return []
    out: list[dict[str, Any]] = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def to_sft_record(interaction: dict[str, Any]) -> dict[str, Any]:
    """Convert a logged interaction to the OpenAI/HF chat SFT format."""

    return {
        "messages": [
            {"role": "system", "content": interaction.get("system", "")},
            {"role": "user", "content": interaction.get("user", "")},
            {"role": "assistant", "content": interaction.get("assistant", "")},
        ]
    }


def export_sft(out_path: str, *, src: str | None = None, min_reward: int | None = None) -> int:
    """Write a JSONL SFT dataset; keep only rewarded examples when asked.

    ``min_reward`` filters to positively-rated turns — a simple form of
    reward-filtered / rejection-sampling finetuning data selection.
    """

    kept = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for rec in load_interactions(src):
            if min_reward is not None and (rec.get("reward") is None or rec["reward"] < min_reward):
                continue
            fh.write(json.dumps(to_sft_record(rec)) + "\n")
            kept += 1
    return kept
