from __future__ import annotations

import re
from typing import Any


def parse_summary_evaluation_output(text: str) -> dict[str, Any]:
    def extract_score(key: str) -> int | None:
        match = re.search(rf"{re.escape(key)}:\s*(10|[1-9])", text, re.I)
        return int(match.group(1)) if match else None

    note_match = re.search(r"note:\s*(.+)", text, re.I)
    return {
        "clarity": extract_score("clarity"),
        "coverage": extract_score("coverage"),
        "faithfulness": extract_score("faithfulness"),
        "note": note_match.group(1).strip() if note_match else "",
        "raw_evaluation": text.strip(),
    }


def parse_reply_evaluation_output(text: str) -> dict[str, Any]:
    score_names = ["relevance", "empathy_tone", "accuracy_safety", "actionability", "clarity"]
    parsed: dict[str, Any] = {"raw_evaluation": text.strip()}

    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key in score_names:
            match = re.match(r"^(10|[1-9])\b", value)
            if match:
                parsed[key] = int(match.group(1))
        elif key == "note":
            parsed["note"] = value

    return parsed

