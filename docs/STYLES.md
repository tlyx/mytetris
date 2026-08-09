# MyTetris Style Guide

This document describes the programming style and conventions used in the
MyTetris codebase. It is written in English; code comments and docstrings are
written in Chinese (the project language). Follow these rules when modifying
the code so that the style stays consistent.

---

## Table of Contents

1. [Language & Layout](#1-language--layout)
2. [Module Architecture](#2-module-architecture)
3. [Naming Conventions](#3-naming-conventions)
4. [Typing & Static Analysis](#4-typing--static-analysis)
5. [Module Headers & Documentation](#5-module-headers--documentation)
6. [Dependency Rules](#6-dependency-rules)
7. [Engine Conventions](#7-engine-conventions)
8. [Testing](#8-testing)
9. [Tooling & QA](#9-tooling--qa)
10. [Git & Versioning](#10-git--versioning)
11. [Checklist](#11-checklist)

---

## 1. Language & Layout

- **Python 3.13+** (`requires-python = ">=3.13"`), dependency-managed with
  [uv](https://github.com/astral-sh/uv) (`uv sync`, `uv run …`).
- Line length follows ruff's default (88 columns); the project only pins
  `src = ["src"]` in `[tool.ruff]` and relies on ruff's defaults otherwise.
- Import order is enforced by ruff (`I001`): standard library → third-party →
  first-party, each group separated by a blank line. If a file carries a
  `from __future__` import, it always comes first (see §4 for when that is
  needed at all).
- One logical concern per module; see
  [Module Architecture](#2-module-architecture).
- Comments and docstrings are written in Chinese, matching the existing code.
  Inline comments explain *why*, not *what*.

## 2. Module Architecture

The codebase is split by responsibility, and the dependency direction is
strictly one-way. Layout: all code lives in `src/` (flat top-level modules,
not a package), including the `main.py` entry point; `tests/` and `docs/`
live at the project root. Imports resolve because the interpreter puts the
script's directory (`src/`) on the path when running `uv run src/main.py`,
and `tests/conftest.py` adds `src` for pytest; pyright resolves via
`extraPaths`.

```
main.py → tetris.py (TetrisApp)
tetris.py → renderer.py, ui_states.py, input_handler.py,
            audio_manager.py, config_manager.py, contracts.py,
            bot.py (BotRunner), engine.py (TetrisEngine)
bot.py → contracts.py, engine.py (shared geometry primitives only)
renderer.py → contracts.py, engine.py (constants/shapes only)
```

| Module | Responsibility |
| --- | --- |
| `main.py` | Entry point; constructs `TetrisApp` and runs it. |
| `tetris.py` | App shell: window, event loop, state switching, input routing, bot driving. |
| `engine.py` | Pure game rules — no graphics dependency, unit-testable in isolation. |
| `renderer.py` | Draws a `GameState` onto a Surface; never touches the app or the engine. |
| `ui_states.py` | State pattern: one handler class per app/UI state. |
| `input_handler.py` | Key → `Action` mapping and DAS/ARR auto-repeat. |
| `contracts.py` | Cross-component contracts: data (`Action`, `GameState`, `BotSnapshot`) and interface protocols (`BotInterface`, `AppInterface`). |
| `bot.py` | Bot decision and scheduling; exposes `BotRunner` (protocols/snapshot live in `contracts.py`). |
| `config_manager.py` | `config.json` persistence. |
| `audio_manager.py` | Music/sound loading and playback, graceful degradation. |
| `utils.py` | `resource_path` (PyInstaller-aware path resolution). |

Guidelines:

- **Keep logic out of the UI.** Game rules live in `engine.py`; the renderer
  consumes snapshots; the app wires them together.
- **The bot is an external agent, not a game feature.** The game interacts
  with it only through the `BotInterface` protocol and a single `tick()`
  call per frame; the renderer knows nothing about it (it just draws
  `status_line`).
- **Shared rules are shared on purpose.** The geometry primitives
  (`rotate_shape`, `collides`, `drop_y`, `spawn_y`, `cells_in_bounds`) are
  module-level pure functions in `engine.py` that both the engine and the bot
  import, so simulation semantics can never drift apart.
- **`TetrisApp` is organized by responsibility, in one canonical order.**
  Class annotations, the `__init__` call sequence, and the `_init_*` helper
  methods all follow the same group order — config → window/display → engine
  session → UI flow → time source → input → rendering → audio → bot — marked
  by `# ---- … ----` headers. Add a new member to the matching group in all
  three places. Nothing enforces this automatically; keep it true by hand.

## 3. Naming Conventions

| Kind | Convention | Example |
| --- | --- | --- |
| Classes | PascalCase | `TetrisEngine`, `BotRunner`, `GameState` |
| Functions / methods | snake_case | `lock_and_clear_lines`, `cycle_strategy` |
| Module-level functions | snake_case, `_`-private when internal | `_best_move`, `_evaluate` |
| Constants | UPPER_SNAKE_CASE | `GRID_WIDTH`, `MAX_SCORE` |
| Private constants | `_`-prefixed UPPER_SNAKE | `_MAX_LEVEL`, `_STATUS_COLOR` |
| Private members | leading underscore | `self._piece_resting`, `_Mailbox` |
| Type aliases | PascalCase; `_`-private when internal | `_ConfigValue` |

Rules:

- **A name is public only if another module imports it.** Everything used
  solely inside its own module (or only by white-box tests) gets a leading
  underscore. The module doc-header states the public API boundary explicitly
  (see `bot.py`).
- Class attributes are annotated at class level, not only in `__init__`.
- Constants that encode tuning knobs stay in the module that owns them.

## 4. Typing & Static Analysis

- **Strict mode.** `pyrightconfig.json` sets `typeCheckingMode: "strict"`
  with `reportUnusedCallResult` and `reportAny` disabled.
- **Annotate everything**: parameters, return values, module- and class-level
  attributes, and container element types (`list[list[tuple[int, int, int] | None]]`,
  not bare `list`).
- Use `from __future__ import annotations` only where annotations reference
  names that are not available at runtime: forward references or
  `TYPE_CHECKING`-only imports (the one case in this repo is
  `ui_states.py`, which annotates with a `TYPE_CHECKING`-imported
  `TetrisEngine` and needs it for Python 3.13). Do not add it everywhere:
  on Python 3.14+ (PEP 649) annotations are lazy by default, so it is a
  no-op there anyway.
- Use `@final` on classes that are not meant to be subclassed
  (`TetrisEngine`, `TetrisApp`, `BotRunner`, `Renderer`, …).
- Use `Protocol` for interface contracts (`BotInterface`, `AppInterface`);
  depend on the protocol, construct the concrete implementation only at the
  composition root (`TetrisApp._init_bot`).
- Use `@dataclass(frozen=True)` for immutable data carriers
  (`GameState`, `BotSnapshot`).
- Use `typing.ClassVar` for class-level constants that are part of the
  instance contract (`TetrisEngine.SCORE_TABLE`).
- Use `@override` when overriding a base-class method (see `ui_states.py`).
- Unused parameters that exist only for signature uniformity are named with a
  leading underscore (`_landing_height`).

## 5. Module Headers & Documentation

Every `.py` file starts with a comment header in this shape:

```python
# <name>.py — <one-line purpose>
# <responsibility summary>
#
# <design notes, when relevant>
#
# 此文件主要负责：
#  - <bullet item>
#  - <bullet item>

imports…
```

- The first line always uses `<name>.py — …` with an em dash.
- The bullet list enumerates the file's concrete responsibilities and stays
  accurate when responsibilities change (update it, don't let it rot).
- Keep the header focused; long design rationale goes into the module that
  owns the design (see `bot.py`).
- Test files keep their module docstring (they document the test suite);
  the comment header sits above it, and `# pyright:` file directives stay on
  **line 1** so the type checker still honors them.
- **Definition order**, as pseudocode:

  ```python
  # module level
  """<module header>"""
  imports …                             # stdlib → third-party → local


  MODULE_CONSTANT = ...                 # module constants


  def public_helper(): ...              # public helpers first


  def _private_helper(): ...            # private helpers after public ones


  class Foo: ...                        # classes last


  if __name__ == "__main__": ...        # entry module only


  # class level
  class Foo:
      def __init__(self): ...           # constructor first

      def public_method(self): ...      # public API, grouped by concern

      def _private(self): ...           # private members last
  ```

  Move a code block together with its section-header comment.

## 6. Dependency Rules

- **Depend on interfaces, not implementations.** `TetrisApp` holds
  `bot: BotInterface`; the concrete `BotRunner` is created only in
  `_init_bot`.
- **No pygame in logic modules.** pygame is confined to the integration
  layer — `tetris.py`, `renderer.py`, `ui_states.py`,
  `input_handler.py`, `audio_manager.py`. Logic modules (`engine.py`,
  `bot.py`, `contracts.py`, `config_manager.py`,
  `utils.py`) never import pygame; the shared `Action` vocabulary lives
  in `contracts.py`.
- **The renderer is read-only.** It takes a `GameState` snapshot, holds no
  reference to `TetrisApp`/`TetrisEngine`, and renders a generic
  `status_line` instead of knowing about "the bot".
- **The bot is a player, not a backdoor.** It emits `Action`s through the
  same path as human keyboard input (`TetrisApp._apply_action`), and is
  subject to the same gravity, lock delay, and scoring. Never give it direct
  engine access or disable game mechanics for it.
- When a module needs state from another module, prefer narrow, explicit
  interfaces (`BotSnapshot`, `tick(current_piece_id, make_snapshot)`) over
  passing whole objects.

## 7. Engine Conventions

- The grid is **bottom-origin**: `grid[0]` is the bottom row; y increases
  upward; a downward move is `dy = -1`.
- Pieces are defined as `(dx, dy)` offsets relative to the piece origin;
  rotation is the clockwise transform `(x, y) → (y, -x)`, shared by the bot's
  simulation.
- Spawn aligns the piece's highest cell to the top row, making spawn
  deterministic across piece types.
- Random generation uses a **7-bag** over `_ALL_PIECES`.
- Wall kicks are a pragmatic, non-SRS offset table; rotation state `0..3` is
  tracked for future SRS work.
- Every spawn increments `piece_id`; treat it as the identity of a piece
  *instance* (same-type pieces are still distinct instances).
- New geometry/collision logic must be added as a shared pure function in the
  primitives section so the bot's simulation stays in sync.

## 8. Testing

- Tests live in `tests/`, run with `pytest` from the repository root
  (`uv run pytest -q`).
- One test module per concern: `test_engine.py`, `test_engine_extra.py`,
  `test_bot.py`, `test_app.py`, `test_config.py`.
- White-box tests touch engine internals directly; such files carry the
  file-level `# pyright: reportPrivateUsage=false` directive on line 1 to
  suppress private-use diagnostics (no helper shim module is kept).
- Prefer deterministic setups: construct boards explicitly (annotated grids,
  explicit `piece_id`s) instead of depending on the random bag.
- Tests must be isolated and full-suite safe; no tests depend on real
  wall-clock timing (thread tests use timeouts and generous deadlines).
- App-level tests boot `TetrisApp` headless with dummy SDL drivers
  (`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`).

## 9. Tooling & QA

| Tool | Role | Config |
| --- | --- | --- |
| uv | Dependency/env management | `pyproject.toml`; dev deps: pillow, pyinstaller, pytest, ruff |
| ruff | Lint + import sort | `[tool.ruff] src = ["src"]` (pins the source root so classification is cwd-independent) |
| basedpyright | Type checking (strict) | `pyrightconfig.json`; tests excluded from CLI checks, kept strict via file directives |
| pytest | Tests | `tests/` |

- Run `ruff check .` and `uv run pytest -q` before committing; both must be
  clean.
- CI runs the same checks on ubuntu for every push to `main`
  (`.github/workflows/build.yml`); the macOS DMG is built on manual
  `workflow_dispatch` (Actions → Run workflow), and official releases are
  packaged from tags via `.github/workflows/release.yml`.

## 10. Git & Versioning

- Commit messages are written in **English**, short (≤ ~72-char subject)
  with a conventional prefix: `feat:`, `fix:`, `refactor:`, `style:`,
  `perf:`, `ci:`, `chore:`, `docs:`, `ui:`.
- When AI tooling contributed to the change, add a trailer naming the
  agent and the model it ran on:
  `Co-authored-by: <AI-Agent-Name> (<LLM Model Name>)`. The current
  project uses e.g.
  `Co-authored-by: oh-my-pi (deepseek/deepseek-v4-flash)`.
- Version lives in `pyproject.toml`; releases are tagged `vX.Y.Z` on `main`.
- Keep related changes in a single commit; squash noisy intermediate commits
  before pushing.

## 11. Checklist

Before submitting a change:

- [ ] Header comment updated if the file's responsibilities changed.
- [ ] New module-level names are `_`-private unless another module imports them.
- [ ] Full annotations; no `Any`-leak; strict check passes.
- [ ] No new coupling: no pygame in logic modules, no renderer knowing
      about the app/bot.
- [ ] `ruff check .` clean, `uv run pytest -q` green.
- [ ] Commit message in English with an appropriate prefix (+ `Co-authored-by`
      trailer when AI-assisted).
