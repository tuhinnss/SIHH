"""Post-LLM validation: every IS number must be a retrieval candidate AND a catalogue entry;
reasons may only state facts visible in the candidate line or the requirement."""
import json
import logging
import re
import time

from app.config import INVENTED_LOG

log = logging.getLogger("kalamkaar.validator")

_NUM = re.compile(r"\d+(?:\.\d+)?")
# certification facts come only from certification.csv, never from LLM prose
_CERT = re.compile(r"\bISI\b|\bBIS\b|certif|\bQCO\b|quality control order|\bCRS\b|compulsor|"
                   r"mandator|licen[cs]e|hallmark", re.I)


def ground_reason(reason: str | None, candidate_line: str, requirement: str) -> str | None:
    """Keep the one-line reason only if every number it states (grades, sizes, years, other IS
    numbers) and every certification term it uses also appears in the candidate line the LLM saw
    or in the requirement text. Otherwise drop it: the card is still shown, just without a reason."""
    if not reason:
        return None
    source = f"{candidate_line} {requirement}"
    nums = set(_NUM.findall(source))
    low = source.lower()
    extra = [n for n in _NUM.findall(reason) if n not in nums]
    extra += [m.group(0) for m in _CERT.finditer(reason) if m.group(0).lower() not in low]
    if extra:
        log.info("dropped ungrounded reason %r (not in candidate/requirement: %s)", reason, extra)
        return None
    return reason


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
