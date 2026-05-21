# MyTetris

A clean, object-oriented implementation of the classic Tetris game, built with Python and `pygame`.

## Features

*   **Classic Gameplay**: Includes all 7 standard tetrominoes with rotation and collision detection.
*   **Modular Architecture**: Clean separation between game engine logic (`TetrisEngine`) and application framework (`TetrisApp`).
*   **Smooth Rendering**: Built for 60 FPS performance.
*   **UI Features**: Next piece preview and real-time score tracking.

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
uv run python main.py
```

## Controls

*   **Left/Right Arrow**: Move piece
*   **Down Arrow**: Soft drop
*   **Up Arrow**: Rotate
*   **Esc**: Quit game
