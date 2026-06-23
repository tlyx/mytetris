# renderer.py — 我的方块独立渲染模块
# 负责所有与 Pygame 绘图相关的操作，完全与游戏逻辑和事件处理解耦。
#
# 设计原则：
#  1. 接收 GameState 对象（只读快照）作为输入。
#  2. 不持有任何 TetrisApp 或 TetrisEngine 的引用。
#  3. 只负责将状态绘制到给定的 Pygame Surface 上。

from typing import final

import pygame  # via pygame-ce

from engine import (
    COLORS,
    GRID_WIDTH,
    GRID_HEIGHT,
    SHAPES_DATA,
)
from game_state import GameState

# 方块大小（逻辑像素）
BLOCK_SIZE = 30

# 左右两侧边栏宽度（逻辑像素）
LEFT_WIDTH = 160
RIGHT_WIDTH = 200

# 逻辑分辨率（基于 BLOCK_SIZE=30）
SCREEN_WIDTH = LEFT_WIDTH + GRID_WIDTH * BLOCK_SIZE + RIGHT_WIDTH
SCREEN_HEIGHT = GRID_HEIGHT * BLOCK_SIZE

# ---- 布局常量（纯数字，绘制时乘以 scale） ----
# 左侧面板
LEFT_PADDING = 10                       # 左侧文字距面板左边缘
TITLE_Y = 20                            # "MyTetris" 标题的 y 坐标
TITLE_SEP_LINE_Y = 70                   # 标题下方分隔线 y 坐标
BOTTOM_MARGIN = 60                      # 底部留白（音乐/音效距离底部）
AUDIO_GAP = 10                          # 音乐行与音效行间距

# 右侧面板
CONTENT_PADDING = 20                    # 右侧文字距面板左/右内边距
LV_LABEL_Y = 20                         # "LEVEL" 标签 y 坐标
LV_VALUE_Y = 45                         # 等级数值 y 坐标
SCORE_LABEL_Y = 20                      # "SCORE" 标签 y 坐标（与 LV_Y 相同）
SCORE_VALUE_Y = 45                      # 分数数值 y 坐标
SEP_LINE_Y = 85                         # LEVEL/SCORE 下方分隔线 y 坐标
PREVIEW_Y = 130                         # 预览框顶部 y 坐标
RIGHT_BOTTOM_MARGIN = 60                # 底部统计信息距底部留白
RIGHT_GAP = 10                          # 底部统计行间距

# 预览框尺寸（逻辑块数，最大形状宽度为4）
PREVIEW_SIZE = 4

# 覆盖层
OVERLAY_GAP = 15                        # 覆盖层各行间距
HELP_GAP = 12                           # 帮助覆盖层各行间距
# -----------------------------------------

# ---- 消行动画持续时间（毫秒） ----
CLEAR_ANIM_DURATION = 200

# 帮助文本常量
HELP_LINES = [
    "HOW TO PLAY",
    "",
    "← →    Move left/right",
    "↓      Soft drop",
    "↑      Rotate",
    "Space  Hard drop",
    "",
    "P      Pause/Resume",
    "M      Toggle music",
    "S      Toggle sound effects",
    "G      Toggle ghost piece",
    "F1/?   Show this help",
    "",
    "Press any key to close.",
]


@final
class Renderer:
    """负责所有 Pygame 渲染逻辑，不依赖任何外部状态。"""

    # 字体缓存（外部在 scale 变化时调用 update_fonts 更新）
    font_big: pygame.font.Font | None
    font_small: pygame.font.Font | None
    help_font: pygame.font.Font | None

    # 静态背景缓存（scale 变化时重建）
    _static_bg: pygame.Surface | None
    _bg_scale: float  # 上一次构建静态背景时的 scale

    # 文字表面缓存（避免每帧重新渲染）
    _text_cache: dict[tuple[str, int], tuple[str, pygame.Surface]]

    # 消行动画相关
    _anim_clearing_rows: list[int]  # 当前正在闪烁的行
    _anim_start_ticks: int     # 动画起始 ticks

    # 底部统计标签文本和颜色（实例变量，避免每帧重建字典）
    _label_strs: dict[str, tuple[str, tuple[int, int, int]]]

    def __init__(self) -> None:
        self.font_big = None
        self.font_small = None
        self.help_font = None
        self._static_bg = None
        self._bg_scale = 0.0
        self._text_cache = {}
        self._anim_clearing_rows = []
        self._anim_start_ticks = 0

        # 初始化底部统计标签字典（仅一次，避免每帧重建）
        self._label_strs = {
            "lines_label": ("Lines: ", (200, 200, 200)),
            "high_label": ("High: ", (200, 200, 200)),
            "time_label": ("Time: ", (200, 200, 200)),
        }

    # ------------------------------------------------------------------
    # 字体更新接口（由外部在 scale 变化时调用）
    # ------------------------------------------------------------------
    def update_fonts(
        self, scale: float,
        font_big: pygame.font.Font,
        font_small: pygame.font.Font,
        help_font: pygame.font.Font,
    ) -> None:
        """更新三个字体引用并重建静态背景（如果 scale 与上次不同）。"""
        self.font_big = font_big
        self.font_small = font_small
        self.help_font = help_font

        # 字体改变后，文字缓存全部失效
        self._text_cache.clear()

        if abs(scale - self._bg_scale) > 1e-9:
            self._bg_scale = scale
            self._static_bg = self._build_static_bg(scale)

    # ------------------------------------------------------------------
    # 文字缓存辅助方法（缓存键包含字体标识，避免不同字体误用）
    # ------------------------------------------------------------------
    def _get_cached_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        """返回缓存的文字表面，仅在字符串变化时重新渲染。"""
        key = (text, id(font))
        cached = self._text_cache.get(key)
        if cached is not None and cached[0] == text:
            return cached[1]

        # 重新渲染并缓存
        surface = font.render(text, True, color)
        # font.render 不会返回 None，断言消除可选性
        assert surface is not None
        self._text_cache[key] = (text, surface)
        return surface

    # ------------------------------------------------------------------
    # 公开渲染入口
    # ------------------------------------------------------------------
    def render(
        self,
        state: GameState,
        logical: pygame.Surface,
        scale: float,
        now: int,  # 当前时间（毫秒），用于消行动画和底部时间统计
    ) -> None:
        """将游戏状态绘制到 logical 表面上。

        :param state: 游戏状态快照
        :param logical: 逻辑表面
        :param scale: 缩放比例
        :param now: 当前时间（毫秒），由外部传入（如 pygame.time.get_ticks()）
        """
        # 确保字体已经设置（update_fonts 必须在第一次 render 前调用）
        assert self.font_big is not None
        assert self.font_small is not None
        assert self.help_font is not None

        ds = logical

        # 1. 贴静态背景（如果缓存有效）
        if self._static_bg is not None:
            ds.blit(self._static_bg, (0, 0))
        else:
            # 降级：用 grid_line 纯色填充（不应发生）
            ds.fill(COLORS["GRID_LINE"])

        # 2. 计算常用缩放尺寸
        bs = int(BLOCK_SIZE * scale)
        left_width_px = int(LEFT_WIDTH * scale)
        right_width_px = int(RIGHT_WIDTH * scale)
        border_color = (80, 85, 95)

        board_left = left_width_px
        board_w = GRID_WIDTH * bs
        board_h = GRID_HEIGHT * bs
        sidebar_left = board_left + board_w

        # 3. 绘制主棋盘、当前块、边框（传入 now）
        self._draw_board(ds, state, bs, board_left, board_w, board_h, border_color, now)

        # 4. 绘制左侧面板
        self._draw_left_panel(
            ds, state, scale, left_width_px, logical.get_height(),
        )

        # 5. 绘制右侧侧边栏（传入 now）
        self._draw_right_panel(
            ds, state, scale, board_h, sidebar_left, right_width_px,
            border_color, logical.get_width(), logical.get_height(), now,
        )

        # 6. 绘制覆盖弹窗
        self._draw_overlays(
            ds, state, scale, logical.get_width(), logical.get_height(),
            board_left, board_w, board_h,
        )

    # ------------------------------------------------------------------
    # 静态背景构建（仅在 scale 变化时调用一次）
    # ------------------------------------------------------------------
    def _build_static_bg(self, scale: float) -> pygame.Surface:
        """预渲染所有不随游戏状态变化的部分（棋盘背景、面板背景、标签、分隔线等）。"""
        assert self.font_big is not None
        assert self.font_small is not None

        logical_w = int(SCREEN_WIDTH * scale)
        logical_h = int(SCREEN_HEIGHT * scale)
        bg = pygame.Surface((logical_w, logical_h))
        ds = bg

        # 填充棋盘网格颜色
        ds.fill(COLORS["GRID_LINE"])

        left_width_px = int(LEFT_WIDTH * scale)
        right_width_px = int(RIGHT_WIDTH * scale)
        bs = int(BLOCK_SIZE * scale)
        board_left = left_width_px
        board_w = GRID_WIDTH * bs
        sidebar_left = board_left + board_w

        # 游戏区域背景（覆盖至侧边栏左边缘）
        game_area_width = sidebar_left - board_left
        pygame.draw.rect(ds, COLORS["GRID_LINE"],
                         (board_left, 0, game_area_width, logical_h))

        # ---- 左侧面板背景 ----
        left_panel_rect = pygame.Rect(0, 0, left_width_px, logical_h)
        pygame.draw.rect(ds, (40, 45, 55), left_panel_rect)
        left_padding = int(LEFT_PADDING * scale)
        left_content_x = left_padding
        left_content_width = left_width_px - 2 * left_padding
        # 游戏名称（居中）
        title_surf = self.font_big.render("MyTetris", True, (255, 255, 255))
        title_x = left_content_x + (left_content_width - title_surf.get_width()) // 2
        ds.blit(title_surf, (title_x, int(TITLE_Y * scale)))
        # 分隔线（标题下方）
        sep_line_y = int(TITLE_SEP_LINE_Y * scale)
        pygame.draw.line(ds, (60, 60, 70),
                         (left_content_x, sep_line_y),
                         (left_content_x + left_content_width, sep_line_y), 1)

        # ---- 右侧面板背景 ----
        panel_rect = pygame.Rect(sidebar_left, 0,
                                 logical_w - sidebar_left, logical_h)
        pygame.draw.rect(ds, (40, 45, 55), panel_rect)
        content_padding = int(CONTENT_PADDING * scale)
        sidebar_content_left = sidebar_left + content_padding
        sidebar_content_right = sidebar_left + right_width_px - content_padding

        # LEVEL 与 SCORE 标签（静态文字）—— 已移至动态绘制，此处不再渲染
        # 分隔线（LEVEL/SCORE 下方）
        sep_y1 = int(SEP_LINE_Y * scale)
        pygame.draw.line(ds, (60, 60, 70),
                         (sidebar_content_left, sep_y1),
                         (sidebar_content_right, sep_y1), 1)

        # ---- 边框在动态绘制中完成，此处不再绘制 ----

        return bg

    # ------------------------------------------------------------------
    # 以下方法为原 TetrisApp 中各个 _draw_* 的直接迁移
    # ------------------------------------------------------------------

    def _draw_board(
        self, ds: pygame.Surface, state: GameState,
        bs: int, board_left: int,
        _board_w: int, _board_h: int, _border_color: tuple[int, int, int],
        now: int,  # 当前时间（毫秒），用于消行动画
    ) -> None:
        """绘制 10×20 棋盘、当前操控块
           同时绘制 ghost piece（落点影子）和消行动画闪烁"""
        # A. 绘制主棋盘（已锁定的方块）
        # 注意：engine 内部 grid 使用 bottom-origin (grid[0] 为底部)，
        # 渲染时需要将 internal row 映射为屏幕行（0=top）
        for screen_r in range(GRID_HEIGHT):
            engine_row = GRID_HEIGHT - 1 - screen_r
            for c in range(GRID_WIDTH):
                color: tuple[int, int, int] = (
                    state.grid[engine_row][c] or COLORS["GRID_LINE"]
                )
                rect = (board_left + c * bs, screen_r * bs, bs - 1, bs - 1)
                pygame.draw.rect(ds, color, rect)

        # B. 绘制 Ghost piece（半透明影子，仅在启用时绘制）
        if not state.game_over and state.ghost_enabled:
            ghost_y = state.ghost_y
            if ghost_y != state.current_y:
                ghost_color = COLORS[state.current_type]
                for dx, dy in state.current_shape:
                    gx = state.current_x + dx
                    gy = ghost_y + dy  # internal y (bottom-origin)
                    if 0 <= gy < GRID_HEIGHT:
                        screen_row = GRID_HEIGHT - 1 - gy
                        tx = board_left + gx * bs
                        ty_px = screen_row * bs
                        ghost_surf = pygame.Surface((bs - 1, bs - 1), pygame.SRCALPHA)
                        ghost_surf.fill((*ghost_color, 80))
                        ds.blit(ghost_surf, (tx, ty_px))

        # C. 绘制当前操控块（在 ghost piece 之上，覆盖它）
        if not state.game_over:
            for dx, dy in state.current_shape:
                gx = state.current_x + dx
                gy = state.current_y + dy
                if 0 <= gy < GRID_HEIGHT:
                    screen_row = GRID_HEIGHT - 1 - gy
                    rect = (
                        board_left + gx * bs,
                        screen_row * bs,
                        bs - 1,
                        bs - 1,
                    )
                    pygame.draw.rect(ds, COLORS[state.current_type], rect)

        # D. 消行动画闪烁（仅在启用时绘制）
        if state.clear_anim_enabled:
            # 检查是否有新的消除行需要启动动画
            if state.clearing_rows and state.clearing_rows != self._anim_clearing_rows:
                self._anim_clearing_rows = state.clearing_rows[:]
                self._anim_start_ticks = now  # 使用传入的 now

            # 如果当前有动画进行中
            if self._anim_clearing_rows:
                elapsed = now - self._anim_start_ticks
                if elapsed >= CLEAR_ANIM_DURATION:
                    # 动画结束
                    self._anim_clearing_rows = []
                else:
                    # 计算当前 alpha (从 255 渐变为 0)
                    alpha = int(255 * (1 - elapsed / CLEAR_ANIM_DURATION))
                    for row in self._anim_clearing_rows:
                        # 创建半透明白色矩形
                        flash_surf = pygame.Surface((_board_w, bs), pygame.SRCALPHA)
                        flash_surf.fill((255, 255, 255, alpha))
                        # row is internal (0=bottom); map to screen row
                        screen_row = GRID_HEIGHT - 1 - row
                        ds.blit(flash_surf, (board_left, screen_row * bs))
        else:
            # 动画禁用时，清空残留的动画状态
            self._anim_clearing_rows = []

        # 动态绘制棋盘边框（上、左、下）及右侧分隔线，覆盖可能残留的像素点
        pygame.draw.line(ds, _border_color, (board_left, 0),
                         (board_left + _board_w, 0), 2)
        pygame.draw.line(ds, _border_color, (board_left, 0),
                         (board_left, _board_h), 2)
        pygame.draw.line(ds, _border_color, (board_left, _board_h),
                         (board_left + _board_w, _board_h), 2)
        pygame.draw.line(ds, _border_color, (board_left + _board_w, 0),
                         (board_left + _board_w, _board_h), 2)

    def _draw_left_panel(
        self, ds: pygame.Surface, state: GameState,
        scale: float, left_width_px: int, logical_h: int,
    ) -> None:
        """绘制左侧面板（音乐/音效状态）。静态背景已包含背景和标题。"""
        assert self.font_small is not None

        if left_width_px <= 0:
            return
        left_padding = int(LEFT_PADDING * scale)
        left_content_x = left_padding

        # 音乐状态（使用缓存）
        music_str = "Music: " + ("ON" if state.music_enabled else "OFF")
        music_color = (0, 255, 0) if state.music_enabled else (200, 50, 50)
        music_surf = self._get_cached_text(
            music_str, self.font_small, music_color
        )

        # 音效状态（使用缓存）
        sfx_str = "SFX:    " + ("ON" if state.sfx_enabled else "OFF")
        sfx_color = (0, 255, 0) if state.sfx_enabled else (200, 50, 50)
        sfx_surf = self._get_cached_text(
            sfx_str, self.font_small, sfx_color
        )

        bottom_margin = int(BOTTOM_MARGIN * scale)
        gap_between = int(AUDIO_GAP * scale)

        sfx_y = logical_h - bottom_margin - sfx_surf.get_height()
        music_y = sfx_y - music_surf.get_height() - gap_between

        ds.blit(music_surf, (left_content_x, music_y))
        ds.blit(sfx_surf, (left_content_x, sfx_y))

    def _draw_right_panel(
        self, ds: pygame.Surface, state: GameState,
        scale: float, _board_h: int,
        sidebar_left: int, right_width_px: int,
        _border_color: tuple[int, int, int],
        _logical_w: int, logical_h: int,
        now: int,  # 当前时间（毫秒），用于时间统计
    ) -> None:
        """绘制右侧侧边栏（LEVEL/SCORE 区域、预览、底部统计）。
           布局修改为：
             Row1: "LEVEL" 标签 + 等级数值（标签颜色与 SCORE 相同，数值白色，
                     标签左对齐，数值右对齐）
             Row2: SCORE 标签（font_small，灰蓝色，左对齐）
             Row3: 得分数值（font_big，金色，右对齐）
        """
        assert self.font_big is not None
        assert self.font_small is not None

        content_padding = int(CONTENT_PADDING * scale)
        sidebar_content_left = sidebar_left + content_padding
        sidebar_content_right = sidebar_left + right_width_px - content_padding
        sidebar_content_width = sidebar_content_right - sidebar_content_left

        # ---------- 新布局：三行文字 ----------
        # 行间距（统一使用 RIGHT_GAP）
        row_gap = int(RIGHT_GAP * scale)

        # ---- Row1: "LEVEL" 标签 + 等级数值（标签左对齐，数值右对齐） ----
        lv_label_color = (150, 150, 160)   # 与 SCORE 标签颜色相同
        lv_val_color   = (255, 255, 255)   # 数值保持白色

        lv_label_text = "LEVEL"
        lv_val_text   = str(state.level)

        lv_label_surf = self._get_cached_text(
            lv_label_text, self.font_small, lv_label_color
        )
        lv_val_surf   = self._get_cached_text(
            lv_val_text,   self.font_small, lv_val_color
        )

        row1_y = int(LV_LABEL_Y * scale)
        ds.blit(lv_label_surf, (sidebar_content_left, row1_y))
        # 数值右对齐
        ds.blit(lv_val_surf,
                (sidebar_content_right - lv_val_surf.get_width(), row1_y))

        # 当前行的高度（用于后续偏移）
        row1_height = max(lv_label_surf.get_height(), lv_val_surf.get_height())

        # ---- 在 LEVEL 行与 SCORE 标签之间画分隔线 ----
        sep_color = (60, 60, 70)   # 与静态背景分隔线颜色一致
        sep_gap = int(6 * scale)   # 分隔线上下间距
        sep_y = row1_y + row1_height + sep_gap
        pygame.draw.line(ds, sep_color,
                         (sidebar_content_left, sep_y),
                         (sidebar_content_right, sep_y), 1)
        # SCORE 标签放在分隔线下方，同样留出间距
        sep_gap2 = int(6 * scale)
        row2_y = sep_y + sep_gap2

        # ---- Row2: SCORE 标签 ----
        score_label_str = "SCORE"
        score_label_surf = self._get_cached_text(
            score_label_str, self.font_small, (150, 150, 160)
        )
        ds.blit(score_label_surf, (sidebar_content_left, row2_y))

        # ---- Row3: 得分数值 ----
        score_str = f"{state.score:6d}"
        score_val_surf = self._get_cached_text(
            score_str, self.font_big, COLORS["SCORE_GOLD"]
        )
        row3_y = row2_y + score_label_surf.get_height() + row_gap
        ds.blit(score_val_surf,
                (sidebar_content_right - score_val_surf.get_width(), row3_y))

        # ---------- 预览框（下一个方块） ----------
        bs = int(BLOCK_SIZE * scale)
        preview_size = PREVIEW_SIZE * bs
        preview_x = sidebar_content_left + (sidebar_content_width - preview_size) // 2
        preview_y = int(PREVIEW_Y * scale)
        # 预览背景
        preview_rect_inner = pygame.Rect(preview_x, preview_y, preview_size, preview_size)
        pygame.draw.rect(ds, (40, 45, 55), preview_rect_inner)

        # NOTE: SHAPES_DATA uses the engine internal bottom-origin
        # coordinate system (y increases upward). When drawing the
        # preview (screen coordinates where y increases downward) we
        # must flip the vertical component so the preview matches the
        # in-play orientation seen on the main board.
        next_shape: list[tuple[int, int]] = SHAPES_DATA[state.next_type]
        xs = [dx for dx, _dy in next_shape]
        ys = [dy for _dx, dy in next_shape]
        min_dx = min(xs)
        max_dx = max(xs)
        min_dy = min(ys)
        max_dy = max(ys)
        shape_width = max_dx - min_dx + 1
        shape_height = max_dy - min_dy + 1
        offset_x = (preview_size - shape_width * bs) // 2
        offset_y = (preview_size - shape_height * bs) // 2

        # Map engine (dx, dy) -> screen pixels. For vertical mapping we use
        # (max_dy - dy) so that larger dy (higher in engine coords) appears
        # higher (smaller screen y) in the preview box.
        for dx, dy in next_shape:
            px = preview_x + offset_x + (dx - min_dx) * bs
            py = preview_y + offset_y + (max_dy - dy) * bs
            pygame.draw.rect(ds, COLORS[state.next_type], (px, py, bs - 1, bs - 1))

        # ---------- 底部统计信息：Lines, High, Time ----------
        elapsed_sec = (now - state.game_start_ticks) // 1000
        mins = elapsed_sec // 60
        secs = elapsed_sec % 60

        lines_str = str(state.total_lines)
        high_str = str(state.high_score)
        time_str = f"{mins:02d}:{secs:02d}"

        lines_val_surf = self._get_cached_text(
            lines_str, self.font_small, (255, 255, 255)
        )
        high_val_surf = self._get_cached_text(
            high_str, self.font_small, (255, 255, 255)
        )
        time_val_surf = self._get_cached_text(
            time_str, self.font_small, (255, 255, 255)
        )

        label_surfs: dict[str, pygame.Surface] = {}
        for key, (txt, clr) in self._label_strs.items():
            label_surfs[key] = self._get_cached_text(
                txt, self.font_small, clr
            )

        right_bottom_margin = int(RIGHT_BOTTOM_MARGIN * scale)
        right_gap = int(RIGHT_GAP * scale)

        temp_height = max(label_surfs["lines_label"].get_height(),
                          lines_val_surf.get_height())
        row_height = temp_height

        time_y = logical_h - right_bottom_margin - row_height
        high_y = time_y - row_height - right_gap
        lines_y = high_y - row_height - right_gap

        ds.blit(label_surfs["lines_label"], (sidebar_content_left, lines_y))
        ds.blit(lines_val_surf,
                (sidebar_content_left + label_surfs["lines_label"].get_width(), lines_y))

        ds.blit(label_surfs["high_label"], (sidebar_content_left, high_y))
        ds.blit(high_val_surf,
                (sidebar_content_left + label_surfs["high_label"].get_width(), high_y))

        ds.blit(label_surfs["time_label"], (sidebar_content_left, time_y))
        ds.blit(time_val_surf,
                (sidebar_content_left + label_surfs["time_label"].get_width(), time_y))

    # ------------------------------------------------------------------
    # 覆盖层绘制工具方法
    # ------------------------------------------------------------------

    def _draw_overlay_text(
        self, surface: pygame.Surface,
        logical_w: int, logical_h: int,
        scale: float,
        title: str,
        title_color: tuple[int, int, int],
        lines: list[tuple[str, tuple[int, int, int]]],
        alpha: int = 180,
        align_left: bool = False,
        overlay_rect: pygame.Rect | None = None,
    ) -> None:
        """绘制半透明覆盖层以及居中的标题和左对齐/居中的说明行。"""
        assert self.font_big is not None
        assert self.font_small is not None

        if overlay_rect:
            overlay = pygame.Surface((logical_w, logical_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha), overlay_rect)
        else:
            overlay = pygame.Surface((logical_w, logical_h))
            overlay.set_alpha(alpha)
            overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        gap = int(OVERLAY_GAP * scale)
        title_surf = self._get_cached_text(
            title, self.font_big, title_color
        )
        line_surfs: list[pygame.Surface] = []
        for text, color in lines:
            line_surf = self._get_cached_text(text, self.font_small, color)
            line_surfs.append(line_surf)

        total_h = (title_surf.get_height()
                   + sum(s.get_height() for s in line_surfs)
                   + len(lines) * gap)
        start_y = (logical_h - total_h) // 2

        # 标题始终居中
        tx = (logical_w - title_surf.get_width()) // 2
        surface.blit(title_surf, (tx, start_y))
        y = start_y + title_surf.get_height() + gap

        if align_left:
            indent = int(LEFT_WIDTH * scale)
        else:
            indent = 0

        for line_surf in line_surfs:
            if align_left:
                lx = indent
            else:
                lx = (logical_w - line_surf.get_width()) // 2
            surface.blit(line_surf, (lx, y))
            y += line_surf.get_height() + gap

    def _draw_help_overlay(
        self, surface: pygame.Surface,
        logical_w: int, logical_h: int,
        scale: float,
    ) -> None:
        """绘制半透明背景，居中显示帮助文字。"""
        assert self.help_font is not None

        overlay = pygame.Surface((logical_w, logical_h))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        title_line = HELP_LINES[0] if HELP_LINES else ""
        body_lines = HELP_LINES[1:] if len(HELP_LINES) > 1 else []

        title_color = (255, 200, 0)
        body_color = (255, 255, 255)

        # 帮助文字也使用缓存
        title_surf = self._get_cached_text(
            title_line, self.help_font, title_color
        )
        tx = (logical_w - title_surf.get_width()) // 2
        gap = int(HELP_GAP * scale)

        body_surfaces: list[pygame.Surface] = []
        for line in body_lines:
            surf = self._get_cached_text(line, self.help_font, body_color)
            body_surfaces.append(surf)

        total_body_h = sum(s.get_height() for s in body_surfaces) + \
                       (len(body_surfaces) - 1) * gap
        total_h = title_surf.get_height() + gap + total_body_h
        start_y = (logical_h - total_h) // 2

        surface.blit(title_surf, (tx, start_y))
        y = start_y + title_surf.get_height() + gap

        indent = int(LEFT_WIDTH * scale)
        for body_surf in body_surfaces:
            surface.blit(body_surf, (indent, y))
            y += body_surf.get_height() + gap

    def _draw_overlays(
        self, ds: pygame.Surface, state: GameState,
        scale: float, logical_w: int, logical_h: int,
        board_left: int, _board_w: int, _board_h: int,
    ) -> None:
        """绘制 Game Over / Pause / Confirm Quit / Help 弹窗。"""
        # 帮助覆盖层优先级最高
        if state.help_active:
            self._draw_help_overlay(ds, logical_w, logical_h, scale)
            return

        board_rect = pygame.Rect(board_left, 0, _board_w, _board_h)

        # Game Over
        if state.game_over:
            self._draw_overlay_text(
                ds, logical_w, logical_h, scale,
                "GAME OVER", (255, 0, 0),
                [
                    ("Press RETURN to restart", (255, 255, 255)),
                    ("Press ESC to quit", (255, 255, 255)),
                ],
                alpha=180, align_left=False, overlay_rect=board_rect,
            )

        # Pause
        elif state.paused:
            self._draw_overlay_text(
                ds, logical_w, logical_h, scale,
                "PAUSED", (255, 255, 0),
                [("Press P to resume", (255, 255, 255))],
                alpha=180, align_left=False, overlay_rect=board_rect,
            )

        # Confirm Quit
        if state.confirm_quit:
            self._draw_overlay_text(
                ds, logical_w, logical_h, scale,
                "QUIT ?", (255, 100, 100),
                [
                    ("Press ESC to confirm", (255, 255, 255)),
                    ("Press R to restart", (255, 255, 255)),
                    ("Any other key to cancel", (255, 255, 255)),
                ],
                alpha=200, align_left=True, overlay_rect=board_rect,
            )
