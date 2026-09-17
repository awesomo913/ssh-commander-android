"""SSH Commander — player progress and achievement system.

Standalone module: no imports from engine.py or main.py.
Callers (UI, engine wrappers) import from here; this module never imports back.

Public API
----------
PlayerProgress          — dataclass holding all persistent player state
save_progress(p, path)  — write to ~/.ssh_commander/progress.json
load_progress(path)     — read from that file (creates fresh if missing)
update_streak(p)        — handle daily-streak bookkeeping
award_xp(p, xp)         — add XP, update level, return new total
check_achievements(p, event) → List[str] of newly-unlocked achievement IDs
get_player_summary(p)   → dict with level, title, xp, accuracy, etc.
ACHIEVEMENTS            — dict[id → AchievementDef] (read-only reference data)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XP / Level tables
# ---------------------------------------------------------------------------

#: XP required to *reach* each level (index 0 = level 1 threshold = 0 XP).
LEVEL_THRESHOLDS: List[int] = [
    0,       # level 1
    100,     # level 2
    250,     # level 3
    500,     # level 4
    1000,    # level 5
    2000,    # level 6
    4000,    # level 7
    7000,    # level 8
    11000,   # level 9
    16000,   # level 10
    22000,   # level 11
    30000,   # level 12
    40000,   # level 13
    52000,   # level 14
    66000,   # level 15
    82000,   # level 16
    100000,  # level 17
    120000,  # level 18
    142000,  # level 19
    166000,  # level 20 (soft cap — stays here beyond this)
]

#: Human-readable title for each level range.
_LEVEL_TITLES: List[tuple[int, int, str]] = [
    (1,  2,  "Newbie"),
    (3,  4,  "Script Kiddie"),
    (5,  6,  "Shell User"),
    (7,  8,  "Hacker"),
    (9,  10, "Pro Hacker"),
    (11, 12, "Elite"),
    (13, 14, "Red Team"),
    (15, 16, "Operator"),
    (17, 18, "Ghost"),
    (19, 20, "Legend"),
]

#: XP awarded per event type.
XP_TABLE: Dict[str, int] = {
    "learn_correct":     10,
    "challenge_correct": 20,
    "boss_step":         50,
}


def level_for_xp(xp: int) -> int:
    """Return the level (1-20) that corresponds to a given XP total."""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
        else:
            break
    return min(level, 20)


def level_title(level: int) -> str:
    """Return the display title for a level."""
    for lo, hi, title in _LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Legend"


def xp_to_next_level(xp: int) -> int:
    """XP needed to reach the next level (0 if already at max)."""
    current = level_for_xp(xp)
    if current >= 20:
        return 0
    return LEVEL_THRESHOLDS[current] - xp  # LEVEL_THRESHOLDS[current] = threshold for level current+1


# ---------------------------------------------------------------------------
# Achievement definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AchievementDef:
    id: str
    title: str
    description: str
    xp_bonus: int


ACHIEVEMENTS: Dict[str, AchievementDef] = {
    a.id: a
    for a in [
        AchievementDef("first_blood",    "First Blood",       "Get your first correct answer",                    25),
        AchievementDef("streak_5",       "On Fire",           "Answer 5 in a row correctly",                      50),
        AchievementDef("streak_10",      "Unstoppable",       "Answer 10 in a row correctly",                    100),
        AchievementDef("mastered_10",    "Getting Dangerous", "Master 10 commands (3+ correct each)",             75),
        AchievementDef("mastered_50",    "Shell Expert",      "Master 50 commands",                              200),
        AchievementDef("boss_first",     "Boss Slayer",       "Beat your first boss scenario",                   100),
        AchievementDef("all_categories", "Well Rounded",      "Get at least 10 correct in every category",       150),
        AchievementDef("daily_7",        "Dedicated",         "Maintain a 7-day daily streak",                   100),
        AchievementDef("daily_30",       "Obsessed",          "Maintain a 30-day daily streak",                  500),
        AchievementDef("level_5",        "Leveling Up",       "Reach level 5",                                    50),
        AchievementDef("level_10",       "Pro Status",        "Reach level 10",                                  150),
        AchievementDef("speed_demon",    "Speed Demon",       "Answer 5 challenge questions correctly in <30s total", 100),
        AchievementDef("no_hints",       "Purist",            "Beat a boss scenario without using any hints",    100),
        AchievementDef("all_bosses",     "Boss Hunter",       "Beat every boss scenario at least once",          300),
        AchievementDef("connect_master", "Connected",         "Master all commands in the connect category",     200),
        AchievementDef("tunnel_rat",     "Tunnel Rat",        "Master all commands in the tunnels category",     200),
    ]
}

# All boss scenario titles (must match engine.py BOSS_SCENARIOS exactly).
_ALL_BOSS_TITLES: Set[str] = {
    "Set Up a Fresh Pi",
    "Deploy a Script and Run It",
    "Fix a Known-Hosts Problem",
    "Forward a Database Port",
    "Sync a Project to a Remote Server",
    "Investigate a Security Incident",
    "Pivot Through a Jump Host",
    "Set Up a Covert Reverse Tunnel",
    "Exfiltrate Data via Encrypted Channel",
    "Blue Team: Hunt the Intruder",
    "Harden a Fresh VPS",
    "CTF: Reach the Hidden Service",
    "Deploy and Monitor a Remote Script",
    "Fix a Broken SSH Setup",
}

# All category names (must match commands.py CATEGORIES).
_ALL_CATEGORIES: Set[str] = {"connect", "files", "tunnels", "manage", "harden"}


# ---------------------------------------------------------------------------
# PlayerProgress dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlayerProgress:
    total_xp: int = 0
    level: int = 1
    commands_seen: Set[str] = field(default_factory=set)
    commands_mastered: Set[str] = field(default_factory=set)
    correct_total: int = 0
    incorrect_total: int = 0
    sessions_played: int = 0
    current_daily_streak: int = 0
    last_played_date: str = ""          # YYYY-MM-DD, empty = never played
    achievements_unlocked: Set[str] = field(default_factory=set)
    category_correct: Dict[str, int] = field(default_factory=dict)
    boss_scenarios_beaten: Set[str] = field(default_factory=set)
    # Internal: tracks per-command correct counts for mastery (not stored separately).
    _cmd_correct_counts: Dict[str, int] = field(default_factory=dict, repr=False)

    # Speed-demon tracker: rolling window for challenge mode fast answers.
    # List of elapsed_s floats for recent correct challenge answers (trimmed to 5).
    _recent_challenge_elapsed: List[float] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _to_json_safe(p: PlayerProgress) -> Dict[str, Any]:
    """Convert PlayerProgress to a JSON-serialisable dict."""
    return {
        "total_xp": p.total_xp,
        "level": p.level,
        "commands_seen": sorted(p.commands_seen),
        "commands_mastered": sorted(p.commands_mastered),
        "correct_total": p.correct_total,
        "incorrect_total": p.incorrect_total,
        "sessions_played": p.sessions_played,
        "current_daily_streak": p.current_daily_streak,
        "last_played_date": p.last_played_date,
        "achievements_unlocked": sorted(p.achievements_unlocked),
        "category_correct": p.category_correct,
        "boss_scenarios_beaten": sorted(p.boss_scenarios_beaten),
        "_cmd_correct_counts": p._cmd_correct_counts,
        "_recent_challenge_elapsed": p._recent_challenge_elapsed,
    }


def _from_json(data: Dict[str, Any]) -> PlayerProgress:
    """Reconstruct PlayerProgress from a deserialised JSON dict."""
    p = PlayerProgress()
    p.total_xp = int(data.get("total_xp", 0))
    p.level = int(data.get("level", 1))
    p.commands_seen = set(data.get("commands_seen", []))
    p.commands_mastered = set(data.get("commands_mastered", []))
    p.correct_total = int(data.get("correct_total", 0))
    p.incorrect_total = int(data.get("incorrect_total", 0))
    p.sessions_played = int(data.get("sessions_played", 0))
    p.current_daily_streak = int(data.get("current_daily_streak", 0))
    p.last_played_date = str(data.get("last_played_date", ""))
    p.achievements_unlocked = set(data.get("achievements_unlocked", []))
    p.category_correct = {str(k): int(v) for k, v in data.get("category_correct", {}).items()}
    p.boss_scenarios_beaten = set(data.get("boss_scenarios_beaten", []))
    p._cmd_correct_counts = {str(k): int(v) for k, v in data.get("_cmd_correct_counts", {}).items()}
    p._recent_challenge_elapsed = [float(x) for x in data.get("_recent_challenge_elapsed", [])]
    # Recompute level from XP to guard against save-file drift.
    p.level = level_for_xp(p.total_xp)
    return p


def _default_save_path() -> Path:
    return Path.home() / ".ssh_commander" / "progress.json"


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

def save_progress(progress: PlayerProgress, path: Optional[Path] = None) -> None:
    """Persist *progress* to disk as JSON.

    Creates ~/.ssh_commander/ if it does not exist.
    Silently logs on IOError rather than crashing the game.
    """
    target = Path(path) if path else _default_save_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = _to_json_safe(progress)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        log.debug("Progress saved to %s", target)
    except IOError as exc:
        log.warning("Could not save progress to %s: %s", target, exc)
    except Exception as exc:
        log.warning("Unexpected error saving progress: %s", exc)


def load_progress(path: Optional[Path] = None) -> PlayerProgress:
    """Load progress from disk.

    Returns a fresh PlayerProgress if the file is missing, empty, or corrupt.
    """
    target = Path(path) if path else _default_save_path()
    if not target.exists():
        log.debug("No save file found at %s — starting fresh", target)
        return PlayerProgress()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return _from_json(data)
    except (IOError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        log.warning("Could not load progress from %s (%s) — starting fresh", target, exc)
        return PlayerProgress()


# ---------------------------------------------------------------------------
# Daily streak
# ---------------------------------------------------------------------------

def update_streak(progress: PlayerProgress) -> None:
    """Advance or reset the daily streak based on today's date.

    - If last played yesterday  → streak +1
    - If last played today       → no change (already counted this session)
    - Anything else (first play, gap > 1 day) → reset to 1

    Always sets last_played_date to today.
    """
    today = date.today()
    today_str = today.isoformat()

    if progress.last_played_date:
        try:
            last = date.fromisoformat(progress.last_played_date)
        except ValueError:
            last = None

        if last is not None:
            delta = (today - last).days
            if delta == 0:
                return  # already updated today
            elif delta == 1:
                progress.current_daily_streak += 1
            else:
                progress.current_daily_streak = 1
        else:
            progress.current_daily_streak = 1
    else:
        progress.current_daily_streak = 1

    progress.last_played_date = today_str


# ---------------------------------------------------------------------------
# XP and levelling
# ---------------------------------------------------------------------------

def award_xp(progress: PlayerProgress, xp: int) -> int:
    """Add *xp* to progress.total_xp, recompute level, return new total."""
    if xp <= 0:
        return progress.total_xp
    progress.total_xp += xp
    progress.level = level_for_xp(progress.total_xp)
    return progress.total_xp


# ---------------------------------------------------------------------------
# Achievement checking
# ---------------------------------------------------------------------------

def check_achievements(progress: PlayerProgress, event: Dict[str, Any]) -> List[str]:
    """Evaluate which achievements were just unlocked by *event*.

    Returns a list of newly-unlocked achievement IDs (empty list if none).
    Also awards each achievement's XP bonus and appends the ID to
    progress.achievements_unlocked.

    *event* keys (all optional — missing keys are treated as falsy/zero):
        mode          str   "learn" | "challenge" | "boss"
        correct       bool  was the answer correct?
        streak        int   current answer streak at time of event
        category      str   command category for the answered question
        elapsed_s     float time taken on the most-recent challenge answer
        hints_used    int   hints used in the boss scenario (boss-complete event)
        scenario_title str  boss scenario title (boss-complete event)
        cmd           str   command string that was just answered correctly
    """
    newly_unlocked: List[str] = []
    already = progress.achievements_unlocked

    def _unlock(achievement_id: str) -> None:
        if achievement_id not in already:
            defn = ACHIEVEMENTS.get(achievement_id)
            if defn is None:
                log.warning("Unknown achievement ID: %s", achievement_id)
                return
            already.add(achievement_id)
            award_xp(progress, defn.xp_bonus)
            newly_unlocked.append(achievement_id)
            log.debug("Achievement unlocked: %s (+%d XP)", achievement_id, defn.xp_bonus)

    mode: str = event.get("mode", "")
    correct: bool = bool(event.get("correct", False))
    streak: int = int(event.get("streak", 0))
    category: str = event.get("category", "")
    elapsed_s: float = float(event.get("elapsed_s", 0.0))
    hints_used: int = int(event.get("hints_used", 0))
    scenario_title: str = event.get("scenario_title", "")
    cmd: str = event.get("cmd", "")

    # ── first_blood ──────────────────────────────────────────────────────────
    if correct and progress.correct_total >= 1:
        _unlock("first_blood")

    # ── streak_5 / streak_10 ─────────────────────────────────────────────────
    if streak >= 5:
        _unlock("streak_5")
    if streak >= 10:
        _unlock("streak_10")

    # ── mastered_10 / mastered_50 ────────────────────────────────────────────
    mastered_count = len(progress.commands_mastered)
    if mastered_count >= 10:
        _unlock("mastered_10")
    if mastered_count >= 50:
        _unlock("mastered_50")

    # ── boss_first ───────────────────────────────────────────────────────────
    if mode == "boss" and scenario_title and scenario_title in progress.boss_scenarios_beaten:
        _unlock("boss_first")

    # ── all_bosses ───────────────────────────────────────────────────────────
    if _ALL_BOSS_TITLES.issubset(progress.boss_scenarios_beaten):
        _unlock("all_bosses")

    # ── all_categories ───────────────────────────────────────────────────────
    if all(progress.category_correct.get(cat, 0) >= 10 for cat in _ALL_CATEGORIES):
        _unlock("all_categories")

    # ── daily_7 / daily_30 ───────────────────────────────────────────────────
    if progress.current_daily_streak >= 7:
        _unlock("daily_7")
    if progress.current_daily_streak >= 30:
        _unlock("daily_30")

    # ── level_5 / level_10 ───────────────────────────────────────────────────
    if progress.level >= 5:
        _unlock("level_5")
    if progress.level >= 10:
        _unlock("level_10")

    # ── speed_demon ──────────────────────────────────────────────────────────
    # Track a rolling list of the last 5 challenge correct answer times.
    if mode == "challenge" and correct and elapsed_s > 0:
        progress._recent_challenge_elapsed.append(elapsed_s)
        # Keep only the most recent 5 entries.
        if len(progress._recent_challenge_elapsed) > 5:
            progress._recent_challenge_elapsed = progress._recent_challenge_elapsed[-5:]
        if (
            len(progress._recent_challenge_elapsed) == 5
            and sum(progress._recent_challenge_elapsed) < 30.0
        ):
            _unlock("speed_demon")

    # ── no_hints ─────────────────────────────────────────────────────────────
    # Fired on boss-complete (scenario_title present) with hints_used == 0.
    if mode == "boss" and scenario_title and hints_used == 0 and scenario_title in progress.boss_scenarios_beaten:
        _unlock("no_hints")

    # ── connect_master / tunnel_rat ──────────────────────────────────────────
    # These are evaluated based on commands_mastered vs the full command bank.
    # We import lazily here to keep the module truly standalone at the top level;
    # the import is guarded so callers that do NOT have commands.py still work.
    try:
        from commands import COMMANDS  # type: ignore[import]
        connect_cmds = {c["cmd"] for c in COMMANDS if c["category"] == "connect"}
        tunnels_cmds = {c["cmd"] for c in COMMANDS if c["category"] == "tunnels"}
        if connect_cmds and connect_cmds.issubset(progress.commands_mastered):
            _unlock("connect_master")
        if tunnels_cmds and tunnels_cmds.issubset(progress.commands_mastered):
            _unlock("tunnel_rat")
    except ImportError:
        log.debug("commands.py not importable — skipping connect_master/tunnel_rat check")

    return newly_unlocked


# ---------------------------------------------------------------------------
# Convenience: record a correct answer
# ---------------------------------------------------------------------------

def record_correct(
    progress: PlayerProgress,
    cmd: str,
    category: str,
    mode: str,
    streak: int,
    elapsed_s: float = 0.0,
) -> None:
    """Update progress counters after a correct answer.

    This is a helper for callers that want one function to call instead of
    manually updating every field.  Does NOT call save_progress — callers
    decide when to persist.
    """
    progress.correct_total += 1
    progress.commands_seen.add(cmd)

    # Per-command mastery count.
    count = progress._cmd_correct_counts.get(cmd, 0) + 1
    progress._cmd_correct_counts[cmd] = count
    if count >= 3:
        progress.commands_mastered.add(cmd)

    # Per-category tally.
    progress.category_correct[category] = progress.category_correct.get(category, 0) + 1

    # Award XP based on mode.
    xp_key = f"{mode}_correct" if f"{mode}_correct" in XP_TABLE else "learn_correct"
    award_xp(progress, XP_TABLE[xp_key])


def record_incorrect(progress: PlayerProgress) -> None:
    """Update progress counters after an incorrect answer."""
    progress.incorrect_total += 1


def record_boss_step(progress: PlayerProgress) -> None:
    """Award XP for a single correct boss scenario step."""
    award_xp(progress, XP_TABLE["boss_step"])


def record_boss_complete(progress: PlayerProgress, scenario_title: str) -> None:
    """Mark a boss scenario as beaten."""
    progress.boss_scenarios_beaten.add(scenario_title)


# ---------------------------------------------------------------------------
# Player summary
# ---------------------------------------------------------------------------

def get_player_summary(progress: PlayerProgress) -> Dict[str, Any]:
    """Return a display-friendly dict for the UI to render."""
    total_answers = progress.correct_total + progress.incorrect_total
    accuracy_pct = (
        round(progress.correct_total / total_answers * 100, 1)
        if total_answers > 0
        else 0.0
    )
    return {
        "level": progress.level,
        "level_title": level_title(progress.level),
        "xp": progress.total_xp,
        "xp_to_next": xp_to_next_level(progress.total_xp),
        "accuracy_pct": accuracy_pct,
        "commands_mastered_count": len(progress.commands_mastered),
        "streak": progress.current_daily_streak,
        "achievements_unlocked_count": len(progress.achievements_unlocked),
    }
