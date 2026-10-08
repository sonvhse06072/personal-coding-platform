from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[#\w][#\w./:-]{1,}", re.UNICODE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
IDENTIFIER_RE = re.compile(
    r"(?i)(?:\b(?:issue|pr|job|workorder|wo)\b(?:\s+|#|:)\s*#?[a-z0-9][a-z0-9._-]*|#\d+|\b[a-f0-9]{12,40}\b)"
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
    "docs/project/business-strategy.md",
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
        "Baseline authority preservation",
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
        "Baseline authority preservation",
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
        "Baseline authority preservation",
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
        "Baseline authority preservation",
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
        "Baseline authority preservation",
        "Core invariants",
        "Change discipline",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "12. Change control",
    },
}

T0_PRIORITY = {
    "product_manager": (
        "Core invariants",
        "Authority order",
        "Baseline authority preservation",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "6. Product Manager authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "Change discipline",
        "Mandatory documentation continuity",
        "12. Change control",
        "13. Practicality rule",
    ),
    "developer": (
        "Core invariants",
        "Authority order",
        "Baseline authority preservation",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "8. Agent-role principles",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "Change discipline",
        "Mandatory documentation continuity",
        "12. Change control",
    ),
    "reviewer": (
        "Core invariants",
        "Authority order",
        "Baseline authority preservation",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "8. Agent-role principles",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "Change discipline",
        "12. Change control",
    ),
    "debugger": (
        "Core invariants",
        "Authority order",
        "Baseline authority preservation",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "Change discipline",
        "12. Change control",
    ),
    "specialist": (
        "Core invariants",
        "Authority order",
        "Baseline authority preservation",
        "4. Authority hierarchy",
        "5. Human Owner authority",
        "9. Trust and security invariants",
        "10. Verification and delivery invariants",
        "Change discipline",
        "12. Change control",
    ),
}


CURRENT_INTENT_TERMS = {
    "current", "currently", "now", "active", "open", "today", "latest", "version",
    "state", "status", "next",
    # Vietnamese status questions also need current-state precedence.
    "hiện", "đang", "trạng", "mới", "nay",
}

HOST_PATH_RE = re.compile(
    r"/(?:home|mnt)/[^\s\x22\x27\x60<>]+"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(RUNTIME_API_TOKEN|DASHBOARD_READ_TOKEN|DASHBOARD_CONTROL_TOKEN|"
    r"ROUTER_API_TOKEN|DDEV_EXECUTOR_TOKEN|GITHUB_DELIVERY_TOKEN|"
    r"PLATFORM_INTERNAL_TOKEN)=([^\s]+)"
)


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
    result: set[str] = set()
    for item in IDENTIFIER_RE.findall(value or ""):
        normalized = item.lower().strip()
        if not normalized:
            continue
        result.add(normalized)
        numeric = re.search(r"#\d+", normalized)
        if numeric:
            result.add(numeric.group(0))
    return result


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
        # Non-overlapping blocks prevent an H1/parent from inheriting all matches.
        end = headings[ordinal + 1][0] if ordinal + 1 < len(headings) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            sections.append(Section(source, tier, heading, level, block, ordinal))
    return sections


def _sanitize_content(text: str) -> str:
    text = HOST_PATH_RE.sub("[local-path-redacted]", text)
    return SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[secret-redacted]",
        text,
    )


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_content(value)
    return value


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    marker = "\n...[truncated]"
    if limit <= len(marker):
        return marker[:limit], True
    return text[: limit - len(marker)] + marker, True



def _budgeted_t1_content(text: str, limit: int) -> tuple[str, list[str]]:
    """Prioritize active state and next actions instead of a silent T1 prefix cut.

    The source remains the original repository file; omitted heading identities
    are reported for a required live verification rather than silently hidden.
    """
    if len(text) <= limit:
        return text, []
    if limit <= 0:
        return "", []

    blocks = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    if len(blocks) == 1:
        return _clip(text, limit)[0], []

    preamble = blocks[0].strip()
    ranked: list[tuple[int, int, str, str]] = []
    for index, block in enumerate(blocks[1:]):
        heading = block.splitlines()[0].removeprefix("## ").strip()
        lower = heading.lower()
        if "resume" in lower:
            priority = 0
        elif "immediate" in lower or "next safe" in lower:
            priority = 1
        elif "active" in lower or "block" in lower:
            priority = 2
        elif "checkpoint" in lower or "github source" in lower:
            priority = 3
        elif "current" in lower:
            priority = 4
        elif "historical" in lower or "completed" in lower:
            priority = 90
        else:
            priority = 10
        ranked.append((priority, index, heading, block.strip()))

    selected = [preamble] if preamble else []
    remaining = max(limit - len(preamble), 0)
    omitted: list[str] = []
    for priority, _index, heading, block in sorted(ranked):
        separator = 2 if selected else 0
        available = remaining - separator
        if available <= 0:
            omitted.append(heading)
            continue
        if len(block) <= available:
            selected.append(block)
            remaining -= len(block) + separator
        elif priority <= 2 and available >= 300:
            clipped, _ = _clip(block, available)
            selected.append(clipped)
            remaining -= len(clipped) + separator
            omitted.append(heading + " (partially selected)")
        else:
            omitted.append(heading)

    return _clip("\n\n".join(selected), limit)[0], omitted

def _query_text(request: dict[str, Any]) -> str:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    refs = request.get("references") if isinstance(request.get("references"), dict) else {}
    parts = [
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
        if key in {"issue", "pr"}:
            if raw.isdigit():
                values.add(f"#{raw}")
                values.add(f"{key} #{raw}")
            elif not raw.startswith("/"):
                values.add(raw)
        elif key in {"job", "work_order", "workorder"}:
            values.add(raw)
        elif key in {"file", "topic"} and not raw.startswith("/"):
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
    # File references must match the repository path itself. Paths normally
    # do not appear inside the Markdown body, so body-only matching misses them.
    source_path = section.source.lower()
    exact_hits = sorted(
        ref for ref in exact_refs
        if ref in haystack or (ref.endswith(".md") and ref == source_path)
    )

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
    priority = T0_PRIORITY.get(role) or T0_PRIORITY["specialist"]
    priority_rank = {heading: index for index, heading in enumerate(priority)}
    candidates: list[Section] = []
    for source in ("AGENTS.md", "docs/project/constitution.md"):
        for section in _markdown_sections(source, "T0", _read(repo_root, source)):
            if section.heading in allowed:
                candidates.append(section)

    # T0 is a bounded pinned budget. Role-critical authority must be selected
    # before lower-priority governance prose so adding documentation cannot
    # silently evict the authority section that governs the active role.
    candidates.sort(
        key=lambda section: (
            priority_rank.get(section.heading, len(priority_rank)),
            section.source,
            section.ordinal,
        )
    )
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
    safe_content = _sanitize_content(section.content)
    content, truncated = _clip(safe_content, allowed)
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
    # Repository-local retrieval must not return PCP source for another project.
    # PCP checkouts may have local directory names such as '-v1'.
    source_project_id = (
        "personal-coding-platform"
        if (repo_root / "config/context-memory-eval.json").is_file()
        and (repo_root / "docs/project/context-memory-architecture.md").is_file()
        else repo_root.name
    )
    requested_project_id = str(request.get("project_id") or "").strip()
    if requested_project_id and requested_project_id != source_project_id:
        raise ValueError(
            f"project_id {requested_project_id!r} does not match "
            f"repository source {source_project_id!r}"
        )
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
    raw_query_tokens = {
        token.lower()
        for token in TOKEN_RE.findall(query)
    }
    exact_refs = _exact_reference_strings(request)
    current_intent = bool(raw_query_tokens & CURRENT_INTENT_TERMS)

    remaining = budget_chars
    pinned: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []

    # At the normal 24K character budget, retain full role-critical governance
    # before topical retrieval; reserve minimum T1 space for small budgets.
    t0_budget = min(9500, max(2400, int(budget_chars * 0.40)), budget_chars - 800)
    t0_remaining = min(t0_budget, remaining)
    for section in _t0_sections(repo_root, role):
        if t0_remaining < 300:
            break
        t0_remaining = _append_budgeted(
            pinned,
            section=section,
            content_limit=(
                2600 if section.heading == "Core invariants"
                else 1800 if section.heading == "6. Product Manager authority"
                else 1400
            ),
            remaining=t0_remaining,
            reasons=["pinned_governance", f"role:{role}"],
            score=None,
        )
        if t0_remaining <= 0:
            break
    remaining -= t0_budget - t0_remaining

    t1_source = _read(repo_root, "docs/project/current-state.md")
    t1_omitted_headings: list[str] = []
    if remaining > 0:
        t1_budget = min(12000, max(800, int(budget_chars * 0.45)))
        t1_budget = min(t1_budget, remaining)
        t1_content, t1_omitted_headings = _budgeted_t1_content(t1_source, t1_budget)
        current_state = Section(
            "docs/project/current-state.md",
            "T1",
            "Current Project State and Handoff",
            1,
            t1_content,
            0,
        )
        t1_remaining = _append_budgeted(
            pinned,
            section=current_state,
            content_limit=t1_budget,
            remaining=t1_budget,
            reasons=["pinned_current_state", "current_precedence"],
            score=None,
        )
        remaining -= t1_budget - t1_remaining
        if t1_omitted_headings and pinned and pinned[-1]["tier"] == "T1":
            pinned[-1]["truncated"] = True
            pinned[-1]["reasons"].append("t1_sections_omitted")

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
        "project_id": requested_project_id or source_project_id,
        "role": role,
        "task": _sanitize_value(
            request.get("task") if isinstance(request.get("task"), dict) else {}
        ),
        "references": _sanitize_value(
            request.get("references")
            if isinstance(request.get("references"), dict)
            else {}
        ),
        "budget_chars": budget_chars,
        "selected_chars": selected_chars,
        "remaining_chars": max(budget_chars - selected_chars, 0),
        "pinned": pinned,
        "retrieved": retrieved,
        "retrieval": {
            "policy": "deterministic-v1",
            "query": _sanitize_content(query),
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "supported_memory_found": bool(retrieved),
            "candidate_count": len(scored),
            "omitted_candidate_count": omitted,
            "current_intent": current_intent,
            "core_governance_complete": any(
                item["tier"] == "T0" and item["heading"] == "Core invariants"
                and not item["truncated"]
                for item in pinned
            ),
            "t1_omitted_section_count": len(t1_omitted_headings),
            "t1_omitted_headings": _sanitize_value(t1_omitted_headings[:12]),
            "exact_references": [
                _sanitize_content(value)
                for value in sorted(exact_refs)
            ],
        },
        "provenance": {
            "generated_from_head": _git_head(repo_root),
            "source_project_id": source_project_id,
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
