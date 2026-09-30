"""Post-LLM validation: every IS number must be a retrieval candidate AND a catalogue entry."""
import json
import logging
import time

from app.config import INVENTED_LOG

log = logging.getLogger("specsure.validator")


def validate_selection(items: list[dict], candidates: set[str], catalogue: set[str],
                       query: str = "") -> tuple[list[dict], list[dict]]:
    """Return (valid, dropped). `dropped` entries carry a `drop_reason`; they are also logged."""
    valid, dropped, seen = [], [], set()
    for it in items:
        num = it.get("is_number")
        if not isinstance(num, str) or num not in candidates:
            reason = "not_in_candidates"
        elif num not in catalogue:
            reason = "not_in_catalogue"
        elif num in seen:
            reason = "duplicate"
        else:
            seen.add(num)
            valid.append(it)
            continue
        dropped.append({**it, "drop_reason": reason})
    if dropped:
        log.warning("dropped %d LLM items for %r: %s", len(dropped), query,
                    [(d.get("is_number"), d["drop_reason"]) for d in dropped])
        try:
            with open(INVENTED_LOG, "a", encoding="utf-8") as f:
                for d in dropped:
                    if d["drop_reason"] != "duplicate":
                        f.write(json.dumps({"ts": time.time(), "query": query, **d}) + "\n")
        except OSError:
            pass
    return valid, dropped
