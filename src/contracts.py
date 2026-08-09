# contracts.py — 跨组件共享的契约（数据结构与接口协议）
#
# 此文件主要负责：
#  - Action：输入层与 bot 的公共动作词汇（人类键盘与 bot 走同一路径）
#  - GameState：游戏侧构造、渲染器消费的只读渲染快照
#  - BotSnapshot：游戏侧构造、bot 线程消费的只读状态快照
#  - BotInterface / AppInterface：bot 与状态机的接口协议（行为契约）

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

# 仅用于注解；运行时零依赖（type-only 边，避免与 keyboard_handler 的导入环）
if TYPE_CHECKING:
    from config_manager import ConfigManager
    from engine import GameEngine
    from keyboard_handler import KeyboardHandler


class Action(Enum):
    """游戏操控动作枚举。"""
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    SOFT_DROP = auto()
    HARD_DROP = auto()
    ROTATE = auto()


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
    combo: int

    # 最高分（持久化）
    high_score: int

    # 游戏开始时刻的 ticks，用于计算游戏时长
    game_start_ticks: int

    # 状态标志
    game_over: bool
    paused: bool
    confirm_quit: bool
    help_active: bool

    # 音频开关（仅用于左侧面板显示文字）
    music_enabled: bool
    sfx_enabled: bool

    # Ghost piece（落点影子）相关
    ghost_y: int
    ghost_enabled: bool

    # 消行动画相关
    clearing_rows: list[int]
    clear_anim_enabled: bool

    # 实时状态行（右侧面板 Time 下方）：非空时显示，渲染器不关心内容含义
    status_line: str


@dataclass(frozen=True)
class BotSnapshot:
    """游戏侧构造、bot 侧消费的只读游戏状态快照（grid 为行拷贝）。"""

    grid: list[list[tuple[int, int, int] | None]]
    current_type: str
    current_x: int
    # 当前旋转状态 0..3（_plan_to_actions 按相对量计算按键次数）
    rotation: int
    next_type: str
    level: int
    game_over: bool
    # 当前方块实例 id（引擎每次生成新块 +1）：同一类型但不同的块 id 不同，
    # 是 bot 识别"换块了"的可靠依据（方块类型可能连续相同）。
    piece_id: int


# ------------------------------------------------------------------
# 接口协议（行为契约；实现位于各自组合根：BotRunner / GameApp）
# ------------------------------------------------------------------

class BotInterface(Protocol):
    """游戏主体依赖的 bot 接口（可整体替换实现）。

    GameApp 只依赖此协议：换 bot 实现（如深度强化学习版）时，
    提供同接口即可，游戏代码零改动。
    """

    @property
    def strategy(self) -> str: ...

    def start(self) -> None: ...
    def stop(self, timeout: float = 1.0) -> None: ...
    def cycle_strategy(self) -> str: ...
    def tick(
        self,
        current_piece_id: int,
        make_snapshot: Callable[[], BotSnapshot],
    ) -> list[Action]: ...


class AppInterface(Protocol):
    """GameApp 对外暴露的接口（供状态处理器调用）。"""
    game: GameEngine
    keyboard_handler: KeyboardHandler
    config: ConfigManager
    paused: bool
    confirm_quit: bool
    fall_event: int

    @property
    def now(self) -> int: ...  # 当前时间（毫秒），由外部提供

    def toggle_pause(self) -> None: ...
    def handle_fall_timer(self) -> None: ...
    def toggle_help(self) -> None: ...
    def restart_game(self) -> None: ...
    def handle_quit(self) -> None: ...
