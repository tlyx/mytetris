# MyTetris

A clean, object-oriented implementation of the classic Tetris game, built with Python and `pygame`.

[![Build status](https://github.com/tlyx/mytetris/actions/workflows/build.yml/badge.svg)](https://github.com/tlyx/mytetris/actions)
[![GitHub Release](https://img.shields.io/github/v/release/tlyx/mytetris)](https://github.com/tlyx/mytetris/releases/latest)

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
    git clone https://github.com/tlyx/mytetris.git
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

## macOS Gatekeeper Troubleshooting

Since this application is not signed with an official Apple Developer account, macOS Gatekeeper will block it upon first launch from the downloaded `.dmg`, showing a warning that the developer cannot be verified.

### How to bypass:

1. **GUI Method (Recommended)**: Drag `mytetris.app` to your `Applications` folder. Hold the **Control key** and **right-click** the app, then select **Open**. In the confirmation dialog that appears, click **Open**. You only need to do this once.
2. **Terminal Method**: Open your terminal and run the following command to strip the quarantine flag completely:
    ```bash
    xattr -cr /Applications/mytetris.app
    ```

## Controls

| Key              | Action                        |
|------------------|-------------------------------|
| ← / →            | Move piece left / right       |
| ↓                | Soft drop (accelerate)        |
| ↑                | Rotate piece                  |
| P                | Pause / Resume                |
| Space            | Hard drop(instantly to bottom)|
| Esc              | Toggle quit confirmation      |
| Return (Enter)   | Restart game (on Game Over)   |
| M                | Toggle background music       |
| S                | Toggle sound effects          |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
