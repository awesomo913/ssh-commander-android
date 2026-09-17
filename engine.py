"""SSH Commander — game engine (no UI dependencies).

Three modes:
  learn      — flashcard loop: show 'what', user types the command
  challenge  — timed terminal sim: show 'what', type command, score streaks
  boss       — multi-step scenario: 3-6 steps that must be solved in order

All functions return plain dicts — the UI reads them, never calls them back.
"""

import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from commands_expanded import COMMANDS, CATEGORIES, boss_eligible, by_category, by_level


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

BASE_POINTS = {"learn": 10, "challenge": 20, "boss": 50}
STREAK_BONUS = 5       # extra points per correct answer in current streak
TIME_BONUS_MAX = 15    # max extra points for speed in challenge mode
TIME_BONUS_CUTOFF = 8  # seconds — full bonus up to this, scales to 0 at 30s


def calc_score(mode: str, streak: int, elapsed_s: float = 0.0) -> int:
    base = BASE_POINTS.get(mode, 10)
    streak_pts = min(streak, 10) * STREAK_BONUS
    time_pts = 0
    if mode == "challenge":
        if elapsed_s <= TIME_BONUS_CUTOFF:
            time_pts = TIME_BONUS_MAX
        elif elapsed_s < 30:
            frac = 1.0 - (elapsed_s - TIME_BONUS_CUTOFF) / (30 - TIME_BONUS_CUTOFF)
            time_pts = int(TIME_BONUS_MAX * frac)
    return base + streak_pts + time_pts


# ---------------------------------------------------------------------------
# Answer checker
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Strip leading/trailing whitespace and collapse internal spaces."""
    return " ".join(text.lower().split())


def _cmd_to_regex(cmd_template: str) -> re.Pattern:
    """Convert a command template with <placeholders> to a regex matching filled-in versions."""
    escaped = re.escape(_normalise(cmd_template))
    # Use lambda so re.sub doesn't process \S as an escape sequence in replacement
    pattern = re.sub(r'<[^>]+>', lambda _: r'\S+', escaped)
    return re.compile(pattern)


def check_answer(user_input: str, cmd: Dict) -> Tuple[bool, str]:
    """Return (correct, feedback_message).

    Accepts:
    - Template with placeholders filled in (e.g. 'ssh pi@host' for 'ssh <user>@<host>')
    - Template with placeholders as-is
    - Syntax example
    - Non-placeholder tokens only (verb + flags, no values)
    - Any alias
    """
    typed = _normalise(user_input)
    if not typed:
        return False, "Type the command and press Enter."

    # 1. Regex match: template with placeholders replaced by \S+
    tmpl_rx = _cmd_to_regex(cmd["cmd"])
    if tmpl_rx.fullmatch(typed):
        return True, "Correct!"

    # 2. Regex match for each alias
    for alias in cmd["aliases"]:
        if _cmd_to_regex(alias).fullmatch(typed):
            return True, "Correct!"

    # 3. Exact match on syntax example or literal template
    accepted = {
        _normalise(cmd["cmd"]),
        _normalise(cmd["syntax"]),
    }
    accepted.update(_normalise(a) for a in cmd["aliases"])
    if typed in accepted:
        return True, "Correct!"

    # 4. Non-placeholder tokens only (user omitted the placeholder values)
    cmd_tokens = _normalise(cmd["cmd"]).split()
    non_placeholder = [t for t in cmd_tokens if not re.fullmatch(r'<[^>]+>', t)]
    if typed.split() == non_placeholder and len(non_placeholder) >= 2:
        return True, "Correct! (placeholders omitted — that's fine)"

    # Hint
    user_tokens = typed.split()
    if user_tokens and cmd_tokens and user_tokens[0] != cmd_tokens[0]:
        hint = f"Starts with '{cmd_tokens[0]}'"
    else:
        hint = f"Expected: {cmd['cmd']}"

    return False, f"Not quite. {hint}"


# ---------------------------------------------------------------------------
# Learn mode
# ---------------------------------------------------------------------------

@dataclass
class LearnSession:
    category: Optional[str]      # None = all categories
    level: Optional[int]          # None = all levels
    deck: List[Dict] = field(default_factory=list)
    index: int = 0
    correct: int = 0
    incorrect: int = 0
    streak: int = 0
    total_score: int = 0
    started_at: float = field(default_factory=time.time)


def learn_start(
    category: Optional[str] = None,
    level: Optional[int] = None,
    shuffle: bool = True,
) -> LearnSession:
    pool = list(COMMANDS)
    if category:
        pool = [c for c in pool if c["category"] == category]
    if level:
        pool = [c for c in pool if c["level"] == level]
    if shuffle:
        random.shuffle(pool)
    return LearnSession(category=category, level=level, deck=pool)


def learn_card(session: LearnSession) -> Dict[str, Any]:
    """Return the current flashcard prompt, or completion summary."""
    if session.index >= len(session.deck):
        return {
            "done": True,
            "correct": session.correct,
            "incorrect": session.incorrect,
            "score": session.total_score,
            "accuracy": round(session.correct / max(1, session.correct + session.incorrect) * 100),
            "elapsed_s": int(time.time() - session.started_at),
        }
    card = session.deck[session.index]
    return {
        "done": False,
        "card_num": session.index + 1,
        "total": len(session.deck),
        "category": card["category"],
        "level": card["level"],
        "prompt": card["what"],
        "streak": session.streak,
        "score": session.total_score,
    }


def learn_submit(session: LearnSession, user_input: str) -> Dict[str, Any]:
    """Process answer for current card. Mutates session. Returns result dict."""
    if session.index >= len(session.deck):
        return {"error": "Session complete — call learn_card to see summary"}

    card = session.deck[session.index]
    correct, feedback = check_answer(user_input, card)

    if correct:
        session.streak += 1
        pts = calc_score("learn", session.streak)
        session.correct += 1
        session.total_score += pts
    else:
        session.streak = 0
        pts = 0
        session.incorrect += 1

    session.index += 1

    return {
        "correct": correct,
        "feedback": feedback,
        "expected": card["cmd"],
        "syntax": card["syntax"],
        "what": card["what"],
        "points_earned": pts,
        "streak": session.streak,
        "score": session.total_score,
    }


# ---------------------------------------------------------------------------
# Challenge mode
# ---------------------------------------------------------------------------

@dataclass
class ChallengeSession:
    deck: List[Dict]
    index: int = 0
    correct: int = 0
    incorrect: int = 0
    streak: int = 0
    total_score: int = 0
    card_start: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    lives: int = 3


def challenge_start(
    category: Optional[str] = None,
    level: Optional[int] = None,
    lives: int = 3,
) -> ChallengeSession:
    pool = [c for c in COMMANDS if c["level"] in (1, 2)] if not level else by_level(level)
    if category:
        pool = [c for c in pool if c["category"] == category]
    random.shuffle(pool)
    return ChallengeSession(deck=pool, lives=lives)


def challenge_card(session: ChallengeSession) -> Dict[str, Any]:
    if session.lives <= 0:
        return {
            "done": True, "reason": "no_lives",
            "correct": session.correct, "score": session.total_score,
        }
    if session.index >= len(session.deck):
        return {
            "done": True, "reason": "completed",
            "correct": session.correct, "score": session.total_score,
            "elapsed_s": int(time.time() - session.started_at),
        }
    card = session.deck[session.index]
    session.card_start = time.time()
    return {
        "done": False,
        "card_num": session.index + 1,
        "total": len(session.deck),
        "category": card["category"],
        "level": card["level"],
        "prompt": card["what"],
        "lives": session.lives,
        "streak": session.streak,
        "score": session.total_score,
    }


def challenge_submit(session: ChallengeSession, user_input: str) -> Dict[str, Any]:
    if session.index >= len(session.deck) or session.lives <= 0:
        return {"error": "Session over"}

    card = session.deck[session.index]
    elapsed = time.time() - session.card_start
    correct, feedback = check_answer(user_input, card)

    if correct:
        session.streak += 1
        pts = calc_score("challenge", session.streak, elapsed)
        session.correct += 1
        session.total_score += pts
        session.index += 1
    else:
        session.streak = 0
        pts = 0
        session.incorrect += 1
        session.lives -= 1

    return {
        "correct": correct,
        "feedback": feedback,
        "expected": card["cmd"],
        "syntax": card["syntax"],
        "elapsed_s": round(elapsed, 1),
        "points_earned": pts,
        "streak": session.streak,
        "lives": session.lives,
        "score": session.total_score,
    }


# ---------------------------------------------------------------------------
# Boss mode — multi-step scenarios
# ---------------------------------------------------------------------------

BOSS_SCENARIOS = [
    {
        "title": "Set Up a Fresh Pi",
        "story": "You just got a Raspberry Pi. Set it up for passwordless SSH access.",
        "steps": [
            {"hint": "Generate a new ed25519 key pair", "cmd_key": "ssh-keygen -t ed25519 -C <comment>"},
            {"hint": "Copy your public key to the Pi at 192.168.1.100", "cmd_key": "ssh-copy-id <user>@<host>"},
            {"hint": "Verify you can log in with your key", "cmd_key": "ssh <user>@<host>"},
            {"hint": "Check the Pi's SSH server config", "cmd_key": "sudo nano /etc/ssh/sshd_config"},
            {"hint": "Restart the SSH server to apply changes", "cmd_key": "sudo systemctl restart sshd"},
        ],
    },
    {
        "title": "Deploy a Script and Run It",
        "story": "You need to copy a Python script to a remote server and start it in the background.",
        "steps": [
            {"hint": "Copy server.py to /home/pi/ on the remote", "cmd_key": "scp <file> <user>@<host>:<dest>"},
            {"hint": "SSH into the remote machine", "cmd_key": "ssh <user>@<host>"},
            {"hint": "Start the script so it keeps running after you disconnect", "cmd_key": "ssh <user>@<host> 'nohup <cmd> &'"},
        ],
    },
    {
        "title": "Fix a Known-Hosts Problem",
        "story": "The server was reinstalled and now SSH is blocking you with a 'host key changed' warning.",
        "steps": [
            {"hint": "Remove the old host key for 192.168.1.100", "cmd_key": "ssh-keygen -R <host>"},
            {"hint": "Fix your .ssh directory permissions", "cmd_key": "chmod 700 ~/.ssh"},
            {"hint": "Fix your private key permissions", "cmd_key": "chmod 600 ~/.ssh/id_ed25519"},
            {"hint": "Re-copy your key to the server", "cmd_key": "ssh-copy-id <user>@<host>"},
        ],
    },
    {
        "title": "Forward a Database Port",
        "story": "A PostgreSQL database runs on port 5432 on your remote server. "
                 "You want to connect to it from your local machine as if it were local.",
        "steps": [
            {"hint": "Create a local tunnel: local port 5432 → remote localhost:5432 (background, no shell)",
             "cmd_key": "ssh -N -L <localport>:<remotehost>:<remoteport> <user>@<host>"},
        ],
    },
    {
        "title": "Sync a Project to a Remote Server",
        "story": "You have a local ./project/ folder you want to keep in sync with /home/pi/project/ on the server.",
        "steps": [
            {"hint": "Do the initial sync", "cmd_key": "rsync -avz <src> <user>@<host>:<dest>"},
            {"hint": "Sync again but also delete files removed locally", "cmd_key": "rsync -avz --delete <src> <user>@<host>:<dest>"},
        ],
    },
    {
        "title": "Investigate a Security Incident",
        "story": "You suspect someone has been trying to brute-force SSH into your server.",
        "steps": [
            {"hint": "Check recent logins", "cmd_key": "last"},
            {"hint": "See who is logged in right now", "cmd_key": "who"},
            {"hint": "Check the last 50 SSH server log lines", "cmd_key": "sudo journalctl -u sshd -n 50"},
            {"hint": "Check fail2ban status for SSH", "cmd_key": "sudo fail2ban-client status sshd"},
        ],
    },
]

try:
    from boss_scenarios_v2 import NEW_BOSS_SCENARIOS
    BOSS_SCENARIOS.extend(NEW_BOSS_SCENARIOS)
except ImportError:
    pass


def _find_cmd_for_key(key: str) -> Optional[Dict]:
    """Look up a command entry by its cmd template."""
    for c in COMMANDS:
        if c["cmd"] == key:
            return c
    return None


@dataclass
class BossSession:
    scenario: Dict
    steps: List[Dict]          # resolved command dicts for each step
    step_index: int = 0
    correct_steps: int = 0
    total_score: int = 0
    hints_used: int = 0
    started_at: float = field(default_factory=time.time)


def boss_start(scenario_index: Optional[int] = None) -> BossSession:
    if scenario_index is None:
        scenario = random.choice(BOSS_SCENARIOS)
    else:
        scenario = BOSS_SCENARIOS[scenario_index % len(BOSS_SCENARIOS)]

    steps = []
    for s in scenario["steps"]:
        cmd = _find_cmd_for_key(s["cmd_key"])
        if cmd:
            steps.append({**cmd, "hint": s["hint"]})
    return BossSession(scenario=scenario, steps=steps)


def boss_state(session: BossSession) -> Dict[str, Any]:
    if session.step_index >= len(session.steps):
        return {
            "done": True,
            "title": session.scenario["title"],
            "score": session.total_score,
            "steps": len(session.steps),
            "hints_used": session.hints_used,
            "elapsed_s": int(time.time() - session.started_at),
        }
    step = session.steps[session.step_index]
    return {
        "done": False,
        "title": session.scenario["title"],
        "story": session.scenario["story"],
        "step": session.step_index + 1,
        "total_steps": len(session.steps),
        "hint": step["hint"],
        "category": step["category"],
        "score": session.total_score,
    }


def boss_submit(session: BossSession, user_input: str, use_hint: bool = False) -> Dict[str, Any]:
    if session.step_index >= len(session.steps):
        return {"error": "Boss already defeated!"}

    step = session.steps[session.step_index]

    if use_hint:
        session.hints_used += 1
        return {"hint": f"Command starts with: {step['cmd'].split()[0]}  —  {step['what']}"}

    correct, feedback = check_answer(user_input, step)
    if correct:
        pts = calc_score("boss", session.correct_steps)
        session.correct_steps += 1
        session.total_score += pts
        session.step_index += 1
        return {
            "correct": True,
            "feedback": feedback,
            "points_earned": pts,
            "step": session.step_index,
            "total_steps": len(session.steps),
            "score": session.total_score,
        }

    return {
        "correct": False,
        "feedback": feedback,
        "expected": step["cmd"],
        "what": step["what"],
    }


def boss_scenarios_list() -> List[Dict[str, Any]]:
    return [
        {
            "index": i,
            "title": s["title"],
            "story": s["story"],
            "steps": len(s["steps"]),
        }
        for i, s in enumerate(BOSS_SCENARIOS)
    ]
