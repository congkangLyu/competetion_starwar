# Orbit Wars — Agent 研究脚手架

> [English version](README.md)

为 Kaggle [Orbit Wars](https://www.kaggle.com/competitions/orbit-wars)
竞赛搭建的研究基础设施。仓库被组织成一个小型 Python 包(`orbit_wars/`)
加一套构建工具链 —— 把 YAML 策略文件打成 Kaggle 期望的单文件 `main.py`。

**你只负责写策略(YAML 或 Agent 子类),工具链负责:**
构建、烟雾测试、并行评估、Elo 锦标赛、复盘可视化、提交。

- **游戏规则与物理**:见 [GAME_RULES.md](GAME_RULES.md)
- **Kaggle CLI 速查表**:见 [agents.md](agents.md)
- **参考 Notebook**:见 `information/`

---

## 概览

```
configs/blitz.yaml ──► build_submission ──► main.py ──► kaggle submit
                                                │
orbit_wars/agents/ ──┐                          │
orbit_wars/core/    ──┤── inline 进 ───────────┘
orbit_wars/eval/    ──┤
orbit_wars/analysis/──┘   (eval/analysis 只在本地用,不上 Kaggle)

7 套 smoke 测试 · 237 个独立 check · 61 个 pytest 函数
```

| 层 | 内容 | 上 Kaggle? |
|---|---|---|
| `orbit_wars/core/` | `GameState`、`Planet`、`Fleet`、`Move`、几何原语 | ✅ |
| `orbit_wars/agents/` | `Agent` ABC、`SniperAgent`、`HeuristicAgent` | ✅ |
| `orbit_wars/eval/` | 并行 runner、衍生指标、锦标赛、Elo | ❌ |
| `orbit_wars/analysis/` | replay 加载、SVG/HTML 可视化 | ❌ |
| `tools/` | CLI 入口(build、eval、tournament、viz) | ❌ |
| `configs/` | YAML 策略预设(唯一真相源) | inline 进 main.py |
| `tests/` | 7 套 smoke 测试(pytest 兼容) | ❌ |

---

## 快速开始

```bash
# 1. 装依赖
pip install kaggle-environments PyYAML pytest

# 2. 验证全部工作正常
make test          # 跑 7 套 smoke,期望 237 行 [OK ]
make pytest        # 同样的测试走 pytest 收集器

# 3. 构建当前提交文件
make build PRESET=blitz       # 从 configs/blitz.yaml 写出 main.py

# 4. 跟 kaggle random agent 打 6 局
python tools/eval.py main.py random -n 6
```

Windows 没装 `make`?用下面 [CLI 参考](#cli-参考) 里的直接 `python ...`
命令即可。

---

## 软件架构

### 分层视图

```
┌─────────────────────────────────────────────────────────────────────┐
│              CLI 工具  (tools/*.py)                                 │
│  build_submission · eval · tournament · viz · replay                │
└───────┬─────────────────┬──────────────┬───────────────┬────────────┘
        │                 │              │               │
        ▼                 ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              开发基础设施  (eval/, analysis/)                       │
│  runner · metrics · tournament · replay loader · SVG/HTML 渲染      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ 单向 import(永不反向)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│           可上 Kaggle 的代码  (agents/, core/)                      │
│  Agent ABC · SniperAgent · HeuristicAgent · GameState · geometry    │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
                Python 标准库 + kaggle_environments(仅运行时)
```

**关键不变量**:`core/` 和 `agents/` 永远不 import `eval/`、
`analysis/`、`tools/`。否则构建脚本无法把它们 inline 进 `main.py`。
这条由 `tests/smoke_test_build.py` 守护。

### 数据流 1:Kaggle 提交链路

```
configs/blitz.yaml ─┐
core/geometry.py ───┤
core/state.py ──────┼──► tools/build_submission.py ──► main.py ──► kaggle
agents/base.py ─────┤        (拼接 + 烟雾测试)         (单一文件)
agents/heuristic.py ┘
```

构建出来的 `main.py` 与手工维护的 `main.py` 在测试覆盖的 obs 下
**byte-equivalent**(逐 move 完全相同) —— 由 `smoke_test_build.py`
的 10 回合 parity 测试守护。

### 数据流 2:本地评估链路

```
agent specs ──► run_matches ──► [worker 里的 kaggle env] ──► env.steps
("preset:blitz"      │                                            │
 "random"            │                                            ▼
 "file:main.py")     │                                compute_metrics()
                     ▼                                            │
              MatchResult(每局一个)◄─── metrics_a/b ────────────┘
                     │
       ┌─────────────┼─────────────────┐
       ▼             ▼                 ▼
   results.jsonl  Summary 文本    Tournament + Elo
```

---

## 项目布局

```
competetion_starwar/
│
├── README.md                    # 英文版
├── README.zh-CN.md              # 本文件(中文版)
├── GAME_RULES.md                # 官方 orbit_wars 规则(改名自原 README)
├── agents.md                    # Kaggle CLI 速查表(submit/replay/logs)
├── Makefile                     # 快捷命令;详见 `make help`
├── pytest.ini                   # pytest 发现规则 + addopts
├── requirements.txt             # 运行时 + 开发依赖
├── .gitignore
│
├── main.py                      # 当前 Kaggle 提交版(用 make 重建)
│
├── configs/                     # ── 策略参数唯一真相源 ──
│   ├── blitz.yaml               # 72.2% baseline(当前提交)
│   ├── sentinel.yaml            # blitz + 防御增援
│   └── sniper.yaml              # 朴素最近邻基线
│
├── orbit_wars/                  # ── Python 包 ──
│   ├── __init__.py              # 常用符号 re-export
│   ├── core/                    # 上 Kaggle:数据 + 物理原语
│   │   ├── state.py             # GameState、Planet、Fleet、Move、CometGroup
│   │   └── geometry.py          # fleet_speed、seg_hits_sun、orbital_position
│   ├── agents/                  # 上 Kaggle:agent 实现
│   │   ├── base.py              # Agent ABC、Decision、make_kaggle_agent
│   │   ├── sniper.py            # SniperAgent(基线)
│   │   └── heuristic.py         # HeuristicAgent + HeuristicConfig
│   ├── eval/                    # 仅本地:评估框架
│   │   ├── runner.py            # MatchResult、run_match、run_matches
│   │   ├── metrics.py           # PlayerMetrics、compute_metrics
│   │   └── tournament.py        # Tournament、Elo、排行榜
│   └── analysis/                # 仅本地:replay + 可视化
│       ├── replay.py            # load_kaggle_replay、extract_states
│       └── viz.py               # render_frame_svg、render_replay_html
│
├── tools/                       # CLI 入口(脚本,不被 import)
│   ├── build_submission.py      # YAML 预设 -> 单文件 main.py
│   ├── eval.py                  # 两 agent 本地对战
│   ├── tournament.py            # N agent round-robin + Elo
│   ├── viz.py                   # replay JSON -> 交互式 HTML
│   └── replay.py                # 临时 replay 助手
│
├── tests/                       # smoke 套件(也兼容 pytest)
│   ├── conftest.py              # autouse kaggle_environments 桩
│   ├── smoke_test_core.py
│   ├── smoke_test_agents.py
│   ├── smoke_test_build.py
│   ├── smoke_test_eval.py
│   ├── smoke_test_metrics.py
│   ├── smoke_test_viz.py
│   └── smoke_test_tournament.py
│
├── agents/                      # 老代码,保留供 parity 测试用
│   ├── sniper.py                # 老的独立 sniper(基线)
│   └── blitz.py                 # 老的独立 blitz(仍 byte-equivalent)
│
├── evaluate.py                  # 老脚本,已被 tools/eval.py 取代
└── information/                 # 原始 notebook(EDA、混合 agent 等)
    ├── getting-started.ipynb
    ├── orbit-wars-complete-guide-eda-agents-submission.ipynb
    └── orbit-wars-tamrazov-ykhnkf-hybrid.ipynb
```

---

## 常用工作流

### 跑全部测试(健康检查)

```bash
make test            # 7 套 standalone smoke 顺序跑
make pytest          # pytest 收集器,可并行,输出更友好
make pytest-verbose  # 加 -v -s flag
```

### 调一组策略参数

```bash
# 1. 复制现有预设
cp configs/blitz.yaml configs/aggressive.yaml

# 2. 编辑权重(任意编辑器)
nano configs/aggressive.yaml
#   例如  enemy_bonus: 1.0   ->  2.0
#         attack_buffer: 1.0 -> 1.2

# 3. 构建并烟雾测试
python tools/build_submission.py aggressive -o _build/aggressive.py

# 4. 对比基线打 20 局(4 个并行 worker)
python tools/eval.py preset:aggressive preset:blitz -n 20 -p 4 -o cmp.jsonl
```

JSONL 每行是一局的完整记录,带 `reward`、`winner` 和嵌套的
`PlayerMetrics`(planets captured/lost、ships lost to sun、peak planets 等)。
可以直接喂给 `jq` 或 pandas 做分析。

### 跑 round-robin 锦标赛

```bash
python tools/tournament.py \
    preset:blitz preset:sentinel preset:sniper preset:aggressive random reaction \
    -n 30 -p 8 --seed 42 -o tourneys/run-2025-05-17
```

stdout 输出:按 Elo 排序的排行榜 + pairwise 胜率矩阵。
输出目录:`matches.jsonl`、`leaderboard.csv`、`tournament.json`(机器可读摘要)。

### 可视化一局对战

先把 replay dump 出来(在 Python 里):

```python
from pathlib import Path
from kaggle_environments import make
env = make("orbit_wars", configuration={"seed": 7}, debug=False)
env.run(["main.py", "random"])
Path("replays").mkdir(exist_ok=True)
Path("replays/g7.json").write_text(env.toJSON())
```

然后渲染:

```bash
python tools/viz.py replays/g7.json -o replay.html
# 用任意浏览器打开 replay.html,拖滑块或点 play 按钮
```

要叠加 agent 的决策日志(意图射线),加
`--decisions logs/p0.jsonl`,其中 `p0.jsonl` 由
`decisions_to_jsonl(agent.decisions)` 生成。

---

## 提交到 Kaggle

### 一次性设置

1. 装 Kaggle CLI:`pip install kaggle`
2. 在 https://www.kaggle.com/settings 生成 API token("Create new
   API token"),把下载的 `kaggle.json` 放到:
   - Linux/Mac:`~/.kaggle/kaggle.json`
   - Windows: `C:\Users\<你>\.kaggle\kaggle.json`
3. 在比赛页面点 "Join Competition" 接受规则:
   https://www.kaggle.com/competitions/orbit-wars
4. 验证:`kaggle competitions list --group entered` 应该列出 orbit-wars。

### 提交

```bash
# 1. 从你想上线的 YAML 预设重建 main.py
make build PRESET=blitz
#  → 写出 main.py,头部含 git commit hash + UTC 时间戳
#  → 自动跑 5 回合烟雾测试,通过才返回成功

# 2. 提交
kaggle competitions submit orbit-wars -f main.py -m "blitz preset, commit abc123"

# 3. 监控
kaggle competitions submissions orbit-wars
```

对于多文件打包(罕见 —— 我们的构建已把一切 inline 进单个文件),
用 tar.gz,`main.py` 放根目录,再提交:

```bash
tar -czf sub.tar.gz main.py extra_helper.py model_weights.pkl
kaggle competitions submit orbit-wars -f sub.tar.gz -m "..."
```

### 查看提交结果

```bash
# 列出你的所有提交(留意 SUBMISSION_ID 列)
kaggle competitions submissions orbit-wars

# 这个提交打过的对局
kaggle competitions episodes <SUBMISSION_ID>

# 下载单局 replay JSON + agent 日志
kaggle competitions replay <EPISODE_ID> -p ./replays
kaggle competitions logs <EPISODE_ID> 0 -p ./logs   # 0 = 第 1 个 agent
```

然后 `python tools/viz.py replays/<file>.json -o out.html` 看可视化。

### 查看排行榜

```bash
kaggle competitions leaderboard orbit-wars -s
```

---

## 添加新 agent

继承 `Agent` 并实现 `act(state) -> list[Move]`:

```python
# orbit_wars/agents/my_idea.py
from orbit_wars.agents.base import Agent
from orbit_wars.core.geometry import angle_to, dist, fleet_speed, seg_hits_sun
from orbit_wars.core.state import GameState, Move

class MyAgent(Agent):
    """一句话描述策略."""

    name = "my_idea"

    def act(self, state: GameState) -> list[Move]:
        moves: list[Move] = []
        for src in state.my_planets:
            # ... 你的策略 ...
            move = Move(src.id, angle_to(src.x, src.y, tgt.x, tgt.y), ships)
            moves.append(move)
            self.log(move, reason="my_reason", **extra_meta)
        return moves
```

你免费拥有:
- `state.my_planets`、`state.enemy_planets`、`state.neutral_planets`、
  `state.planet_by_id`、`state.my_fleets`、`state.enemy_fleets`、
  `state.comet_planet_ids`
- `state.angular_velocity` + `state.initial_planets` 用于轨道预测
  (见 `orbit_wars.core.geometry.orbital_position`)
- `state.step`、`state.remaining_time`
- 通过 `self.log(move, reason=..., **meta)` 自动记决策日志
- 生命周期钩子:`on_game_start(state)`、`on_game_end(state, reward)`
- `reset()` 用于 game 之间状态隔离(runner 自动调用)

让它可被提交,做以下事:

1. 在 `tools/build_submission.py` 里注册类:
   ```python
   AGENT_MODULES: dict[str, list[Path]] = {
       "SniperAgent":    [ROOT / "orbit_wars" / "agents" / "sniper.py"],
       "HeuristicAgent": [ROOT / "orbit_wars" / "agents" / "heuristic.py"],
       "MyAgent":        [ROOT / "orbit_wars" / "agents" / "my_idea.py"],   # ← 加这行
   }
   ```
2. 在 `render_adapter()` 里加一个对应分支,生成正确的实例化代码
   (只有 agent 需要构造参数时才需要)。
3. 写一份 YAML 预设(见下一节)。
4. 在 `orbit_wars/agents/__init__.py` re-export(让测试 / import 能找到)。

## 添加新策略预设

```yaml
# configs/my_idea.yaml
name: my_idea
description: |
  简短描述,会出现在构建出的 main.py 文件头 docstring 里。

agent: MyAgent          # 必须是 tools/build_submission.py 里
                        # AGENT_MODULES 的一个 key

config:                 # 作为 **kwargs 传给 MyAgent(...)
  # 如果你的 agent 接受一个 dataclass 配置(类似 HeuristicConfig):
  some_weight: 1.5
  threshold:   10
```

然后:

```bash
python tools/build_submission.py my_idea -o _build/my_idea.py
python tools/eval.py preset:my_idea preset:blitz -n 50 -p 8 -o cmp.jsonl
```

---

## CLI 参考

### `tools/build_submission.py`

| Flag | 默认 | 含义 |
|---|---|---|
| `preset`(位置参数) | — | `configs/` 下的 YAML 名 |
| `-o, --output` | `main.py` | 输出路径(可在 repo 内或外) |
| `--no-check` | 关 | 跳过构建后的 5 回合 import 烟雾测试 |

### `tools/eval.py`

| Flag | 默认 | 含义 |
|---|---|---|
| `agent_a agent_b` | — | 两个 agent spec(见下) |
| `-n, --games` | 6 | 总局数(在两个位置间均分) |
| `-p, --parallel` | 1 | 进程池大小 |
| `--seed` | None | 派生每局 seed 的根 seed |
| `--no-balance` | 关 | 不做位置交换 |
| `--episode-steps` | None | 覆盖 kaggle `episodeSteps`(默认 500) |
| `-o, --output` | None | 把每局结果写到这里(JSONL) |

### `tools/tournament.py`

| Flag | 默认 | 含义 |
|---|---|---|
| `agents`(位置参数,≥2) | — | 互不重复的 agent spec 列表 |
| `-n, --games-per-pair` | 6 | 每对组合打几局 |
| `-p, --parallel` | 1 | 进程池大小 |
| `--seed` | None | 根 seed |
| `--no-balance` | 关 | 不做位置交换 |
| `--k` | 32 | Elo K 因子 |
| `--initial-elo` | 1500 | 起始 Elo |
| `-o, --output-dir` | None | 写出 matches.jsonl + leaderboard.csv + tournament.json |

### `tools/viz.py`

| Flag | 默认 | 含义 |
|---|---|---|
| `replay`(位置参数) | — | Kaggle replay JSON 路径 |
| `-o, --output` | `replay.html` | 输出 HTML 路径 |
| `--player` | 0 | 用哪个玩家视角(只影响内部 `my_planets` 计算) |
| `--decisions` | None | 要叠加的 decisions JSONL |
| `--title` | 文件名 | HTML 标题 |
| `--width` | 640 | SVG 像素宽度 |

### `eval.py` / `tournament.py` 接受的 agent spec 形式

| spec | 含义 |
|---|---|
| `preset:NAME` | 把 `configs/NAME.yaml` 构建到临时文件,用它 |
| `file:PATH` | 直接用 PATH 这个 .py 文件 |
| `PATH`(如 `main.py`) | 等价于 `file:PATH`,只要文件存在 |
| `random` | Kaggle 内置随机 agent |
| `reaction` | Kaggle 内置反应式 agent |

---

## Makefile 目标

```text
make help              显示这个列表
make test              跑全部 7 套 standalone smoke
make test-core         单独跑一套(把 core 换成 agents/build/eval/
                          metrics/viz/tournament 任意一个)
make pytest            每个 smoke_test_*.py 走 pytest
make pytest-verbose    pytest 加 -v -s

make build PRESET=blitz       从 YAML 预设构建 main.py
make build-all                把每个预设都构建到 _build/ 下
make submit-prep PRESET=blitz 构建 main.py 并打印 kaggle 命令

make eval ARGS="preset:blitz random -n 20 -p 4 -o out.jsonl"
                              tools/eval.py 的快捷方式

make clean             清掉 _build/ 和 __pycache__/
```

Windows 没装 `make`?右边对应的命令是等价的,可以直接跑。

---

## 测试套件

| 文件 | 独立 check | pytest 函数 | 覆盖什么 |
|---|---:|---:|---|
| `smoke_test_core.py` | 41 | 10 | `GameState` 解析、几何原语 |
| `smoke_test_agents.py` | 28 |  9 | `Agent` ABC、SniperAgent + blitz 与老代码 parity |
| `smoke_test_build.py` | 32 |  3 | YAML → main.py、built blitz vs 老 main.py parity |
| `smoke_test_eval.py` | 40 | 10 | Runner、JSONL roundtrip、metrics 集成 |
| `smoke_test_metrics.py` | 20 |  7 | 在合成 env.steps 上单测 metrics |
| `smoke_test_viz.py` | 31 | 10 | SVG/HTML 渲染器、replay 加载、CLI |
| `smoke_test_tournament.py` | 45 | 12 | Round-robin、pairwise WR、Elo |
| **合计** | **237** | **61** | |

说明:
- "独立 check" 列统计的是 `[OK ]` 行数 —— 真正的断言,grep 失败用。
- pytest 把每个 `def test_*()` 当一个 test,大多数 test 内含多个
  `[OK ]` check。
- 两种跑法都必须保持绿色。standalone 形式不需要 pytest;pytest 形式
  需要 `pip install pytest`。

跑一个子集:

```bash
# 只跑一套
python tests/smoke_test_metrics.py

# 或用 pytest
pytest tests/smoke_test_metrics.py
pytest tests/smoke_test_metrics.py::test_planet_capture_and_loss
pytest -k parity     # 所有名字含 'parity' 的 test
```

---

## 架构不变量(三条承诺)

整套基础设施有三条由测试套件守护的承诺。**破任何一条都是后续无声
回归的最常见来源**:

1. **单向依赖**:`core/` 和 `agents/` 永远不 import `eval/`、
   `analysis/` 或 `tools/`。由
   `smoke_test_build.py::test_built_header_carries_metadata` 的
   "no leftover orbit_wars import" 检查守护 —— 如果你不小心加了这种
   import,构建出的 `main.py` 会残留无法解析的 `from orbit_wars...`
   行,测试立即挂掉。
2. **行为 parity**:任何对 `agents/heuristic.py` 的重构,都必须让
   `smoke_test_build.py::test_blitz_parity_against_handmaintained_main`
   保持绿色(10 回合 byte-identical 的 moves vs 老 `main.py`)。这是
   让你大胆重构同时不退步 Kaggle 排名的护栏。
3. **唯一真相源**:策略参数只活在 `configs/*.yaml`。`HeuristicConfig`
   的 dataclass 默认值只是"YAML 没指定时的兜底",**不是策略本体**。

---

## 常见问题排查

### `ModuleNotFoundError: No module named 'orbit_wars'`

你不在项目根目录运行。所有脚本都假设你在 README 所在的目录。
`cd` 过去,或者设 `PYTHONPATH=.`。

### `ModuleNotFoundError: No module named 'kaggle_environments'`

`pip install kaggle-environments`。`tools/eval.py`、`tools/tournament.py`
和真正跑游戏需要这个。构建 / metrics / viz / 单元测试不需要(测试
套件自带一个 stub)。

### `make pytest` 显示的 test 数比预期少

确认 `pytest.ini` 被识别(里头有
`python_files = test_*.py smoke_test_*.py`)。没有它的话 pytest
会跳过 `smoke_test_*` 命名的文件。

### 构建出的 `main.py` 本地能跑但 Kaggle 报 "Agent error"

检查构建文件头 —— 含 git commit hash 和构建时间戳。打开 `main.py`
搜 `from orbit_wars` —— 如果有任何匹配,说明 strip-imports regex
漏了。提个 issue,或重跑 `python tools/build_submission.py <preset>`
看烟雾测试的输出。

### 只在 pytest 下 `test_metrics_populated_through_runner` 失败

这曾经发生过,根因是 smoke 测试间的 `sys.modules` 污染(每个 smoke
在模块顶层装自己的 kaggle env stub,最后装的覆盖前面的)。已经通过
"每个 test 函数开头重新装一次 stub" 修了。如果你改了 smoke 测试后
又见到这个错,确保任何调用 `run_match()` / `run_matches()` 的 test
函数都在第一行调本地的 `_install_fake_kaggle()`。

### Windows:`make` 命令找不到

要么装 make(`scoop install make` / `choco install make`),要么用上面
[CLI 参考](#cli-参考)给的直接 `python ...` 命令 —— 每个 `make X` 都
只是一行 python 命令的包装。

---

## 延伸阅读

- [GAME_RULES.md](GAME_RULES.md) —— 完整的 Orbit Wars 规则:棋盘、
  行星、彗星、战斗、得分、observation 格式。
- [agents.md](agents.md) —— 更多 Kaggle CLI 例子(submit、下 replay、
  leaderboard 等)。
- `information/getting-started.ipynb` —— 比赛官方起步 notebook。
- `information/orbit-wars-complete-guide-eda-agents-submission.ipynb`
  —— EDA + 10 策略 round-robin 的 notebook,blitz 预设就是从这里
  来的。
- `information/orbit-wars-tamrazov-ykhnkf-hybrid.ipynb` —— 第三方
  混合 agent 参考。
