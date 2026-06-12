# MyTetris

A clean, object-oriented implementation of the classic Tetris game, built with Python and `pygame`.

## Features

*   **Classic Gameplay**: Includes all 7 standard tetrominoes with rotation, wall‑kick, and collision detection.
*   **Modular Architecture**: Clean separation between game engine logic (`TetrisEngine`) and application framework (`TetrisApp`).
*   **Dynamic Difficulty**: Speed increases as you level up (every 10 lines).
*   **Smooth Rendering**: Built for 60 FPS performance with hardware‑accelerated surfaces.
*   **Intuitive UI**:
    *   Real‑time score, level, and lines cleared display.
    *   Next‑piece preview.
    *   Game‑over overlay with restart prompt.
    *   Pause/Resume screen.
    *   Quit‑confirmation dialog.
*   **Resizable Window**: The game scales automatically to any window size (minimum 400×400), keeping a crisp, centered view.
*   **Audio**:
    *   Background music with toggle (M key).
    *   Sound effects for line clears and game over, with toggle (S key).
*   **High Score Persistence**: Best score is saved automatically across sessions.

## Prerequisites

*   Python 3.x
*   [uv](https://github.com/astral-sh/uv) (for dependency management)

## Setup

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd mytetris
    ```

2.  Sync dependencies:
    ```bash
    uv sync
    ```

## Usage

Run the game using:
```bash
uv run main.py
```

## Controls

| Key              | Action                        |
|------------------|-------------------------------|
| ← / →            | Move piece left / right       |
| ↓                | Soft drop (accelerate)        |
| ↑                | Rotate piece                  |
| Space            | Pause / Resume                |
| Esc              | Toggle quit confirmation      |
| Return (Enter)   | Restart game (on Game Over)   |
| M                | Toggle background music       |
| S                | Toggle sound effects          |
