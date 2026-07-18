#!/usr/bin/env python3
"""Shared utilities for codex-reflect Hooks and scripts.

Cross-platform compatible (Windows, macOS, Linux).
"""
import re
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from .codex_history import parse_transcript
from .codex_paths import get_project_state_dir
from .state_store import StateStore

# =============================================================================
# Path utilities
# =============================================================================

def get_queue_path(project_dir: Optional[str] = None) -> Path:
    """Get the current project's queue path below the Codex state root."""
    return get_project_state_dir(project_dir) / "queue.json"


def get_backup_dir(project_dir: Optional[str] = None) -> Path:
    """Get the current project's queue backup directory."""
    return get_project_state_dir(project_dir) / "backups"


# =============================================================================
# Queue operations
# =============================================================================


def load_queue(project_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load the current project's queue from shared Codex state."""
    return StateStore(get_project_state_dir(project_dir)).load()


def save_queue(items: List[Dict[str, Any]], project_dir: Optional[str] = None) -> None:
    """Atomically save the current project's queue."""
    StateStore(get_project_state_dir(project_dir)).save(items)


def append_to_queue(item: Dict[str, Any], project_dir: Optional[str] = None) -> None:
    """Append one item while holding the project queue lock."""
    StateStore(get_project_state_dir(project_dir)).append(item)


# =============================================================================
# Timestamp utilities
# =============================================================================

def iso_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_timestamp() -> str:
    """Get timestamp for backup filenames."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# =============================================================================
# Pattern definitions retained from the upstream capture behavior
# =============================================================================

# Explicit marker patterns (highest confidence)
EXPLICIT_PATTERNS = [
    (r"remember:", "remember:", 0.90, 120),  # pattern, name, confidence, decay_days
]

# Positive feedback patterns
POSITIVE_PATTERNS = [
    (r"perfect!|exactly right|that's exactly", "perfect", 0.70, 90),
    (r"that's what I wanted|great approach", "great-approach", 0.70, 90),
    (r"keep doing this|love it|excellent|nailed it", "keep-doing", 0.70, 90),
]

# Correction patterns (conservative set to minimize false positives)
# Format: (regex_pattern, pattern_name, is_strong)
#
# DESIGN NOTES:
# - These patterns are English-centric as a FAST first-pass filter
# - Non-English corrections are caught by semantic filtering during reflect
# - We use STRUCTURAL signals (length, questions, task requests) for language-agnostic filtering
# - Users can use explicit markers like "remember:" in any language
#
CORRECTION_PATTERNS = [
    (r"^no[,. ]+", "no,", True),  # Starts with "no," - common correction opener
    (r"^don't\b|^do not\b", "don't", True),  # Starts with don't/do not
    (r"^stop\b|^never\b", "stop/never", True),  # Starts with stop/never
    (r"that's (wrong|incorrect)|that is (wrong|incorrect)", "that's-wrong", True),
    (r"^actually[,. ]", "actually", False),  # Starts with "actually"
    (r"^I meant\b|^I said\b", "I-meant/said", True),  # Clarification
    (r"^I told you\b|^I already told\b", "I-told-you", True),  # Higher confidence
    (r"use .{1,30} not\b", "use-X-not-Y", True),  # "use X not Y" - limited gap
]

# Guardrail patterns - "don't do X unless" constraints (highest confidence for corrections)
# These detect user frustrations about the agent making unwanted changes
# Format: (regex_pattern, pattern_name, confidence, decay_days)
GUARDRAIL_PATTERNS = [
    (r"don't (?:add|include|create) .{1,40} unless", "dont-unless-asked", 0.90, 120),
    (r"only (?:change|modify|edit|touch) what I (?:asked|requested|said)", "only-what-asked", 0.90, 120),
    (r"stop (?:refactoring|changing|modifying|editing) (?:unrelated|other|surrounding)", "stop-unrelated", 0.90, 120),
    (r"don't (?:over-engineer|add extra|be too|make unnecessary)", "dont-over-engineer", 0.85, 90),
    (r"don't (?:refactor|reorganize|restructure) (?:unless|without)", "dont-refactor-unless", 0.85, 90),
    (r"leave .{1,30} (?:alone|unchanged|as is)", "leave-alone", 0.85, 90),
    (r"don't (?:add|include) (?:comments|docstrings|type hints|annotations) (?:unless|to code)", "dont-add-annotations", 0.85, 90),
    (r"(?:minimal|minimum|only necessary) changes", "minimal-changes", 0.80, 90),
]

# Structural patterns indicating FALSE POSITIVES (language-agnostic)
# These focus on MESSAGE STRUCTURE rather than specific words
FALSE_POSITIVE_PATTERNS = [
    r"[?\uff1f]$",  # Ends with question mark (ASCII ? or full-width ？)
    r"[\u55ce\u5417\u5462\u304b\uae4c]$",  # Ends with CJK question particle (嗎吗呢か까)
    r"^(please|can you|could you|would you|help me)\b",  # Task request openers
    r"(help|fix|check|review|figure out|set up)\s+(this|that|it|the)\b",  # Task verbs
    r"(error|failed|could not|cannot|can't|unable to)\s+\w+",  # Error descriptions
    r"(is|was|are|were)\s+(not|broken|failing)",  # Bug reports
    r"^I (need|want|would like)\b",  # Task requests
    r"^(ok|okay|alright)[,.]?\s+(so|now|let)",  # Task continuations
]

# English phrases that look like correction openers but are NOT corrections
# Especially important for CJK-mixed text where these appear naturally
NON_CORRECTION_PHRASES = [
    r"^no\s+problem",        # "No problem" - agreement
    r"^no\s+worries",        # "No worries" - agreement
    r"^no\s+need\b",         # "No need" - acknowledgment
    r"^no\s+way\b",          # "No way!" - surprise/exclamation
    r"^don't\s+worry",       # "Don't worry" - reassurance
    r"^don't\s+mind",        # "Don't mind" - agreement
    r"^don't\s+bother",      # "Don't bother" - polite decline
    r"^never\s+mind",        # "Never mind" - dismissal
    r"^stop\s+worrying",     # "Stop worrying" - reassurance
]

# CJK correction patterns (parallel to English CORRECTION_PATTERNS)
# These detect explicit corrections in CJK languages
# Format: (regex_pattern, pattern_name, is_strong)
CJK_CORRECTION_PATTERNS = [
    # Japanese
    (r"^いや[、,.\s]|^いや違", "iya", True),       # いや、〜 / いや違う - "no, ..."
    (r"^違う[、，,.\s！!。]|^ちがう[、,.\s]", "chigau", True),  # 違う、〜 - "wrong, ..."
    (r"そうじゃなく[てけ]|そっちじゃなく[てけ]", "souja-nakute", True),  # "not that"
    (r"間違[いえっ]て", "machigatte", True),       # 間違ってる - "it's wrong"
    (r"じゃなくて.{0,30}にして", "janakute-nishite", True),  # 〜じゃなくて〜にして
    (r"^やめて[。！!]?\s*$", "yamete", True),      # やめて - "stop"
    (r"^そうじゃない", "souja-nai", True),          # そうじゃない - "that's not right"
    (r"って言った[のよでじゃ]", "tte-itta", True),   # って言ったのに - "I told you"
    # Chinese
    (r"^不是[，,. ]", "bushi", True),              # 不是、〜 - "no, ..."
    (r"^错了|^錯了", "cuole", True),               # 错了 - "wrong"
    (r"不要.{0,20}要", "buyao-yao", True),         # 不要X要Y - "don't X, use Y"
    # Korean
    (r"^아니[,. ]", "ani", True),                  # 아니, - "no, ..."
    (r"틀렸", "teullyeoss", True),                 # 틀렸 - "wrong"
]

# Maximum prompt length for live capture (UserPromptSubmit hook)
# Prompts longer than this are almost certainly system content, not user corrections.
# Exception: explicit "remember:" markers are always processed regardless of length.
MAX_CAPTURE_PROMPT_LENGTH = 500

# Maximum message length for weak patterns (structural heuristic)
# Long messages are more likely to be context/tasks than corrections
MAX_WEAK_PATTERN_LENGTH = 150

# Very short messages without question marks are more likely corrections
MIN_SHORT_CORRECTION_LENGTH = 80


def detect_patterns(text: str) -> Tuple[Optional[str], str, float, str, int]:
    """
    Detect patterns in text and return classification.

    Returns:
        Tuple of (type, matched_patterns, confidence, sentiment, decay_days)
        type: "explicit", "positive", "auto", "guardrail", or None
        matched_patterns: Space-separated pattern names
        confidence: 0.0 to 1.0
        sentiment: "correction" or "positive"
        decay_days: Number of days until decay
    """
    # Too short to be actionable (e.g. "OK", "好", "yes")
    # CJK characters carry more meaning per char, so use a lower threshold
    stripped = text.strip()
    has_cjk = bool(re.search(r'[\u3000-\u9fff\uf900-\ufaff\uac00-\ud7af]', stripped))
    short_threshold = 2 if has_cjk else 4
    if len(stripped) <= short_threshold:
        return (None, "", 0.0, "correction", 90)

    # Check for explicit "remember:" - always highest priority
    for pattern, name, confidence, decay in EXPLICIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ("explicit", name, confidence, "correction", decay)

    # Check for guardrail patterns - "don't do X unless" constraints
    # These are high-confidence corrections about unwanted behavior
    for pattern, name, confidence, decay in GUARDRAIL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ("guardrail", name, confidence, "correction", decay)

    # Check for FALSE POSITIVE patterns - skip these messages
    for fp_pattern in FALSE_POSITIVE_PATTERNS:
        if re.search(fp_pattern, text, re.IGNORECASE):
            return (None, "", 0.0, "correction", 90)

    # Check for non-correction English phrases (before correction patterns)
    # Prevents "No problem", "Don't worry" etc. from being caught as corrections
    for nc_pattern in NON_CORRECTION_PHRASES:
        if re.search(nc_pattern, text, re.IGNORECASE):
            return (None, "", 0.0, "correction", 90)

    # Check for positive patterns
    matched_positive = []
    for pattern, name, confidence, decay in POSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matched_positive.append(name)

    if matched_positive:
        return ("positive", " ".join(matched_positive), 0.70, "positive", 90)

    # Skip long messages for weak patterns (likely task requests)
    text_length = len(text)

    # Check for CJK correction patterns (language-specific)
    # Use stripped text for anchor patterns (^/$) to handle leading/trailing whitespace
    matched_cjk = []
    cjk_strong = False
    for pattern, name, is_strong in CJK_CORRECTION_PATTERNS:
        if re.search(pattern, stripped):
            matched_cjk.append(name)
            if is_strong:
                cjk_strong = True

    if matched_cjk:
        confidence = 0.75 if cjk_strong else 0.60
        decay_days = 90 if cjk_strong else 60
        if text_length < MIN_SHORT_CORRECTION_LENGTH:
            confidence = min(0.90, confidence + 0.10)
        elif text_length > 300:
            confidence = max(0.50, confidence - 0.15)
        return ("auto", " ".join(matched_cjk), confidence, "correction", decay_days)

    # Check for English correction patterns
    matched_corrections = []
    pattern_count = 0
    has_strong_pattern = False
    has_i_told_you = False

    for pattern, name, is_strong in CORRECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Skip weak patterns in long messages
            if not is_strong and text_length > MAX_WEAK_PATTERN_LENGTH:
                continue
            matched_corrections.append(name)
            pattern_count += 1
            if is_strong:
                has_strong_pattern = True
            if name == "I-told-you":
                has_i_told_you = True

    if matched_corrections:
        # Calculate confidence based on pattern count, type, and length
        if has_i_told_you:
            confidence = 0.85
            decay_days = 120
        elif pattern_count >= 3:
            confidence = 0.85
            decay_days = 120
        elif pattern_count >= 2:
            confidence = 0.75
            decay_days = 90
        elif has_strong_pattern:
            confidence = 0.70
            decay_days = 60
        else:
            confidence = 0.55  # Reduced for weak single patterns
            decay_days = 45

        # Adjust confidence based on message length (structural signal)
        # Short messages are more likely to be direct corrections
        if text_length < MIN_SHORT_CORRECTION_LENGTH:
            confidence = min(0.90, confidence + 0.10)  # Boost for short messages
        elif text_length > 300:
            confidence = max(0.50, confidence - 0.15)  # Reduce for long messages
        elif text_length > 150:
            confidence = max(0.55, confidence - 0.10)

        return ("auto", " ".join(matched_corrections), confidence, "correction", decay_days)

    return (None, "", 0.0, "correction", 90)


def create_queue_item(
    message: str,
    item_type: str,
    patterns: str,
    confidence: float,
    sentiment: str,
    decay_days: int,
    project: Optional[str] = None,
    session_id: str = "",
    turn_id: Optional[str] = None,
    model: Optional[str] = None,
    source: str = "",
) -> Dict[str, Any]:
    """Create a properly formatted queue item."""
    return {
        "schema_version": 1,
        "type": item_type,
        "message": message,
        "timestamp": iso_timestamp(),
        "project": project if project is not None else os.getcwd(),
        "session_id": session_id,
        "turn_id": turn_id,
        "model": model,
        "source": source,
        "patterns": patterns,
        "confidence": confidence,
        "sentiment": sentiment,
        "decay_days": decay_days,
    }


# =============================================================================
# Session file utilities
# =============================================================================

def extract_user_messages(session_file: Path, corrections_only: bool = False) -> List[str]:
    """
    Extract user messages from a supported Codex session file.

    Args:
        session_file: Path to the session JSONL file
        corrections_only: If True, only return messages matching correction patterns

    Returns:
        List of user message texts
    """
    if not session_file.exists():
        return []

    result = parse_transcript(session_file)
    if not result.supported:
        return []
    messages = [
        message
        for message in result.user_messages
        if _should_include_message(message)
    ]

    if corrections_only:
        # Filter for correction patterns
        correction_pattern = (
            r"(no,? use|don't use|stop using|never use|that's wrong|that's incorrect|"
            r"not right|not correct|actually[,. ]|I meant|I said|I told you|"
            r"I already told|you should use|you need to use|use .+ not|not .+, use|remember:)"
        )
        messages = [m for m in messages if re.search(correction_pattern, m, re.IGNORECASE)]

    return messages


def should_include_message(text: str) -> bool:
    """Check if a message should be included in learning detection.

    Filters out system content like XML tags, JSON, tool results, and
    session continuations that should never be treated as user corrections.

    Used by both session file extraction and live capture (UserPromptSubmit hook).
    """
    # Skip empty lines
    if not text.strip():
        return False

    # Skip lines starting with certain patterns
    skip_patterns = [
        r"^<",              # XML tags (<task-notification>, <system-reminder>, etc.)
        r"^\[",             # Brackets
        r"^\{",             # JSON
        r"tool_result",
        r"tool_use_id",
        r"<command-",
        r"<task-notification>",
        r"<system-reminder>",
        r"This session is being continued",
        r"^Analysis:",
        r"^\*\*",           # Bold text
        r"^   -",           # Indented lists
    ]

    for pattern in skip_patterns:
        if re.search(pattern, text):
            return False

    return True


# Backward-compatible alias
_should_include_message = should_include_message


def extract_tool_rejections(session_file: Path) -> List[str]:
    """
    Return confirmed user tool rejections from a Codex session.

    Current supported Codex transcripts have no dedicated rejection record.
    Generic user messages, turn-aborted events, and tool output text are not
    treated as rejections because doing so would guess at schema semantics.

    Args:
        session_file: Path to the session JSONL file

    Returns:
        An empty list until a dedicated Codex rejection shape is confirmed
    """
    if not session_file.exists():
        return []
    parse_transcript(session_file)
    return []


# =============================================================================
# Tool execution error patterns
# =============================================================================

# EXCLUDE: generic agent guardrails and non-project-specific tool behavior
TOOL_ERROR_EXCLUDE_PATTERNS = [
    # Agent guardrails - system enforcing its rules
    r"File has not been read yet",
    r"exceeds maximum allowed tokens",
    r"InputValidationError",
    r"not valid JSON",
    r"The user doesn't want to proceed",  # User rejections handled separately
    # Global agent behavior issues - not project-specific
    r"unexpected EOF while looking for matching",  # Bash quoting
    r"EISDIR|illegal operation on a directory",    # File vs dir confusion
    r"syntax error.*eval",                          # Bash syntax errors
]

# PROJECT-SPECIFIC error patterns that reveal env/config/structure issues
# Format: (error_type, regex_pattern, suggested_guideline_template)
PROJECT_SPECIFIC_ERROR_PATTERNS = [
    # Connection/service errors - often reveal env/config issues
    ("connection_refused",
     r"Connection refused|ECONNREFUSED|connect ECONNREFUSED",
     "Check .env for service URLs - don't assume localhost"),
    ("env_undefined",
     r"(\w+_URL|DATABASE_URL|API_KEY|SECRET).*undefined|not set|is not defined",
     "Load .env file before accessing environment variables"),
    # Database-specific errors
    ("supabase_error",
     r"supabase|Supabase|SUPABASE",
     "Check SUPABASE_URL and SUPABASE_KEY in .env"),
    ("postgres_error",
     r"postgres|PostgreSQL|PGHOST|:5432|password authentication failed",
     "Check DATABASE_URL in .env for PostgreSQL connection"),
    ("redis_error",
     r"redis|REDIS|:6379",
     "Check REDIS_URL in .env for Redis connection"),
    # Path/module errors - reveal project structure
    ("module_not_found",
     r"ModuleNotFoundError|Cannot find module|No module named",
     "Check import paths - verify project structure"),
    ("venv_not_found",
     r"venv.*No such file|activate: No such file|\.venv.*not found",
     "Check virtual environment location"),
    # Port/service conflicts
    ("port_in_use",
     r"address already in use|EADDRINUSE|port.*already.*use",
     "Check if service is already running on this port"),
]


def extract_tool_errors(
    session_file: Path,
    project_specific_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Apply the existing technical error patterns to normalized Codex tool output.

    Args:
        session_file: Path to the session JSONL file
        project_specific_only: If True, only return errors matching project-specific patterns

    Returns:
        List of dicts with {error_type, content, project, timestamp, suggested_guideline}
    """
    if not session_file.exists():
        return []

    result = parse_transcript(session_file)
    if not result.supported:
        return []

    errors = []
    for tool_content in result.tool_outputs:
        if any(
            re.search(pattern, tool_content, re.IGNORECASE)
            for pattern in TOOL_ERROR_EXCLUDE_PATTERNS
        ):
            continue

        error_type = "unknown"
        suggested_guideline = None
        for etype, pattern, guideline in PROJECT_SPECIFIC_ERROR_PATTERNS:
            if re.search(pattern, tool_content, re.IGNORECASE):
                error_type = etype
                suggested_guideline = guideline
                break

        if project_specific_only and error_type == "unknown":
            continue

        errors.append({
            "error_type": error_type,
            "content": tool_content[:500],
            "project": result.cwd,
            "timestamp": result.timestamp,
            "suggested_guideline": suggested_guideline,
        })

    return errors


def aggregate_tool_errors(
    errors: List[Dict[str, Any]],
    min_occurrences: int = 2
) -> List[Dict[str, Any]]:
    """
    Group errors by type and return those with multiple occurrences.

    Only repeated errors are valuable for AGENTS.md guidance; one-offs are noise.

    Args:
        errors: List of error dicts from extract_tool_errors()
        min_occurrences: Minimum times an error type must occur

    Returns:
        List of aggregated errors with {error_type, count, suggested_guideline,
        confidence, sample_errors}
    """
    from collections import Counter

    # Count by error type
    type_counts = Counter(e["error_type"] for e in errors)

    # Group errors by type
    errors_by_type: Dict[str, List[Dict]] = {}
    for error in errors:
        etype = error["error_type"]
        if etype not in errors_by_type:
            errors_by_type[etype] = []
        errors_by_type[etype].append(error)

    # Build aggregated results for types meeting threshold
    aggregated = []
    for error_type, count in type_counts.items():
        if count < min_occurrences:
            continue

        samples = errors_by_type[error_type][:3]  # Keep up to 3 samples
        suggested_guideline = samples[0].get("suggested_guideline") if samples else None

        # Higher confidence for more occurrences
        if count >= 5:
            confidence = 0.90
        elif count >= 3:
            confidence = 0.85
        else:
            confidence = 0.70

        aggregated.append({
            "error_type": error_type,
            "count": count,
            "suggested_guideline": suggested_guideline,
            "confidence": confidence,
            "decay_days": 180,  # Tool error learnings decay slower
            "sample_errors": [s["content"][:200] for s in samples],
        })

    # Sort by count descending
    aggregated.sort(key=lambda x: x["count"], reverse=True)

    return aggregated
