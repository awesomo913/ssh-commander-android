#!/usr/bin/env python3
"""SSH Commander — Kivy port for Android.

Three modes wired to the same engine as main_v2.py:
  Learn     — flashcard loop, all categories or filtered
  Challenge — timed, lose a life per wrong answer
  Boss      — multi-step scenarios, must solve in order

No .kv file — all layout defined in Python.
"""

__version__ = "1.0.0"

import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress module (optional)
# ---------------------------------------------------------------------------

try:
    from progress import (
        load_progress, save_progress, award_xp, level_for_xp,
        check_achievements, get_player_summary, update_streak,
        record_correct, record_boss_step, record_boss_complete,
        ACHIEVEMENTS,
    )
    PROGRESS_AVAILABLE = True
except ImportError:
    PROGRESS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Engine imports
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(__file__))

from commands_expanded import CATEGORIES, COMMANDS
from engine import (
    BossSession, ChallengeSession, LearnSession,
    boss_scenarios_list, boss_start, boss_state, boss_submit,
    challenge_card, challenge_start, challenge_submit,
    learn_card, learn_start, learn_submit,
)

# ---------------------------------------------------------------------------
# Kivy environment config — must happen before any kivy import
# ---------------------------------------------------------------------------

os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle

# ---------------------------------------------------------------------------
# Colour palette (RGBA tuples, 0-1 range)
# ---------------------------------------------------------------------------

BG      = (0.051, 0.067, 0.090, 1)   # #0d1117
BG2     = (0.086, 0.106, 0.133, 1)   # #161b22
BG3     = (0.129, 0.149, 0.176, 1)   # #21262d
FG      = (0.902, 0.929, 0.953, 1)   # #e6edf3
FG2     = (0.545, 0.580, 0.620, 1)   # #8b949e
GREEN   = (0.247, 0.729, 0.314, 1)   # #3fb950
RED     = (0.973, 0.318, 0.286, 1)   # #f85149
YELLOW  = (0.824, 0.600, 0.133, 1)   # #d29922
AMBER   = (0.890, 0.627, 0.251, 1)   # #e3a040
BLUE    = (0.345, 0.651, 1.000, 1)   # #58a6ff
PURPLE  = (0.737, 0.549, 1.000, 1)   # #bc8cff
DARK_AMBER = (0.176, 0.122, 0.000, 1)

BADGE_COLORS: Dict[str, tuple] = {
    "connect": BLUE,
    "files":   GREEN,
    "tunnels": PURPLE,
    "manage":  YELLOW,
    "harden":  RED,
}

# ---------------------------------------------------------------------------
# Hacker tips shown on main menu
# ---------------------------------------------------------------------------

HACKER_TIPS: List[str] = [
    "TIP  Disable password auth once key auth works: set PasswordAuthentication no in sshd_config",
    "TIP  Use ed25519 keys — they're shorter, faster, and more secure than RSA-2048",
    "TIP  Run sshd on a non-standard port to cut 90% of automated brute-force noise",
    "TIP  Add AllowUsers in sshd_config — only named accounts can log in via SSH",
    "TIP  Set LoginGraceTime 20 to drop connection attempts that stall at the password prompt",
]

# ---------------------------------------------------------------------------
# Hacker notes fallback dict
# ---------------------------------------------------------------------------

HACKER_NOTES: Dict[str, str] = {
    "ssh <user>@<host>": "Default port 22 is scanned constantly. Change it in sshd_config if the server is internet-facing.",
    "ssh-keygen -t ed25519 -C <comment>": "ed25519 keys are smaller and faster than RSA-4096. Never share the private key — only the .pub file.",
    "ssh-copy-id <user>@<host>": "This appends your public key to ~/.ssh/authorized_keys on the remote. Once done, you can disable password auth entirely.",
    "chmod 600 ~/.ssh/id_ed25519": "SSH WILL refuse to use a private key with loose permissions. 600 means only you can read/write it.",
    "chmod 700 ~/.ssh": "700 means only you can enter the .ssh directory. Other users cannot even list its contents.",
    "rsync -avz <src> <user>@<host>:<dest>": "rsync computes a rolling checksum — only the parts of files that changed are transmitted.",
    "sudo nano /etc/ssh/sshd_config": "Always set PasswordAuthentication no and PermitRootLogin no once key-based auth is confirmed working.",
    "sudo systemctl restart sshd": "Config changes only take effect after a restart. Use 'sshd -t' first to test the config without reloading.",
    "ssh-keygen -R <host>": "The REMOTE_HOST_IDENTIFICATION_HAS_CHANGED error is a security warning — only suppress it when you know the server was rebuilt.",
    "last": "login records come from /var/log/wtmp. They can be tampered with; cross-check with journalctl for forensic work.",
    "sudo fail2ban-client status sshd": "fail2ban watches auth.log and bans IPs after N failures. Default is 5 attempts — lower it for public servers.",
}


def get_hacker_note(cmd_template: str) -> str:
    """Return hacker note for a command template. Falls back gracefully."""
    for entry in COMMANDS:
        if entry["cmd"] == cmd_template:
            note = entry.get("hacker_note")
            if note:
                return note
            break
    note = HACKER_NOTES.get(cmd_template)
    if note:
        return note
    return "Always test changes on a non-production server first. SSH misconfigurations can lock you out."


def calc_grade(accuracy: int) -> tuple:
    """Return (letter, color_tuple) based on accuracy percentage."""
    if accuracy >= 95:
        return "S", GREEN
    if accuracy >= 85:
        return "A", BLUE
    if accuracy >= 70:
        return "B", PURPLE
    if accuracy >= 50:
        return "C", YELLOW
    return "D", RED


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def _bg_rect(widget: Widget, color: tuple) -> None:
    """Paint a solid background on a widget using canvas instructions."""
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, v: setattr(rect, "pos", v),
                size=lambda w, v: setattr(rect, "size", v))


def _make_label(text: str = "", color: tuple = FG, font_size: int = 14,
                bold: bool = False, **kw) -> Label:
    """Create a label with sensible defaults for our dark theme."""
    kw.setdefault("size_hint_y", None)
    kw.setdefault("markup", False)
    lbl = Label(
        text=text,
        color=color,
        font_size=dp(font_size),
        bold=bold,
        text_size=(None, None),
        halign=kw.pop("halign", "left"),
        valign=kw.pop("valign", "middle"),
        **kw,
    )
    lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(8)))
    return lbl


def _make_button(text: str, callback, color: tuple = FG,
                 bg_color: tuple = BG3, min_height: int = 50,
                 font_size: int = 14, bold: bool = False) -> Button:
    """Create a touch-friendly button with our dark theme."""
    btn = Button(
        text=text,
        color=color,
        background_normal="",
        background_color=bg_color,
        font_size=dp(font_size),
        bold=bold,
        size_hint=(1, None),
        height=dp(min_height),
    )
    btn.bind(on_release=lambda b: callback())
    return btn


def _make_text_input(hint: str = "", fg_color: tuple = GREEN) -> TextInput:
    """Create a monospace TextInput for command entry."""
    ti = TextInput(
        hint_text=hint,
        hint_text_color=FG2,
        foreground_color=fg_color,
        background_color=BG3,
        cursor_color=fg_color,
        font_name="Roboto",
        font_size=dp(15),
        multiline=False,
        size_hint=(1, None),
        height=dp(50),
        padding=[dp(10), dp(10)],
    )
    return ti


def _colored_box(color: tuple, height: int = 2) -> Widget:
    """Thin horizontal divider line."""
    w = Widget(size_hint=(1, None), height=dp(height))
    _bg_rect(w, color)
    return w


def _make_badge(category: str, level: int) -> Label:
    """Category + level badge label."""
    col = BADGE_COLORS.get(category, FG2)
    lbl = Label(
        text=f"  [{category.upper()}]  LVL {level}  ",
        color=BG,
        font_size=dp(11),
        bold=True,
        size_hint=(None, None),
        padding=[dp(6), dp(4)],
    )
    lbl.bind(texture_size=lambda w, v: (
        setattr(w, "width", v[0] + dp(12)),
        setattr(w, "height", v[1] + dp(8)),
    ))
    _bg_rect(lbl, col)
    return lbl


def _scroll_wrap(content: Widget) -> ScrollView:
    """Wrap content in a vertical ScrollView."""
    sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
    sv.add_widget(content)
    return sv


def _card_box() -> BoxLayout:
    """Return a vertical BoxLayout with standard padding, suitable for screen content."""
    box = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        padding=[dp(12), dp(8)],
        spacing=dp(8),
    )
    box.bind(minimum_height=box.setter("height"))
    return box


def _panel(bg_color: tuple, border_color: Optional[tuple] = None):
    """Return (outer, inner) BoxLayouts. Outer has the border color; inner has the fill color."""
    outer = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(2))
    outer.bind(minimum_height=outer.setter("height"))
    if border_color:
        _bg_rect(outer, border_color)
    inner = BoxLayout(orientation="vertical", size_hint_y=None, padding=[dp(10), dp(6)])
    inner.bind(minimum_height=inner.setter("height"))
    _bg_rect(inner, bg_color)
    outer.add_widget(inner)
    return outer, inner


# ---------------------------------------------------------------------------
# Achievement popup
# ---------------------------------------------------------------------------

def show_achievement_popup(achievement: Dict) -> None:
    """Show a brief auto-dismissing Popup for an unlocked achievement."""
    title_txt = achievement.get("title", "Achievement")
    desc_txt = achievement.get("description", "")

    content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
    _bg_rect(content, BG2)

    hdr = _make_label("  ACHIEVEMENT UNLOCKED", color=GREEN, font_size=11, bold=True)
    content.add_widget(hdr)
    content.add_widget(_colored_box(GREEN))
    content.add_widget(_make_label(f"  {title_txt}", color=FG, font_size=14, bold=True))
    content.add_widget(_make_label(f"  {desc_txt}", color=FG2, font_size=11))

    popup = Popup(
        title="",
        content=content,
        size_hint=(0.85, None),
        height=dp(160),
        separator_height=0,
        background="",
        background_color=(0, 0, 0, 0),
    )
    # Green border via title_color trick is unavailable in pure Kivy; use outline on content
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), 2.5)


# ---------------------------------------------------------------------------
# WHY THIS MATTERS panel
# ---------------------------------------------------------------------------

def make_hacker_note_panel(expected: str, syntax: str, hacker_note: str) -> BoxLayout:
    """Build the amber 'WHY THIS MATTERS' info panel shown on wrong answers."""
    outer, inner = _panel(DARK_AMBER, border_color=AMBER)

    hdr = _make_label("  WHY THIS MATTERS", color=AMBER, font_size=11, bold=True)
    inner.add_widget(hdr)
    inner.add_widget(_colored_box(AMBER))

    cmd_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6))
    cmd_row.add_widget(_make_label("Command:", color=FG2, font_size=11, size_hint_x=0.25))
    cmd_row.add_widget(_make_label(expected, color=AMBER, font_size=12, bold=True, size_hint_x=0.75))
    inner.add_widget(cmd_row)

    ex_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6))
    ex_row.add_widget(_make_label("Example:", color=FG2, font_size=11, size_hint_x=0.25))
    ex_row.add_widget(_make_label(syntax, color=FG, font_size=11, size_hint_x=0.75))
    inner.add_widget(ex_row)

    inner.add_widget(_colored_box(AMBER))
    note_lbl = _make_label(f"  {hacker_note}", color=FG, font_size=11)
    note_lbl.text_size = (Window.width - dp(60), None)
    note_lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(8)))
    inner.add_widget(note_lbl)

    return outer


# ---------------------------------------------------------------------------
# Header bar widget
# ---------------------------------------------------------------------------

def make_header(left_text: str, right_text: str,
                left_color: tuple = FG2, right_color: tuple = FG2) -> BoxLayout:
    hdr = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(44))
    _bg_rect(hdr, BG2)
    left = _make_label(f"  {left_text}", color=left_color, font_size=11)
    right = _make_label(right_text, color=right_color, font_size=11, halign="right")
    hdr.add_widget(left)
    hdr.add_widget(right)
    return hdr


# ---------------------------------------------------------------------------
# MenuScreen
# ---------------------------------------------------------------------------

class MenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._tip_text = random.choice(HACKER_TIPS)
        self._build()

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)

        root = BoxLayout(orientation="vertical")

        # Scrollable inner content
        content = _card_box()

        app = App.get_running_app()

        # ── Player banner ────────────────────────────────────────────────
        if PROGRESS_AVAILABLE and app._progress is not None:
            try:
                summary = get_player_summary(app._progress)
                banner, inner = _panel(BG2, border_color=BG3)
                lvl = summary.get("level", 1)
                title = summary.get("level_title", "Newcomer")
                xp_cur = summary.get("xp", 0)
                xp_next = summary.get("xp_to_next", 100)
                streak_n = summary.get("streak", 0)
                streak_col = GREEN if streak_n >= 3 else (YELLOW if streak_n >= 1 else FG2)

                row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
                row.add_widget(_make_label(
                    f"LVL {lvl}  {title}", color=GREEN, font_size=13, bold=True,
                    size_hint_x=0.6))
                row.add_widget(_make_label(
                    f"STREAK {streak_n}d", color=streak_col, font_size=11,
                    halign="right", size_hint_x=0.4))
                inner.add_widget(row)

                xp_lbl = _make_label(f"XP  {xp_cur} / {xp_next}", color=FG2, font_size=10)
                inner.add_widget(xp_lbl)

                pb = ProgressBar(
                    max=max(xp_next, 1),
                    value=xp_cur,
                    size_hint=(1, None),
                    height=dp(8),
                )
                inner.add_widget(pb)
                content.add_widget(banner)
            except Exception as exc:
                log.warning("Player banner error: %s", exc)

        # ── Title ────────────────────────────────────────────────────────
        content.add_widget(Widget(size_hint_y=None, height=dp(12)))
        content.add_widget(_make_label(
            "SSH COMMANDER", color=GREEN, font_size=30, bold=True, halign="center"))
        content.add_widget(_make_label(
            "Master the shell. One command at a time.",
            color=FG2, font_size=12, halign="center"))
        content.add_widget(_colored_box(BG3))
        content.add_widget(_make_label(
            f"{len(COMMANDS)} commands  •  {len(CATEGORIES)} categories  •  3 modes",
            color=FG2, font_size=11, halign="center"))
        content.add_widget(Widget(size_hint_y=None, height=dp(8)))

        # ── Mode buttons ─────────────────────────────────────────────────
        for label, screen_name, color in [
            ("LEARN",     "learn_menu",     GREEN),
            ("CHALLENGE", "challenge_menu", YELLOW),
            ("BOSS MODE", "boss_menu",      RED),
        ]:
            btn = _make_button(label, lambda sn=screen_name: self._go(sn),
                               color=color, bg_color=BG3,
                               min_height=56, font_size=15, bold=True)
            content.add_widget(btn)

        content.add_widget(_colored_box(BG3))

        # ── Hacker Tip ───────────────────────────────────────────────────
        tip_outer, tip_inner = _panel(BG2, border_color=BG3)
        tip_inner.add_widget(_make_label(
            self._tip_text, color=FG2, font_size=11))
        content.add_widget(tip_outer)
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

    def _go(self, screen_name: str) -> None:
        self.manager.transition = SlideTransition(direction="left")
        # Trigger a rebuild on the target screen before switching
        target = self.manager.get_screen(screen_name)
        if hasattr(target, "_build"):
            target._build()
        self.manager.current = screen_name

    def on_pre_enter(self) -> None:
        self._build()


# ---------------------------------------------------------------------------
# LearnMenuScreen
# ---------------------------------------------------------------------------

class LearnMenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._cat_selected = "all"
        self._lvl_selected = "all"
        self._build()

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)

        root = BoxLayout(orientation="vertical")
        content = _card_box()

        content.add_widget(_make_label("LEARN MODE", color=GREEN, font_size=20, bold=True, halign="center"))
        content.add_widget(_make_label(
            "Flashcards — see the description, type the command",
            color=FG2, font_size=12, halign="center"))
        content.add_widget(_colored_box(BG3))

        # Category selector
        content.add_widget(_make_label("Category", color=FG2, font_size=12))
        cat_grid = GridLayout(cols=3, size_hint_y=None, spacing=dp(6))
        cat_grid.bind(minimum_height=cat_grid.setter("height"))
        for cat in ["all"] + CATEGORIES:
            is_sel = (cat == self._cat_selected)
            btn = _make_button(
                cat,
                lambda c=cat: self._select_cat(c),
                color=BG if is_sel else FG2,
                bg_color=BLUE if is_sel else BG3,
                min_height=44,
                font_size=12,
            )
            cat_grid.add_widget(btn)
        content.add_widget(cat_grid)

        # Level selector
        content.add_widget(_make_label("Level", color=FG2, font_size=12))
        lvl_grid = GridLayout(cols=4, size_hint_y=None, spacing=dp(6))
        lvl_grid.bind(minimum_height=lvl_grid.setter("height"))
        for lvl in ["all", "1", "2", "3"]:
            disp = "All" if lvl == "all" else f"Lv{lvl}"
            is_sel = (lvl == self._lvl_selected)
            btn = _make_button(
                disp,
                lambda l=lvl: self._select_lvl(l),
                color=BG if is_sel else FG2,
                bg_color=GREEN if is_sel else BG3,
                min_height=44,
                font_size=12,
            )
            lvl_grid.add_widget(btn)
        content.add_widget(lvl_grid)

        content.add_widget(Widget(size_hint_y=None, height=dp(8)))
        content.add_widget(_make_button("START", self._start,
                                        color=BG, bg_color=GREEN,
                                        min_height=56, font_size=16, bold=True))
        content.add_widget(_make_button("Back", self._back,
                                        color=FG2, bg_color=BG2, min_height=48))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

    def _select_cat(self, cat: str) -> None:
        self._cat_selected = cat
        self._build()

    def _select_lvl(self, lvl: str) -> None:
        self._lvl_selected = lvl
        self._build()

    def _start(self) -> None:
        cat = None if self._cat_selected == "all" else self._cat_selected
        lvl = None if self._lvl_selected == "all" else int(self._lvl_selected)
        app = App.get_running_app()
        app._session = learn_start(category=cat, level=lvl)
        app._session_xp_start = app._progress.total_xp if app._progress else 0
        app._session_achievements = []
        card_screen: LearnCardScreen = self.manager.get_screen("learn_card")
        card_screen._build()
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "learn_card"

    def _back(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# LearnCardScreen
# ---------------------------------------------------------------------------

class LearnCardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._submit_locked = False

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._submit_locked = False

        app = App.get_running_app()
        s: LearnSession = app._session
        state = learn_card(s)

        if state["done"]:
            rs: ResultScreen = self.manager.get_screen("result")
            rs._build("LEARN COMPLETE", state)
            self.manager.transition = SlideTransition(direction="left")
            self.manager.current = "result"
            return

        root = BoxLayout(orientation="vertical")

        # Header
        hdr = make_header(
            f"LEARN  Card {state['card_num']}/{state['total']}  Streak {state['streak']}",
            f"Score: {state['score']}",
            left_color=FG2, right_color=GREEN,
        )
        root.add_widget(hdr)
        root.add_widget(_colored_box(BG3))

        # Scrollable content
        content = _card_box()

        # Badge
        badge_row = BoxLayout(size_hint_y=None, height=dp(36))
        badge_row.add_widget(_make_badge(state["category"], state["level"]))
        badge_row.add_widget(Widget())  # spacer
        content.add_widget(badge_row)

        # Prompt panel
        p_outer, p_inner = _panel(BG2, border_color=BG3)
        prompt_lbl = _make_label(state["prompt"], color=FG, font_size=14,
                                  bold=True, halign="center")
        prompt_lbl.text_size = (Window.width - dp(48), None)
        prompt_lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(12)))
        p_inner.add_widget(prompt_lbl)
        content.add_widget(p_outer)

        # Input label
        content.add_widget(_make_label("Type the command:", color=FG2, font_size=11))

        # Text input
        self._entry = _make_text_input("command here...", fg_color=GREEN)
        self._entry.bind(on_text_validate=lambda ti: self._submit())
        content.add_widget(self._entry)
        content.add_widget(_make_label("Press Enter or tap Submit", color=FG2, font_size=10))

        # Feedback label
        self._feedback_lbl = _make_label("", color=FG2, font_size=12)
        content.add_widget(self._feedback_lbl)

        # Note holder (populated on wrong answer)
        self._note_holder = BoxLayout(orientation="vertical", size_hint_y=None)
        self._note_holder.bind(minimum_height=self._note_holder.setter("height"))
        content.add_widget(self._note_holder)

        # Submit button
        self._submit_btn = _make_button("Submit", self._submit,
                                         color=BG, bg_color=GREEN,
                                         min_height=52, font_size=15, bold=True)
        content.add_widget(self._submit_btn)

        # Skip / Quit row
        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        skip_btn = _make_button("Skip", self._skip, color=FG2, bg_color=BG2, min_height=48)
        quit_btn = _make_button("Quit", self._quit, color=FG2, bg_color=BG2, min_height=48)
        btn_row.add_widget(skip_btn)
        btn_row.add_widget(quit_btn)
        content.add_widget(btn_row)
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)
        # Request focus after layout
        Clock.schedule_once(lambda dt: setattr(self._entry, "focus", True), 0.15)

    def _submit(self) -> None:
        if self._submit_locked:
            return
        if self._wrong_shown:
            elapsed = time.time() - self._wrong_time
            if elapsed < 2.0:
                self._feedback_lbl.text = f"Read the note — {int(2 - elapsed) + 1}s remaining..."
                self._feedback_lbl.color = AMBER
                return
            # Advance to next card
            self._build()
            return

        app = App.get_running_app()
        s: LearnSession = app._session
        result = learn_submit(s, self._entry.text)

        if result["correct"]:
            pts = result.get("points_earned", 0)
            streak = result.get("streak", 0)
            self._feedback_lbl.text = f"Correct!  +{pts} pts    STREAK: {streak}"
            self._feedback_lbl.color = GREEN
            self._submit_locked = True
            self._entry.disabled = True

            # Progress tracking
            if PROGRESS_AVAILABLE and app._progress is not None:
                try:
                    answered = s.deck[s.index - 1] if s.index > 0 else {}
                    record_correct(
                        app._progress, result["expected"],
                        answered.get("category", ""), "learn",
                        result.get("streak", 0),
                    )
                    new_ach = check_achievements(app._progress, {
                        "mode": "learn", "correct": True,
                        "streak": result.get("streak", 0),
                        "cmd": result["expected"],
                        "category": answered.get("category", ""),
                    })
                    for ach_id in new_ach:
                        defn = ACHIEVEMENTS.get(ach_id)
                        if defn:
                            d = {"title": defn.title, "description": defn.description}
                            app._session_achievements.append(d)
                            Clock.schedule_once(lambda dt, a=d: show_achievement_popup(a), 0.2)
                except Exception as exc:
                    log.warning("Achievement check failed: %s", exc)

            Clock.schedule_once(lambda dt: self._build(), 0.7)
        else:
            self._wrong_shown = True
            self._wrong_time = time.time()
            self._feedback_lbl.text = result["feedback"]
            self._feedback_lbl.color = RED
            self._entry.text = ""
            self._entry.disabled = True
            self._submit_btn.text = "Continue  →"
            self._submit_btn.background_color = AMBER

            expected = result.get("expected", "")
            syntax = result.get("syntax", "")
            note = get_hacker_note(expected)

            self._note_holder.clear_widgets()
            self._note_holder.add_widget(make_hacker_note_panel(expected, syntax, note))

    def _skip(self) -> None:
        app = App.get_running_app()
        learn_submit(app._session, "")
        self._build()

    def _quit(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# ChallengeMenuScreen
# ---------------------------------------------------------------------------

class ChallengeMenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._lives_selected = 3
        self._build()

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)

        root = BoxLayout(orientation="vertical")
        content = _card_box()

        content.add_widget(_make_label("CHALLENGE MODE", color=YELLOW, font_size=20, bold=True, halign="center"))
        content.add_widget(_make_label(
            "Timed — wrong answers cost a life. Streak = bonus points.",
            color=FG2, font_size=12, halign="center"))
        content.add_widget(_colored_box(BG3))
        content.add_widget(_make_label("Lives", color=FG2, font_size=12))

        lives_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        for n in [1, 3, 5]:
            is_sel = (n == self._lives_selected)
            btn = _make_button(
                f"♥ {n}",
                lambda v=n: self._select_lives(v),
                color=BG if is_sel else RED,
                bg_color=RED if is_sel else BG3,
                min_height=48,
                font_size=14,
            )
            lives_row.add_widget(btn)
        content.add_widget(lives_row)

        content.add_widget(Widget(size_hint_y=None, height=dp(8)))
        content.add_widget(_make_button("START", self._start,
                                        color=BG, bg_color=YELLOW,
                                        min_height=56, font_size=16, bold=True))
        content.add_widget(_make_button("Back", self._back,
                                        color=FG2, bg_color=BG2, min_height=48))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

    def _select_lives(self, n: int) -> None:
        self._lives_selected = n
        self._build()

    def _start(self) -> None:
        app = App.get_running_app()
        app._session = challenge_start(lives=self._lives_selected)
        app._session_xp_start = app._progress.total_xp if app._progress else 0
        app._session_achievements = []
        cs: ChallengeCardScreen = self.manager.get_screen("challenge_card")
        cs._build()
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "challenge_card"

    def _back(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# ChallengeCardScreen
# ---------------------------------------------------------------------------

class ChallengeCardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._timer_event: Optional[Any] = None
        self._card_start = 0.0
        self._submit_locked = False

    def _cancel_timer(self) -> None:
        if self._timer_event is not None:
            self._timer_event.cancel()
            self._timer_event = None

    def _build(self) -> None:
        self._cancel_timer()
        self.clear_widgets()
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._card_start = time.time()
        self._submit_locked = False

        app = App.get_running_app()
        s: ChallengeSession = app._session
        state = challenge_card(s)

        if state["done"]:
            rs: ResultScreen = self.manager.get_screen("result")
            rs._build("CHALLENGE OVER", state)
            self.manager.transition = SlideTransition(direction="left")
            self.manager.current = "result"
            return

        root = BoxLayout(orientation="vertical")

        # Header
        lives_str = "♥ " * state["lives"]
        hdr = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(44))
        _bg_rect(hdr, BG2)
        hdr.add_widget(_make_label(f"  {lives_str}", color=RED, font_size=13, size_hint_x=0.4))
        self._timer_lbl = _make_label("0s", color=GREEN, font_size=12,
                                       halign="center", size_hint_x=0.2)
        hdr.add_widget(self._timer_lbl)
        hdr.add_widget(_make_label(
            f"Card {state['card_num']}/{state['total']}  Score:{state['score']}",
            color=FG2, font_size=11, halign="right", size_hint_x=0.4))
        root.add_widget(hdr)
        root.add_widget(_colored_box(BG3))

        # Scrollable content
        content = _card_box()

        badge_row = BoxLayout(size_hint_y=None, height=dp(36))
        badge_row.add_widget(_make_badge(state["category"], state["level"]))
        badge_row.add_widget(Widget())
        content.add_widget(badge_row)

        p_outer, p_inner = _panel(BG2, border_color=BG3)
        prompt_lbl = _make_label(state["prompt"], color=FG, font_size=14,
                                  bold=True, halign="center")
        prompt_lbl.text_size = (Window.width - dp(48), None)
        prompt_lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(12)))
        p_inner.add_widget(prompt_lbl)
        content.add_widget(p_outer)

        content.add_widget(_make_label("Type the command:", color=FG2, font_size=11))

        self._entry = _make_text_input("command here...", fg_color=YELLOW)
        self._entry.bind(on_text_validate=lambda ti: self._submit())
        content.add_widget(self._entry)
        content.add_widget(_make_label("Press Enter or tap Submit", color=FG2, font_size=10))

        self._feedback_lbl = _make_label("", color=FG2, font_size=12)
        content.add_widget(self._feedback_lbl)

        self._note_holder = BoxLayout(orientation="vertical", size_hint_y=None)
        self._note_holder.bind(minimum_height=self._note_holder.setter("height"))
        content.add_widget(self._note_holder)

        self._submit_btn = _make_button("Submit", self._submit,
                                         color=BG, bg_color=YELLOW,
                                         min_height=52, font_size=15, bold=True)
        content.add_widget(self._submit_btn)
        content.add_widget(_make_button("Quit", self._quit,
                                         color=FG2, bg_color=BG2, min_height=48))
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

        # Start the timer
        self._timer_event = Clock.schedule_interval(self._tick_timer, 0.5)
        Clock.schedule_once(lambda dt: setattr(self._entry, "focus", True), 0.15)

    def _tick_timer(self, dt: float) -> None:
        if not hasattr(self, "_timer_lbl"):
            return
        elapsed = int(time.time() - self._card_start)
        if elapsed <= 8:
            col = GREEN
        elif elapsed <= 20:
            col = YELLOW
        else:
            col = RED
        try:
            self._timer_lbl.text = f"{elapsed}s"
            self._timer_lbl.color = col
        except Exception as exc:
            log.warning("Timer label update error: %s", exc)

    def _submit(self) -> None:
        if self._submit_locked:
            return
        if self._wrong_shown:
            elapsed = time.time() - self._wrong_time
            if elapsed < 2.0:
                self._feedback_lbl.text = f"Read the note — {int(2 - elapsed) + 1}s remaining..."
                self._feedback_lbl.color = AMBER
                return
            self._cancel_timer()
            self._build()
            return

        app = App.get_running_app()
        s: ChallengeSession = app._session
        result = challenge_submit(s, self._entry.text)

        if result["correct"]:
            streak = result.get("streak", 0)
            pts = result.get("points_earned", 0)
            self._feedback_lbl.text = f"Correct!  +{pts} pts    STREAK: {streak}"
            self._feedback_lbl.color = GREEN
            self._submit_locked = True
            self._entry.disabled = True

            if PROGRESS_AVAILABLE and app._progress is not None:
                try:
                    answered = s.deck[s.index - 1] if s.index > 0 else {}
                    record_correct(
                        app._progress, result["expected"],
                        answered.get("category", ""), "challenge",
                        result.get("streak", 0),
                        result.get("elapsed_s", 0.0),
                    )
                    new_ach = check_achievements(app._progress, {
                        "mode": "challenge", "correct": True,
                        "streak": result.get("streak", 0),
                        "elapsed_s": result.get("elapsed_s", 0.0),
                        "cmd": result["expected"],
                        "category": answered.get("category", ""),
                    })
                    for ach_id in new_ach:
                        defn = ACHIEVEMENTS.get(ach_id)
                        if defn:
                            d = {"title": defn.title, "description": defn.description}
                            app._session_achievements.append(d)
                            Clock.schedule_once(lambda dt, a=d: show_achievement_popup(a), 0.2)
                except Exception as exc:
                    log.warning("Achievement check failed: %s", exc)

            self._cancel_timer()
            Clock.schedule_once(lambda dt: self._build(), 0.5)
        else:
            self._wrong_shown = True
            self._wrong_time = time.time()
            lives_left = result.get("lives", 0)
            self._feedback_lbl.text = f"{result['feedback']}   Lives: {'♥ ' * lives_left}"
            self._feedback_lbl.color = RED
            self._entry.text = ""
            self._entry.disabled = True
            self._submit_btn.text = "Continue  →"
            self._submit_btn.background_color = AMBER

            expected = result.get("expected", "")
            syntax = result.get("syntax", "")
            note = get_hacker_note(expected)
            self._note_holder.clear_widgets()
            self._note_holder.add_widget(make_hacker_note_panel(expected, syntax, note))

    def _quit(self) -> None:
        self._cancel_timer()
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"

    def on_leave(self) -> None:
        self._cancel_timer()


# ---------------------------------------------------------------------------
# BossMenuScreen
# ---------------------------------------------------------------------------

class BossMenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._selected_idx = -1
        self._build()

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)

        root = BoxLayout(orientation="vertical")
        content = _card_box()

        content.add_widget(_make_label("BOSS MODE", color=RED, font_size=20, bold=True, halign="center"))
        content.add_widget(_make_label(
            "Multi-step scenarios — solve each command in order to win",
            color=FG2, font_size=12, halign="center"))
        content.add_widget(_colored_box(BG3))

        scenarios = boss_scenarios_list()

        # Random option
        is_rand = (self._selected_idx == -1)
        rand_btn = _make_button(
            "  Random scenario",
            lambda: self._select(-1),
            color=BG if is_rand else YELLOW,
            bg_color=YELLOW if is_rand else BG2,
            min_height=48, font_size=13, bold=True,
        )
        content.add_widget(rand_btn)

        for sc in scenarios:
            idx = sc["index"]
            is_sel = (idx == self._selected_idx)
            lbl = f"{sc['title']}  ({sc['steps']} steps)"
            btn = _make_button(
                lbl,
                lambda i=idx: self._select(i),
                color=BG if is_sel else FG,
                bg_color=RED if is_sel else BG3,
                min_height=50, font_size=12,
            )
            content.add_widget(btn)

        content.add_widget(Widget(size_hint_y=None, height=dp(8)))
        content.add_widget(_make_button("START", self._start,
                                        color=BG, bg_color=RED,
                                        min_height=56, font_size=16, bold=True))
        content.add_widget(_make_button("Back", self._back,
                                        color=FG2, bg_color=BG2, min_height=48))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

    def _select(self, idx: int) -> None:
        self._selected_idx = idx
        self._build()

    def _start(self) -> None:
        app = App.get_running_app()
        idx = None if self._selected_idx == -1 else self._selected_idx
        app._session = boss_start(idx)
        app._session_xp_start = app._progress.total_xp if app._progress else 0
        app._session_achievements = []
        bs: BossStepScreen = self.manager.get_screen("boss_step")
        bs._build()
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "boss_step"

    def _back(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# BossStepScreen
# ---------------------------------------------------------------------------

class BossStepScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._submit_locked = False

    def _build(self) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)
        self._wrong_shown = False
        self._wrong_time = 0.0
        self._submit_locked = False

        app = App.get_running_app()
        s: BossSession = app._session
        state = boss_state(s)

        if state["done"]:
            rs: ResultScreen = self.manager.get_screen("result")
            rs._build("BOSS DEFEATED", state)
            self.manager.transition = SlideTransition(direction="left")
            self.manager.current = "result"
            return

        root = BoxLayout(orientation="vertical")

        # Header
        hdr = make_header(
            state["title"],
            f"Step {state['step']}/{state['total_steps']}  Score:{state['score']}",
            left_color=RED, right_color=FG2,
        )
        root.add_widget(hdr)
        root.add_widget(_colored_box(RED))

        # Scrollable content
        content = _card_box()

        # Story panel — first step only
        if state["step"] == 1:
            s_outer, s_inner = _panel(BG3, border_color=RED)
            story_lbl = _make_label(state["story"], color=FG2, font_size=12)
            story_lbl.text_size = (Window.width - dp(60), None)
            story_lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(12)))
            s_inner.add_widget(story_lbl)
            content.add_widget(s_outer)

        # Progress dots
        dots_row = BoxLayout(size_hint_y=None, height=dp(32))
        for i in range(1, state["total_steps"] + 1):
            if i < state["step"]:
                col, sym = GREEN, "●"
            elif i == state["step"]:
                col, sym = YELLOW, "◉"
            else:
                col, sym = FG2, "○"
            dots_row.add_widget(_make_label(f" {sym} ", color=col, font_size=18,
                                             size_hint_x=None, width=dp(28)))
        content.add_widget(dots_row)

        # Step prompt panel
        sp_outer, sp_inner = _panel(BG2, border_color=RED)
        step_lbl = _make_label(
            f"Step {state['step']}: {state['hint']}",
            color=FG, font_size=13, bold=True, halign="center")
        step_lbl.text_size = (Window.width - dp(60), None)
        step_lbl.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(12)))
        sp_inner.add_widget(step_lbl)
        content.add_widget(sp_outer)

        content.add_widget(_make_label("Type the command:", color=FG2, font_size=11))

        self._entry = _make_text_input("command here...", fg_color=RED)
        self._entry.bind(on_text_validate=lambda ti: self._submit())
        content.add_widget(self._entry)
        content.add_widget(_make_label("Press Enter or tap Submit", color=FG2, font_size=10))

        self._feedback_lbl = _make_label("", color=FG2, font_size=12)
        content.add_widget(self._feedback_lbl)

        self._note_holder = BoxLayout(orientation="vertical", size_hint_y=None)
        self._note_holder.bind(minimum_height=self._note_holder.setter("height"))
        content.add_widget(self._note_holder)

        # Button row: Submit | Hint | Quit
        self._submit_btn = _make_button("Submit", self._submit,
                                         color=BG, bg_color=RED,
                                         min_height=52, font_size=15, bold=True)
        content.add_widget(self._submit_btn)

        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        hint_btn = _make_button("Hint", self._hint, color=YELLOW, bg_color=BG2, min_height=48)
        quit_btn = _make_button("Quit", self._quit, color=FG2, bg_color=BG2, min_height=48)
        btn_row.add_widget(hint_btn)
        btn_row.add_widget(quit_btn)
        content.add_widget(btn_row)
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)
        Clock.schedule_once(lambda dt: setattr(self._entry, "focus", True), 0.15)

    def _submit(self) -> None:
        if self._submit_locked:
            return
        if self._wrong_shown:
            elapsed = time.time() - self._wrong_time
            if elapsed < 2.0:
                self._feedback_lbl.text = f"Read the note — {int(2 - elapsed) + 1}s remaining..."
                self._feedback_lbl.color = AMBER
                return
            # Re-enable input for retry (boss mode lets you retry same step)
            self._wrong_shown = False
            self._note_holder.clear_widgets()
            self._entry.disabled = False
            self._entry.text = ""
            Clock.schedule_once(lambda dt: setattr(self._entry, "focus", True), 0.05)
            self._submit_btn.text = "Submit"
            self._submit_btn.background_color = RED
            self._feedback_lbl.text = ""
            self._feedback_lbl.color = FG2
            return

        app = App.get_running_app()
        s: BossSession = app._session
        result = boss_submit(s, self._entry.text)

        if result.get("correct"):
            pts = result.get("points_earned", 0)
            self._feedback_lbl.text = f"Correct!  +{pts} pts"
            self._feedback_lbl.color = GREEN
            self._submit_locked = True
            self._entry.disabled = True

            if PROGRESS_AVAILABLE and app._progress is not None:
                try:
                    record_boss_step(app._progress)
                    is_done = result.get("step", 1) >= result.get("total_steps", 1)
                    if is_done:
                        record_boss_complete(app._progress, s.scenario["title"])
                    new_ach = check_achievements(app._progress, {
                        "mode": "boss", "correct": True,
                        "streak": s.correct_steps,
                        "hints_used": s.hints_used,
                        "scenario_title": s.scenario["title"],
                    })
                    for ach_id in new_ach:
                        defn = ACHIEVEMENTS.get(ach_id)
                        if defn:
                            d = {"title": defn.title, "description": defn.description}
                            app._session_achievements.append(d)
                            Clock.schedule_once(lambda dt, a=d: show_achievement_popup(a), 0.2)
                except Exception as exc:
                    log.warning("Boss achievement check failed: %s", exc)

            Clock.schedule_once(lambda dt: self._build(), 0.7)
        else:
            self._wrong_shown = True
            self._wrong_time = time.time()
            fb = result.get("feedback", "")
            self._feedback_lbl.text = fb
            self._feedback_lbl.color = RED
            self._entry.text = ""
            self._entry.disabled = True
            self._submit_btn.text = "Continue  →"
            self._submit_btn.background_color = AMBER

            expected = result.get("expected", "")
            syntax = ""
            for cmd_entry in COMMANDS:
                if cmd_entry["cmd"] == expected:
                    syntax = cmd_entry.get("syntax", "")
                    break
            note = get_hacker_note(expected)
            self._note_holder.clear_widgets()
            self._note_holder.add_widget(make_hacker_note_panel(expected, syntax, note))

    def _hint(self) -> None:
        app = App.get_running_app()
        s: BossSession = app._session
        result = boss_submit(s, "", use_hint=True)
        self._feedback_lbl.text = result.get("hint", "")
        self._feedback_lbl.color = YELLOW

    def _quit(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# ResultScreen
# ---------------------------------------------------------------------------

GRADE_DESC = {
    "S": "Flawless. Shell wizard detected.",
    "A": "Excellent. Almost perfect.",
    "B": "Solid. Keep practicing.",
    "C": "Fair. Review the weak spots.",
    "D": "Keep going — every expert was a beginner once.",
}


class ResultScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg_rect(self, BG)

    def _build(self, title: str, state: Dict) -> None:
        self.clear_widgets()
        _bg_rect(self, BG)

        app = App.get_running_app()
        success = "COMPLETE" in title or "DEFEATED" in title
        banner_col = GREEN if success else RED

        root = BoxLayout(orientation="vertical")

        # Banner header
        hdr = BoxLayout(size_hint=(1, None), height=dp(60))
        _bg_rect(hdr, BG2)
        hdr.add_widget(_make_label(f"  {title}", color=banner_col,
                                    font_size=20, bold=True, size_hint_x=0.8))
        root.add_widget(hdr)
        root.add_widget(_colored_box(banner_col))

        # Scrollable content
        content = _card_box()

        # Grade
        accuracy = state.get("accuracy")
        if accuracy is not None:
            grade_letter, grade_col = calc_grade(accuracy)
            grade_row = BoxLayout(size_hint_y=None, height=dp(80), spacing=dp(12))
            grade_lbl = Label(
                text=grade_letter,
                color=grade_col,
                font_size=dp(56),
                bold=True,
                size_hint=(None, None),
                width=dp(70),
                height=dp(80),
            )
            grade_row.add_widget(grade_lbl)
            grade_row.add_widget(_make_label(
                GRADE_DESC.get(grade_letter, ""),
                color=grade_col, font_size=13,
                size_hint_x=1,
            ))
            content.add_widget(grade_row)
            content.add_widget(_colored_box(BG3))

        # Stats grid
        stats_box, stats_inner = _panel(BG2, border_color=BG3)
        grid = GridLayout(cols=3, size_hint_y=None, spacing=dp(4))
        grid.bind(minimum_height=grid.setter("height"))

        stat_rows = [
            ("score",      "SCORE",       GREEN,  ""),
            ("correct",    "Correct",     GREEN,  ""),
            ("incorrect",  "Wrong",       RED,    ""),
            ("accuracy",   "Accuracy",    BLUE,   "%"),
            ("hints_used", "Hints",       YELLOW, ""),
            ("elapsed_s",  "Time",        FG2,    "s"),
        ]
        for key, label_txt, color, suffix in stat_rows:
            val = state.get(key)
            if val is None:
                grid.add_widget(Widget(size_hint_y=None, height=dp(10)))
                continue
            cell = BoxLayout(orientation="vertical", size_hint_y=None, padding=[dp(8), dp(6)])
            cell.bind(minimum_height=cell.setter("height"))
            cell.add_widget(_make_label(label_txt, color=FG2, font_size=10))
            cell.add_widget(_make_label(f"{val}{suffix}", color=color, font_size=18, bold=True))
            grid.add_widget(cell)

        stats_inner.add_widget(grid)
        content.add_widget(stats_box)

        # XP earned this session
        if PROGRESS_AVAILABLE and app._progress is not None:
            try:
                xp_earned = app._progress.total_xp - app._session_xp_start
                leveled = app._progress.level > level_for_xp(app._session_xp_start)
                xp_outer, xp_inner = _panel(BG3, border_color=GREEN)
                xp_msg = f"  +{max(xp_earned, 0)} XP earned this session"
                if leveled:
                    xp_msg += f"  ·  LEVEL UP → {app._progress.level}"
                xp_inner.add_widget(_make_label(xp_msg, color=GREEN, font_size=13, bold=True))
                content.add_widget(xp_outer)
                save_progress(app._progress)
            except Exception as exc:
                log.warning("Progress save failed: %s", exc)

        # New achievements
        if app._session_achievements:
            content.add_widget(_colored_box(GREEN))
            content.add_widget(_make_label("NEW ACHIEVEMENTS", color=GREEN,
                                            font_size=12, bold=True))
            for ach in app._session_achievements:
                a_outer, a_inner = _panel(BG2, border_color=GREEN)
                a_inner.add_widget(_make_label(
                    f"  {ach.get('title', '?')}", color=GREEN, font_size=13, bold=True))
                a_inner.add_widget(_make_label(
                    f"  {ach.get('description', '')}", color=FG2, font_size=11))
                content.add_widget(a_outer)

        content.add_widget(_colored_box(BG3))
        content.add_widget(_make_button("Play Again", self._play_again,
                                         color=BG, bg_color=GREEN,
                                         min_height=56, font_size=15, bold=True))
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        sv = _scroll_wrap(content)
        root.add_widget(sv)
        self.add_widget(root)

        # Clear achievements for next session
        app._session_achievements = []

    def _play_again(self) -> None:
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class SSHCommanderApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._session: Any = None
        self._session_xp_start: int = 0
        self._session_achievements: List[Dict] = []
        self._progress = None

    def build(self) -> ScreenManager:
        Window.clearcolor = BG

        # Load player progress
        if PROGRESS_AVAILABLE:
            try:
                self._progress = load_progress()
                update_streak(self._progress)
            except Exception as exc:
                log.warning("Failed to load progress: %s", exc)

        sm = ScreenManager()
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(LearnMenuScreen(name="learn_menu"))
        sm.add_widget(LearnCardScreen(name="learn_card"))
        sm.add_widget(ChallengeMenuScreen(name="challenge_menu"))
        sm.add_widget(ChallengeCardScreen(name="challenge_card"))
        sm.add_widget(BossMenuScreen(name="boss_menu"))
        sm.add_widget(BossStepScreen(name="boss_step"))
        sm.add_widget(ResultScreen(name="result"))

        sm.current = "menu"
        return sm

    def get_application_config(self) -> str:
        """Return platform-aware config path."""
        return str(Path(self.user_data_dir) / "ssh_commander.ini")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    SSHCommanderApp().run()
