# AGENTS.md

Guidance for AI agents working in the TaoClear repository. Read this file
first; `docs/STYLES.md` is the authoritative convention document — this file
is the operational summary, not a replacement.

## Project

TaoClear (清除之道) — a classic falling-block game with an independent fair
bot. Python 3.13+, pygame-ce, managed with uv. Personal project: the owner is
the only player, so gameplay preferences are final.

## Commands

- Run: `uv run python src/main.py`
- Test: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Typecheck: `uv run basedpyright .` (strict mode)
- All three (`pytest`, `ruff`, `basedpyright`) must be green before
  committing.

## Architecture

One-way dependencies:

```
contracts.py  cross-component contracts: Action, GameState, BotSnapshot,
              BotInterface, AppInterface
engine.py     GameEngine — the single source of game rules (pygame-free)
renderer.py   draws a GameState snapshot; never touches app or engine
bot.py        BotRunner — independent thread; Actions go through the same
              _apply_action path as the keyboard (fair, not a backdoor)
app.py        GameApp — composition root
ui_states.py  state machine: Playing / Paused / GameOver / ConfirmQuit / Help
keyboard_handler.py / config_manager.py / audio_manager.py / utils.py / main.py
```

- Game rules live only in `engine.py`. `app.py` (GameApp) is a shell;
  `renderer.py` is read-only — it never touches the app or the engine.
- The bot (`bot.py`) is a player: same Actions, same
  gravity/lock-delay/scoring. Never give it direct engine access or
  special treatment.
- New geometry/rule logic goes in `engine.py`'s shared primitives section so
  the bot's simulation stays in sync.

## Design decisions

Game rules live in `engine.py` and are summarized in STYLES §7 — read them
before touching gameplay. Some choices are deliberate; do not "fix" them:

- **No Hold piece, no multi-piece next queue** — the owner considers them
  cheating; the single next preview is the ceiling.
- **Strict T-spin** — the rotation must be the literal last action. A hard
  drop that actually moves the piece cancels it; a grounded hard drop
  (distance 0) does not. The mainstream "rotate then hard-drop" T-spin is
  deliberately not recognized.
- **Gentle difficulty is intended** — level caps at 14, speed floors at
  100 ms, endless mode, generous lock delay. The owner is a veteran player
  who wants casual leisure; do not steepen the curve unasked.
- **Feature-complete posture** — propose new features before building them;
  the owner's gameplay preferences are final.
- **Version cycle** — the dev version lives in `pyproject.toml`; changes
  accumulate on it, and the pre-release checklist (STYLES §11) runs before
  bumping to a release tag `vX.Y.Z`.

## Hard rules

- Comments and docstrings in **Chinese**; commit messages in **English** with a
  conventional prefix (`feat:` `fix:` `refactor:` `chore:` `docs:` …). For
  AI-assisted work, append a `Co-authored-by:` trailer in the standard Git
  format `Co-authored-by: Name <email>` — use the agent's dedicated email
  address when it has one.
- **Never amend, rebase, or force-push commits that have been pushed** — pushed
  history is frozen; small follow-ups become new commits.
- Keep comments and docstrings in sync with the code; when renaming or
  refactoring, update the stale text too.
- Rule changes are test-first: engine rules get engine tests, scoring gets
  explicit assertions, end-to-end behavior gets app-level tests.
- No production API or fields that only tests would use — tests reach `_`
  internals directly (white-box, no shims).
- Pre-release: run the hygiene checklist in STYLES §11 (semantic audit, dead
  code/API, comment sync, docs drift, full verification) before bumping.
- Product name is TaoClear (package `taoclear`); the GitHub repo
  `tlyx/mytetris` stays as-is — don't rename it.

## Layout

- GameApp's annotations, `__init__` sequence, and `_init_*` helpers follow one
  canonical group order (see STYLES §2): config → window/display → engine
  session → UI flow → time source → input → rendering → audio → bot.
- One module per concern; keep each module header's "此文件主要负责" bullets
  accurate when responsibilities change.
