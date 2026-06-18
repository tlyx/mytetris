# game_state.py — 游戏状态快照数据类（不可变）
# 用于和渲染器解耦：渲染器只读取此对象，不依赖 TetrisApp 内部状态

from dataclasses import dataclass

@dataclass(frozen=True)
class GameState:
    """某一时刻游戏的所有渲染所需状态（只读快照）"""

    # 网格（20 行 × 10 列），每个元素为 COLORS 中的颜色值或 None
    grid: list[list[tuple[int, int, int] | None]]

    # 当前操控方块
    current_type: str
    current_shape: list[tuple[int, int]]
    current_x: int
    current_y: int

    # 下一个方块类型（仅用于绘制预览）
    next_type: str

    # 分数与等级
    score: int
    level: int
    total_lines: int

    # 最高分（持久化）
    high_score: int

    # 游戏开始时刻的ticks，用于计算游戏时长
    game_start_ticks: int

    # 状态标志
    game_over: bool
    paused: bool
    confirm_quit: bool
    help_active: bool

    # 音频开关（仅用于左侧面板显示文字）
    music_enabled: bool
    sfx_enabled: bool

    # Ghost piece（落点影子）的 y 坐标
    ghost_y: int

    # 消行动画：当前正在闪烁的行（可能是空列表）
    clearing_rows: list[int]
