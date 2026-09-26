from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[#\\w][#\\w./:-]{1,}", re.UNICODE)
HEADING_RE = re.compile(r"^(#{1,6})\\s+(.+?)\\s*$")
IDENTIFIER_RE = re.compile(
    r"(?i)(?:\\b(?:issue|pr|job|workorder|wo)\\s*#?[-:\\s]*[a-z0-9._-]+|#\\d+|\\b[a-f0-9]{12,40}\\b)"
)

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "when", "where",
    "what", "which", "how", "why", "are", "was", "were", "been", "being", "have",
    "has", "had", "will", "would", "should", "could", "can", "may", "must", "not",
    "but", "its", "their", "our", "your", "about", "after", "before", "current",
    "project", "task", "review", "change", "work", "pcp",
}

T2_FILES = (
    "docs/project/architecture.md",
    "docs/project/operating-model.md",
    "docs/project/efficiency-model.md",
    "docs/project/provider-policy.md",
    "docs/project/roadmap.md",
    "docs/project/telegram-terminal-operations.md",
    "docs/project/service-secret-upgrades.md",
    "docs/project/context-memory-architecture.md",
)

T3_FILES = ("docs/project/history/episodes.md",)

ROLE_PREFERENCES = {
    "product_manager": {
        "docs/project/operating-model.md",
        "docs/project/roadmap.md",
        "docs/project/architecture.md",
        "docs/project/efficiency-model.md",
    },
    "developer": {
        "docs/project/architecture.md",
        "docs/project/operating-model.md",
    },
    "reviewer": {
        "docs/project/architecture.md",
        "docs/project/efficiency-model.md",
        "docs/project/operating-model.md",
    },
    "debugger": {
        "docs/project/architecture.md",
        "docs/project/history/episodes.md",
    },
    "specialist": {
        "docs/project/architecture.md",
        "docs/project/history/episodes.md",
    },
}

T0_HEADINGS = {
    "product_manager": {
        "Authority order",
        "Core invariants",
        "Change discipline",
        "Mandatory documentation continuity",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "6. Product Manager authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
        "13. Practicality rule",
    },
    "developer": {
        "Authority order",
        "Core invariants",
        "Change discipline",
        "Mandatory documentation continuity",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "8. Agent-role principles",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
    },
    "reviewer": {
        "Authority order",
        "Core invariants",
        "Change discipline",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "8. Agent-role principles",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
    },
    "debugger": {
        "Authority order",
        "Core invariants",
        "Change discipline",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
    },
    "specialist": {
        "Authority order",
        "Core invariants",
        "Change discipline",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
    },
}

CURRENT_INTENT_TERMS = {
    "current", "currently", "now", "active", "open", "today", "latest", "version",
    "state", "status", "next",
}


@dataclass(frozen=True)
class Section:
    source: str
    tier: str
    heading: str
    level: int
    content: str
    ordinal: int

    @property
    def identity(self) -> str:
        return f"{self.source}#{self.heading}"


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for raw in TOKEN_RE.findall(value.lower()):
        token = raw.strip(".,:;()[]{}<>\\\"'")
        if len(token) < 2 or token in STOPWORDS:
            continue
        result.add(token)
    return result


def _identifiers(value: str) -> set[str]:
    return {item.lower().strip() for item in IDENTIFIER_RE.findall(value or "")}


def _git_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def _read(repo_root: Path, relative: str) -> str:
    path = (repo_root / relative).resolve()
    root = repo_root.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"source escapes repository root: {relative}")
    return path.read_text(encoding="utf-8")


def _markdown_sections(source: str, tier: str, text: str) -> list[Section]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return [Section(source, tier, source, 1, text.strip(), 0)]

    sections: list[Section] = []
    for ordinal, (start, level, heading) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _next_heading in headings[ordinal + 1 :]:
            if next_level <= level:
                end = next_start
                break
        block = "\n".join(lines[start:end]).strip()
        if block:
            sections.append(Section(source, tier, heading, level, block, ordinal))
    return sections


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    marker = "\n...[truncated]"
    if limit <= len(marker):
        return marker[:limit], True
    return text[: limit - len(marker)] + marker, True


def _query_text(request: dict[str, Any]) -> str:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    refs = request.get("references") if isinstance(request.get("references"), dict) else {}
    parts = [
        request.get("project_id"),
        request.get("role"),
        task.get("title"),
        task.get("task_type"),
        task.get("description"),
        " ".join(f"{key}:{value}" for key, value in refs.items() if value),
    ]
    return " ".join(str(part or "") for part in parts)


def _exact_reference_strings(request: dict[str, Any]) -> set[str]:
    refs = request.get("references") if isinstance(request.get("references"), dict) else {}
    values: set[str] = set()
    for key, value in refs.items():
        if value is None or value == "":
            continue
        raw = str(value).strip().lower()
        values.add(raw)
        if key in {"issue", "pr"} and raw.isdigit():
            values.add(f"#{raw}")
            values.add(f"{key} #{raw}")
        if key in {"job", "work_order", "workorder"}:
            values.add(raw)
    values.update(_identifiers(_query_text(request)))
    return {value for value in values if value}


def _score_section(
    section: Section,
    *,
    query_tokens: set[str],
    exact_refs: set[str],
    role: str,
    current_intent: bool,
) -> tuple[int, list[str]]:
    haystack = section.content.lower()
    heading_tokens = _tokens(section.heading)
    body_tokens = _tokens(section.content)
    exact_hits = sorted(ref for ref in exact_refs if ref in haystack)

    heading_overlap = len(query_tokens & heading_tokens)
    body_overlap = len(query_tokens & body_tokens)

    if not exact_hits and heading_overlap == 0 and body_overlap == 0:
        return 0, []

    score = len(exact_hits) * 100
    reasons: list[str] = []

    if exact_hits:
        reasons.append("exact_ref:" + ",".join(exact_hits[:4]))

    if heading_overlap:
        score += heading_overlap * 12
        reasons.append(f"heading_overlap:{heading_overlap}")

    if body_overlap:
        score += min(body_overlap, 12) * 3
        reasons.append(f"body_overlap:{body_overlap}")

    if section.source in ROLE_PREFERENCES.get(role, set()):
        score += 8
        reasons.append("role_preference")

    if section.tier == "T2":
        score += 4
        reasons.append("semantic_tier")

    if section.tier == "T3":
        reasons.append("historical_tier")
        if current_intent and not exact_hits:
            score -= 30
            reasons.append("current_intent_penalty")

    return max(score, 0), reasons


def _t0_sections(repo_root: Path, role: str) -> list[Section]:
    allowed = T0_HEADINGS.get(role) or T0_HEADINGS["specialist"]
    candidates: list[Section] = []
    for source in ("AGENTS.md", "docs/project/constitution.md"):
        for section in _markdown_sections(source, "T0", _read(repo_root, source)):
            if section.heading in allowed:
                candidates.append(section)
    return candidates


def _candidate_sections(repo_root: Path) -> list[Section]:
    sections: list[Section] = []
    for source in T2_FILES:
        path = repo_root / source
        if path.exists():
            sections.extend(_markdown_sections(source, "T2", _read(repo_root, source)))
    for source in T3_FILES:
        path = repo_root / source
        if not path.exists():
            continue
        for section in _markdown_sections(source, "T3", _read(repo_root, source)):
            if section.level >= 3:
                sections.append(section)
    return sections


def _append_budgeted(
    output: list[dict[str, Any]],
    *,
    section: Section,
    content_limit: int,
    remaining: int,
    reasons: list[str],
    score: int | None,
) -> int:
    if remaining <= 0:
        return remaining
    allowed = min(content_limit, remaining)
    content, truncated = _clip(section.content, allowed)
    if not content:
        return remaining
    item: dict[str, Any] = {
        "tier": section.tier,
        "source": section.source,
        "heading": section.heading,
        "identity": section.identity,
        "content": content,
        "content_chars": len(content),
        "truncated": truncated,
        "reasons": reasons,
    }
    if score is not None:
        item["score"] = score
    output.append(item)
    return remaining - len(content)


def compose_context(repo_root: Path, request: dict[str, Any]) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    role = str(request.get("role") or "specialist").strip().lower()
    role = {
        "pm": "product_manager",
        "product-manager": "product_manager",
        "product manager": "product_manager",
        "dev": "developer",
        "code_reviewer": "reviewer",
        "debug": "debugger",
    }.get(role, role)
    if role not in ROLE_PREFERENCES:
        role = "specialist"

    budget_chars = int(request.get("budget_chars") or 24000)
    if budget_chars < 2000:
        raise ValueError("budget_chars must be at least 2000")
    if budget_chars > 120000:
        raise ValueError("budget_chars must be at most 120000")

    query = _query_text(request)
    query_tokens = _tokens(query)
    exact_refs = _exact_reference_strings(request)
    current_intent = bool(query_tokens & CURRENT_INTENT_TERMS)

    remaining = budget_chars
    pinned: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []

    for section in _t0_sections(repo_root, role):
        remaining = _append_budgeted(
            pinned,
            section=section,
            content_limit=1400,
            remaining=remaining,
            reasons=["pinned_governance", f"role:{role}"],
            score=None,
        )
        if remaining <= 0:
            break

    current_state = Section(
        "docs/project/current-state.md",
        "T1",
        "Current Project State and Handoff",
        1,
        _read(repo_root, "docs/project/current-state.md"),
        0,
    )
    if remaining > 0:
        remaining = _append_budgeted(
            pinned,
            section=current_state,
            content_limit=min(12000, remaining),
            remaining=remaining,
            reasons=["pinned_current_state", "current_precedence"],
            score=None,
        )

    scored: list[tuple[int, int, Section, list[str]]] = []
    for section in _candidate_sections(repo_root):
        score, reasons = _score_section(
            section,
            query_tokens=query_tokens,
            exact_refs=exact_refs,
            role=role,
            current_intent=current_intent,
        )
        if score <= 0:
            continue
        tier_order = 0 if section.tier == "T2" else 1
        scored.append((score, tier_order, section, reasons))

    scored.sort(key=lambda row: (-row[0], row[1], row[2].source, row[2].ordinal))

    for score, _tier_order, section, reasons in scored:
        if remaining < 300:
            break
        remaining = _append_budgeted(
            retrieved,
            section=section,
            content_limit=3200,
            remaining=remaining,
            reasons=reasons,
            score=score,
        )

    selected_chars = sum(item["content_chars"] for item in pinned + retrieved)
    omitted = max(len(scored) - len(retrieved), 0)

    return {
        "context_pack_version": 1,
        "project_id": str(request.get("project_id") or ""),
        "role": role,
        "task": request.get("task") if isinstance(request.get("task"), dict) else {},
        "references": request.get("references") if isinstance(request.get("references"), dict) else {},
        "budget_chars": budget_chars,
        "selected_chars": selected_chars,
        "remaining_chars": max(budget_chars - selected_chars, 0),
        "pinned": pinned,
        "retrieved": retrieved,
        "retrieval": {
            "policy": "deterministic-v1",
            "query": query,
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "supported_memory_found": bool(retrieved),
            "candidate_count": len(scored),
            "omitted_candidate_count": omitted,
            "current_intent": current_intent,
            "exact_references": sorted(exact_refs),
        },
        "provenance": {
            "generated_from_head": _git_head(repo_root),
            "repository_root_name": repo_root.name,
            "sources_are_repository_relative": True,
        },
    }


def render_context_text(pack: dict[str, Any]) -> str:
    lines = [
        f"CONTEXT_PACK_VERSION: {pack['context_pack_version']}",
        f"ROLE: {pack['role']}",
        f"PROJECT: {pack['project_id']}",
        f"GENERATED_FROM_HEAD: {pack['provenance'].get('generated_from_head') or 'unknown'}",
        "",
    ]
    for group_name in ("pinned", "retrieved"):
        lines.append(group_name.upper())
        for item in pack[group_name]:
            lines.extend(
                [
                    f"[{item['tier']}] {item['identity']}",
                    f"reasons={','.join(item.get('reasons') or [])}",
                    item["content"],
                    "",
                ]
            )
    if not pack["retrieval"]["supported_memory_found"]:
        lines.append("RETRIEVAL: no supported T2/T3 memory selected for this query")
    return "\n".join(lines).rstrip() + "\n"


def read_all_docs_chars(repo_root: Path) -> int:
    total = 0
    for path in sorted((repo_root / "docs" / "project").rglob("*.md")):
        total += len(path.read_text(encoding="utf-8"))
    if (repo_root / "AGENTS.md").exists():
        total += len((repo_root / "AGENTS.md").read_text(encoding="utf-8"))
    return total


def selected_identities(pack: dict[str, Any]) -> set[str]:
    return {
        str(item.get("identity") or "")
        for item in [*pack.get("pinned", []), *pack.get("retrieved", [])]
        if item.get("identity")
    }


__all__ = [
    "compose_context",
    "read_all_docs_chars",
    "render_context_text",
    "selected_identities",
]
