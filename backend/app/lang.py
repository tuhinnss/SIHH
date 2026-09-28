"""Cheap language detection: Devanagari script -> hi, romanised Hindi markers -> hinglish, else en."""
import re

_DEV = re.compile(r"[ऀ-ॿ]")
# Common romanised-Hindi function/product words (no domain knowledge about standards).
_HINGLISH = {"ke", "ka", "ki", "ko", "liye", "wala", "wali", "chahiye", "aur", "se", "mein", "me",
             "hai", "hain", "pani", "sariya", "saria", "bijli", "taar", "nali", "lohe", "lohey",
             "kamre", "sadak", "batti", "khamba", "khambe", "cement ka", "ke lie", "vala"}


def detect_lang(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if _DEV.match(c)) / len(letters) > 0.3:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for w in words if w in _HINGLISH)
    return "hinglish" if hits >= 2 or (words and hits / len(words) >= 0.34) else "en"
