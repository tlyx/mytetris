# MyTetris 编程风格指南

本文档描述 MyTetris 代码库使用的编程风格与约定。本文是 [STYLES.md](STYLES.md) 的中文翻译;代码注释与文档字符串使用中文(项目语言),提交信息与英文版指南使用英文。修改代码时请遵循以下规则以保持风格一致。

> **基准说明**:以英文版 `STYLES.md` 为唯一基准。本翻译仅作阅读便利;两者不一致时,以英文版为准,并请同步修订本文件。

---

## 目录

1. [语言与排版](#1-语言与排版)
2. [模块架构](#2-模块架构)
3. [命名约定](#3-命名约定)
4. [类型标注与静态分析](#4-类型标注与静态分析)
5. [模块头部与文档](#5-模块头部与文档)
6. [依赖规则](#6-依赖规则)
7. [引擎约定](#7-引擎约定)
8. [测试](#8-测试)
9. [工具与质量保障](#9-工具与质量保障)
10. [Git 与版本管理](#10-git-与版本管理)
11. [检查清单](#11-检查清单)

---

## 1. 语言与排版

- **Python 3.13+**(`requires-python = ">=3.13"`),依赖由 [uv](https://github.com/astral-sh/uv) 管理(`uv sync`、`uv run …`)。
- 行宽遵循 ruff 默认值(88 列);项目仅在 `[tool.ruff]` 中固定 `src = ["src"]`,其余依赖 ruff 默认配置。
- 导入顺序由 ruff 强制(`I001`):标准库 → 第三方 → 第一方,各组之间以空行分隔。若文件带有 `from __future__` 导入,它必须排在首位(何时需要见 §4)。
- 每个模块只承担一个职责;见 [模块架构](#2-模块架构)。
- 注释与文档字符串使用中文,与现有代码一致。行内注释解释*为什么*,不解释*是什么*。

## 2. 模块架构

代码按职责拆分,依赖方向严格单向。布局:全部代码位于 `src/`(平铺的顶层模块,非包),包括入口 `main.py`;`tests/`、`docs/` 位于项目根。导入解析:运行 `uv run src/main.py` 时解释器自动把脚本目录(src)加入路径;pytest 由 `tests/conftest.py` 注入 src;pyright 经 `extraPaths` 解析。

```
main.py → tetris.py (TetrisApp)
tetris.py → renderer.py, ui_states.py, keyboard_handler.py,
            audio_manager.py, config_manager.py, contracts.py,
            bot.py (BotRunner), engine.py (TetrisEngine)
bot.py → contracts.py, engine.py (仅共享几何原语)
renderer.py → contracts.py, engine.py (仅常量/形状)
```

| 模块 | 职责 |
| --- | --- |
| `main.py` | 入口;构造 `TetrisApp` 并运行。 |
| `tetris.py` | 应用外壳:窗口、事件循环、状态切换、输入路由、bot 驱动。 |
| `engine.py` | 纯游戏规则——无图形依赖,可独立单元测试。 |
| `renderer.py` | 将 `GameState` 绘制到 Surface;绝不触碰应用或引擎。 |
| `ui_states.py` | 状态模式:每个 UI 状态对应一个处理器类。 |
| `keyboard_handler.py` | 按键 → `Action` 映射与 DAS/ARR 自动重复。 |
| `contracts.py` | 跨组件契约:数据结构(`Action`、`GameState`、`BotSnapshot`)与接口协议(`BotInterface`、`AppInterface`)。 |
| `bot.py` | bot 决策与调度;对外暴露 `BotRunner`(协议/快照在 `contracts.py`)。 |
| `config_manager.py` | `config.json` 持久化。 |
| `audio_manager.py` | 音乐/音效加载与播放,优雅降级。 |
| `utils.py` | `resource_path`(兼容 PyInstaller 的资源路径解析)。 |

原则:

- **逻辑不进 UI。** 游戏规则在 `engine.py`;渲染器消费快照;应用负责串联。
- **bot 是外部智能体,不是游戏功能。** 游戏只通过 `BotInterface` 协议与每帧一次的 `tick()` 调用与它交互;渲染器对它一无所知(只绘制 `status_line`)。
- **共享规则是刻意为之。** 几何原语(`rotate_shape`、`collides`、`drop_y`、`spawn_y`、`cells_in_bounds`)是 `engine.py` 中的模块级纯函数,引擎与 bot 都从同一处导入,模拟语义永远不会漂移。
- **`TetrisApp` 按职责分组,且三处顺序一致。** 类注解、`__init__` 调用序列与 `_init_*` 帮手方法的顺序完全一致——配置 → 窗口与显示 → 引擎会话 → UI 流程 → 时间源 → 输入 → 渲染 → 音频 → bot——以 `# ---- … ----` 组头标记。新增成员时三处都要加到对应组;此约定无 lint 强制,靠手动维护。

## 3. 命名约定

| 类别 | 约定 | 示例 |
| --- | --- | --- |
| 类 | PascalCase | `TetrisEngine`、`BotRunner`、`GameState` |
| 函数 / 方法 | snake_case | `lock_and_clear_lines`、`cycle_strategy` |
| 模块级函数 | snake_case,内部实现加 `_` 前缀 | `_best_move`、`_evaluate` |
| 常量 | UPPER_SNAKE_CASE | `GRID_WIDTH`、`MAX_SCORE` |
| 私有常量 | `_` 前缀的 UPPER_SNAKE | `_MAX_LEVEL`、`_STATUS_COLOR` |
| 私有成员 | 下划线前缀 | `self._piece_resting`、`_Mailbox` |
| 类型别名 | PascalCase;内部使用时加 `_` | `_ConfigValue` |

规则:

- **只有被其他模块 import 的名字才算公开。** 仅在本模块内使用(或仅被白盒测试使用)的名字一律加下划线前缀。模块头部会明确写出公开 API 边界(见 `bot.py`)。
- 类属性在类级别标注类型,而不只在 `__init__` 中。
- 编码调优旋钮的常量留在所属模块中。

## 4. 类型标注与静态分析

- **严格模式。** `pyrightconfig.json` 设置 `typeCheckingMode: "strict"`,并关闭 `reportUnusedCallResult` 与 `reportAny`。
- **全量标注**:参数、返回值、模块级与类级属性、容器元素类型(`list[list[tuple[int, int, int] | None]]`,而不是裸 `list`)。
- 仅在注解引用运行时不可用的名字时才使用 `from __future__ import annotations`:前向引用或 `TYPE_CHECKING` 下导入的名字(本仓库唯一场景是 `ui_states.py`——它用 `TYPE_CHECKING` 导入的 `TetrisEngine` 做注解,Python 3.13 上必需)。不要处处添加:Python 3.14+(PEP 649)注解默认惰性求值,它在 3.14 上已是空操作。
- 对不允许被继承的类使用 `@final`(`TetrisEngine`、`TetrisApp`、`BotRunner`、`Renderer`、…)。
- 接口契约使用 `Protocol`(`BotInterface`、`AppInterface`);依赖协议,只在组合根(`TetrisApp._init_bot`)构造具体实现。
- 不可变数据载体使用 `@dataclass(frozen=True)`(`GameState`、`BotSnapshot`)。
- 属于实例契约的类级常量使用 `typing.ClassVar`(`TetrisEngine.SCORE_TABLE`)。
- 重写基类方法时使用 `@override`(见 `ui_states.py`)。
- 仅为统一签名而保留、未使用的参数,以下划线开头命名(`_landing_height`)。

## 5. 模块头部与文档

每个 `.py` 文件以如下形状的注释头开始:

```python
# <name>.py — <一句话定位>
# <职责描述>
#
# <设计说明(按需)>
#
# 此文件主要负责：
#  - <条目>
#  - <条目>

imports…
```

- 首行始终是 `<name>.py — …`,使用全角破折号。
- 条目清单列出文件的具体职责,职责变化时保持同步更新(不要让它腐化)。
- 头部保持聚焦;较长的设计说明放到拥有该设计的模块中(见 `bot.py`)。
- 测试文件保留模块文档字符串(它们说明测试套件);注释头放在文档字符串上方,`# pyright:` 文件级指令保持在**第 1 行**,以便类型检查器继续生效。
- **定义顺序**,以伪代码呈现:

  ```python
  # 模块级
  """<模块头部注释>"""
  imports …                             # 标准库 → 第三方 → 本地


  MODULE_CONSTANT = ...                 # 模块常量


  def public_helper(): ...              # 公开辅助函数在前


  def _private_helper(): ...            # 私有辅助函数在公开之后


  class Foo: ...                        # 类在最后


  if __name__ == "__main__": ...        # 仅入口模块


  # 类级
  class Foo:
      def __init__(self): ...           # 构造器最先

      def public_method(self): ...      # 公开 API，按职责分组

      def _private(self): ...           # 私有成员最后
  ```

  移动代码块时分节头注释随代码一起移动。

## 6. 依赖规则

- **依赖接口,不依赖实现。** `TetrisApp` 持有 `bot: BotInterface`;具体 `BotRunner` 只在 `_init_bot` 中创建。
- **逻辑模块不碰 pygame。** pygame 只存在于集成层——`tetris.py`、`renderer.py`、`ui_states.py`、`keyboard_handler.py`、`audio_manager.py`。逻辑模块(`engine.py`、`bot.py`、`contracts.py`、`config_manager.py`、`utils.py`)绝不 import pygame;共享的 `Action` 词汇表放在 `contracts.py`。
- **渲染器只读。** 它接收 `GameState` 快照,不持有 `TetrisApp`/`TetrisEngine` 引用,渲染通用的 `status_line` 而不是了解"bot"。
- **bot 是玩家,不是后门。** 它通过与人类键盘输入完全相同的路径(`TetrisApp._apply_action`)发出 `Action`,并受同样的重力、锁定延迟与计分约束。绝不给它直接访问引擎的能力,也不要为它关闭游戏机制。
- 模块需要其他模块的状态时,优先使用窄而显式的接口(`BotSnapshot`、`tick(current_piece_id, make_snapshot)`),而不是传递整个对象。

## 7. 引擎约定

- 网格为**底部原点**:`grid[0]` 是底行;y 向上递增;向下移动是 `dy = -1`。
- 方块以相对方块原点的 `(dx, dy)` 偏移定义;旋转使用顺时针变换 `(x, y) → (y, -x)`,与 bot 模拟共享。
- 生成时把方块最高单元对齐到顶行,使各类型方块的生成位确定。
- 随机生成使用基于 `_ALL_PIECES` 的 **7-bag**。
- Wall kick 是实用而非 SRS 的偏移表;记录旋转状态 `0..3` 供未来 SRS 工作使用。
- 每次生成递增 `piece_id`;把它视为方块*实例*的身份(同类型方块仍是不同实例)。
- 新增几何/碰撞逻辑必须作为共享纯函数加入原语区,保持 bot 模拟同步。

## 8. 测试

- 测试位于 `tests/`,从仓库根目录运行 `pytest`(`uv run pytest -q`)。
- 按职责拆分测试模块:`test_engine.py`、`test_engine_extra.py`、`test_bot.py`、`test_app.py`、`test_config.py`。
- 白盒测试直接访问引擎内部;这类文件在第 1 行携带文件级 `# pyright: reportPrivateUsage=false` 指令压制私有访问诊断(不保留辅助 shim 模块)。
- 优先确定性构造:显式构造盘面(标注类型的 grid、显式 `piece_id`),而不是依赖随机 bag。
- 测试必须相互隔离、整包安全;不得依赖真实墙钟时序(线程测试使用超时与宽裕的截止时间)。
- App 层测试以 dummy SDL 驱动无头启动 `TetrisApp`(`SDL_VIDEODRIVER=dummy`、`SDL_AUDIODRIVER=dummy`)。

## 9. 工具与质量保障

| 工具 | 职责 | 配置 |
| --- | --- | --- |
| uv | 依赖/环境管理 | `pyproject.toml`;dev 依赖:pillow、pyinstaller、pytest、ruff |
| ruff | Lint + 导入排序 | `[tool.ruff] src = ["src"]`(固定源码根,使分类不随运行目录变化) |
| basedpyright | 类型检查(strict) | `pyrightconfig.json`;CLI 检查排除 tests,经文件级指令保持严格 |
| pytest | 测试 | `tests/` |

- 提交前运行 `ruff check .` 与 `uv run pytest -q`,两者必须全绿。
- CI 在每次 push 到 `main` 时于 ubuntu 运行同样的检查(`.github/workflows/build.yml`);macOS DMG 通过手动 `workflow_dispatch` 构建(Actions → Run workflow),正式发版由 tag 触发 `.github/workflows/release.yml` 打包。

## 10. Git 与版本管理

- 提交信息使用**英文**,简短(主题 ≤ ~72 字符),带约定前缀:`feat:`、`fix:`、`refactor:`、`style:`、`perf:`、`ci:`、`chore:`、`docs:`、`ui:`。
- 当 AI 工具参与了改动,添加署名尾注,注明智能体名称与其运行的模型:
  `Co-authored-by: <AI-Agent-Name> (<LLM Model Name>)`。当前项目使用例如
  `Co-authored-by: oh-my-pi (deepseek/deepseek-v4-flash)`。
- 版本号位于 `pyproject.toml`;发版在 `main` 上打 `vX.Y.Z` tag。
- 相关改动合并为单个提交;推送前合并零碎的中间提交。

## 11. 检查清单

提交改动前:

- [ ] 若文件职责发生变化,更新头部注释。
- [ ] 新模块级名字除非被其他模块 import,否则加 `_` 前缀。
- [ ] 全量标注;无 `Any` 泄漏;严格检查通过。
- [ ] 无新增耦合:逻辑模块不碰 pygame,渲染器不知道应用/bot。
- [ ] `ruff check .` 干净,`uv run pytest -q` 全绿。
- [ ] 提交信息为英文并带合适前缀(AI 协助时附 `Co-authored-by` 尾注)。

### 发布前清洁(时间盒约 30 分钟,在 bump 版本之前)

- [ ] **语义审计**——通览全部名字清单,专找"名字已不覆盖其概念"的(如名字与注释互相矛盾,或拆分后概念扩界——bot 成为第二个 Action 来源时 `InputHandler` → `KeyboardHandler`)。
- [ ] **死代码/死 API**——公开物不得只有测试引用(白盒测试直接访问 `_` 内部,不留 shim);共享数据结构的每个字段都有真实读者。
- [ ] **注释与代码一致**——docstring 与模块头"此文件主要负责"条目反映当前行为,而非重构前的。
- [ ] **文档漂移**——STYLES 英中互查且与实际配置一致(`src = ["src"]`、CI 触发方式、测试模块清单);README 功能与按键表最新。
- [ ] **全量验证**——`pytest`、ruff、basedpyright、无头冒烟全绿。
- [ ] 全部通过后才 bump 版本并发布。
