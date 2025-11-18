from typing import Optional


COLOR_MAP = {
    "blk": "black",
    "black": "black",
    "navy blue": "navy",
    "dark blue": "navy",
    # extend as you go
}

FIT_MAP = {
    "slim fit": "slim",
    "regular fit": "regular",
    "oversized": "oversized",
}


def normalize_color(color: Optional[str]) -> Optional[str]:
    if not color:
        return None
    c = color.strip().lower()
    return COLOR_MAP.get(c, c)


def normalize_fit(fit: Optional[str]) -> Optional[str]:
    if not fit:
        return None
    f = fit.strip().lower()
    return FIT_MAP.get(f, f)