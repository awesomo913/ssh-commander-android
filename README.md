# SSH Commander Game (Android)

> A flashcard-style game for learning real SSH commands, with Learn / Challenge / Boss modes.

SSH Commander is a study game that drills SSH command syntax through three modes — plain flashcards (Learn), a timed mode where wrong answers cost a life (Challenge), and multi-step scenarios that must be solved in order (Boss). This repo holds two separate, unmerged attempts at shipping it on Android.

## Features
- **Three game modes**: Learn (flashcard loop across all or filtered categories), Challenge (timed, life-based), Boss (ordered multi-step scenarios) — `engine.py`.
- **Expanded command bank** across categories (`commands_expanded.py`) and a dedicated Boss scenario set v2 (`boss_scenarios_v2.py`).
- **Player progress system**: XP, levels, streaks, and achievements (`progress.py`).
- **Python/Kivy build**: all screens defined in Python (no `.kv` files), intended for Termux/Android (`main.py`).
- **Parallel native build**: a second, independent Kotlin/Android implementation with its own `GameEngine.kt`, `MainActivity.kt`, and XML layouts under `app/src/main/`.

## Stack
Two separate, unconsolidated implementations: Python + Kivy (`main.py`, `engine.py`, `progress.py`), and Kotlin + native Android views (`app/src/main/kotlin/`).

## Getting started
**Requirements**
- For the Kivy build: Python 3.x + Kivy.
- For the native build: Android Studio / Gradle.

**Run**
```bash
# Kivy build:
python main.py
```
The Kotlin build is a standard Gradle Android project under `app/` (open in Android Studio or build with `gradlew`).

## Status
Paused before completion — two parallel, unmerged implementations (Python/Kivy and native Kotlin); the concept was shelved rather than finished. Last touched 2026-06-17.

## License
[MIT](LICENSE) — free to use, fork, and build on.
