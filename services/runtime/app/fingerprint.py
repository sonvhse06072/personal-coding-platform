from __future__ import annotations

import hashlib
import re


def failure_fingerprint(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"0x[0-9a-f]+", "0xADDR", normalized)
    normalized = re.sub(r"\b\d{2,}\b", "N", normalized)
    normalized = re.sub(r"/[^\s:]+/", "/PATH/", normalized)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    core = "\n".join(lines[-30:])
    return hashlib.sha256(core.encode()).hexdigest()[:24]
