# Orbit Wars Strategy Iteration Prompts

This file stores reusable prompts for strategy work in this repository.

## Champion Strategy Optimization Workflow

```text
你现在作为 Orbit Wars 冠军策略优化助手工作。

项目背景：
- 当前项目是 Kaggle Orbit Wars 策略研究工程。
- 当前冠军/最优策略是 preset:ow_proto。
- ow_proto 对应实现主要在 orbit_wars/agents/ow_proto.py。
- ow_proto 对应配置在 configs/ow_proto.yaml。
- 策略参数在 configs/*.yaml。
- 本地评估通过 tools/eval.py 和 tools/tournament.py。
- 可视化通过 tools/viz.py。
- 不要直接手改 main.py，除非我明确要求构建提交版本。
- 不要覆盖我已有的未提交改动。

目标：
- 本轮只围绕当前冠军 preset:ow_proto 做优化。
- 优先通过新增 configs/ow_proto_xxx.yaml 或调整参数实现。
- 只有当参数无法表达优化想法时，才小范围修改 orbit_wars/agents/ow_proto.py。
- 每次只优化一个明确方向，避免多变量混杂。

工作流程：

1. 冠军策略理解
- 先阅读 configs/ow_proto.yaml 和 orbit_wars/agents/ow_proto.py。
- 总结 ow_proto 当前核心机制：
  - 目标评分逻辑
  - 轨道/移动目标预测
  - 彗星处理
  - 太阳碰撞规避
  - 在途舰队/目标过量投入控制
  - 防守增援
  - 多源协同攻击
- 明确列出哪些机制已经验证有效，不应轻易破坏。

2. 优化假设
- 提出 1-3 个围绕 ow_proto 的优化假设。
- 每个假设必须包含：
  - 改动点
  - 为什么可能提升
  - 可能造成的副作用
  - 需要观察的指标
- 每轮只选择一个最值得尝试的假设执行。

3. 实现约束
- 优先新建配置文件，例如 configs/ow_proto_prod_push.yaml。
- 不要直接覆盖 configs/ow_proto.yaml，除非我明确要求。
- 如果必须改 agent 代码：
  - 改动范围必须小
  - 保留 ow_proto 已有关键能力
  - 不做无关重构
- 新策略命名必须清晰。
- 修改后同步更新 CHANGELOG.md。

4. 反退化检查
- 实现后必须检查新策略是否保留：
  - 轨道/移动目标预测
  - 彗星位置预测
  - 太阳规避
  - 在途舰队记录
  - 防守增援
  - 多源协同攻击
- 如果任何能力被削弱或移除，必须明确说明原因和风险。
- 除非实验目标就是简化 baseline，否则不允许把功能明显倒退的策略作为候选冠军。

5. 模型对比
- 因为这是冠军优化，必须直接和 preset:ow_proto 对比。
- 但仍要保留基础 sanity check。

评估流程：
A. Sanity check
- new vs preset:blitz，5-10 局
- new vs preset:sentinel，5-10 局
- 如果明显输给 blitz 或 sentinel，停止该方向。

B. 冠军挑战
- new vs preset:ow_proto，10-20 局
- 输出胜率、mean reward diff、关键 metrics、样本局数。

C. 泛化确认
- 如果 new 接近或超过 ow_proto，跑小型 tournament：
  new、preset:ow_proto、preset:blitz、preset:sentinel、preset:peaking、random
- 每组 6-10 局即可作为初步确认。

6. 参数调整规则
- 每个优化方向最多允许 3 轮参数调整。
- 每轮只允许改 1-3 个关键参数。
- 每轮调整前必须说明：
  - 上一轮观察到了什么
  - 为什么改这些参数
  - 预期改善什么
- 如果连续 2 轮没有提升胜率或 mean reward diff，则停止该方向。

7. 晋级/停止规则
- 如果 new vs preset:ow_proto 胜率 >= 55%：
  - 标记为 candidate champion
  - 扩大样本或跑 tournament
- 如果 new vs preset:ow_proto 胜率在 48%-55%：
  - 标记为 candidate
  - 允许最多 2 轮针对性微调
- 如果 new vs preset:ow_proto 胜率 < 48%，且 mean reward diff 为负：
  - 标记为 rejected 或 parked
  - 停止该优化方向
- 如果 tournament 中整体 Elo/胜率超过 ow_proto：
  - 标记为 champion

8. 可视化分析
- 如果输赢异常、reward diff 和胜率矛盾、或需要解释失败原因，生成 replay 并可视化。
- 可视化时必须传入双方名字：
  python tools/viz.py <replay.json> -o <out.html> --names new_strategy,ow_proto
- 分析时说明蓝色/红色分别是什么策略。

9. 记忆保存与实验追踪
- 在开始新一轮优化前，必须先阅读 EXPERIMENTS.md 和 CHANGELOG.md。
- 如果当前想法和历史 rejected/parked 实验相似，必须说明为什么这次仍值得尝试，否则换下一个方向。
- 每轮实验结束后，必须把关键信息写入 EXPERIMENTS.md。
- 如果 EXPERIMENTS.md 不存在，先创建它。
- 不允许只在最终回答里记录实验结论；重要结论必须写入 EXPERIMENTS.md。
- 每条实验记录必须包含：
  - 日期
  - 策略名称
  - 策略类型：champion optimization
  - 核心假设
  - 继承了哪些冠军能力
  - 修改了哪些文件
  - 参数变化
  - 评估命令
  - 对比对象
  - 胜率、mean reward diff、关键 metrics
  - 结论状态：rejected / parked / candidate / candidate champion / champion
  - 停止原因或下一步计划
  - 相关输出文件路径，例如 cmp.jsonl、tourneys/...、replay.html
- CHANGELOG.md 只记录代码和功能变更；EXPERIMENTS.md 记录策略实验过程和结论。

10. 输出要求
最终回答必须包含：
- 本轮优化假设
- 修改了哪些文件
- 是否保留冠军关键机制
- 评估命令
- 评估结果
- 策略状态：rejected / parked / candidate / candidate champion / champion
- 是否继续调参
- 下一步建议

本轮目标：
【在这里填写，例如：
“基于 ow_proto 增强前期抢高 production 中立星球”
或
“优化 ow_proto 的防守增援参数”
或
“降低 ow_proto 对彗星的忽略程度，测试是否提高中后期收益”】
```

## New Strategy Exploration Workflow

```text
你现在作为 Orbit Wars 新策略探索助手工作。

项目背景：
- 当前项目是 Kaggle Orbit Wars 策略研究工程。
- 当前冠军/最优策略是 preset:ow_proto。
- 主要策略代码在 orbit_wars/agents/。
- 策略参数在 configs/*.yaml。
- 本地评估通过 tools/eval.py 和 tools/tournament.py。
- 可视化通过 tools/viz.py。
- 不要直接手改 main.py，除非我明确要求构建提交版本。
- 不要覆盖我已有的未提交改动。

目标：
- 本轮允许探索新策略方向。
- 但新策略不能无理由丢弃当前冠军已经验证有效的能力。
- 新策略应该尽量复用 ow_proto 或其他强策略中的成熟机制。
- 只有当新方向确实需要完全不同架构时，才新建独立 Agent。

工作流程：

1. 问题观察
- 先阅读当前相关 agent、config、最近 eval/tournament 结果。
- 如果没有近期结果，先说明缺口，并用小样本建立基线。
- 总结当前冠军 ow_proto 的优势和可能短板。
- 明确新策略想解决什么问题。

2. 冠军经验继承
- 在设计新策略前，必须阅读 configs/ow_proto.yaml 和 orbit_wars/agents/ow_proto.py。
- 总结当前冠军中已经验证有效的机制。
- 新策略应优先继承或复用这些机制：
  - 轨道/移动目标预测
  - 彗星位置预测
  - 太阳碰撞规避
  - 在途舰队/目标过量投入控制
  - 防守增援
  - 多源协同攻击
- 如果新策略要替换或绕开这些机制，必须说明：
  - 为什么要替换
  - 风险是什么
  - 如何验证不会退化

3. 策略假设
- 提出 1-3 个新策略假设。
- 每个假设必须包含：
  - 核心想法
  - 与 ow_proto 的区别
  - 继承了哪些冠军能力
  - 可能优于 ow_proto 的场景
  - 可能弱于 ow_proto 的场景
  - 验证指标
- 每轮只选择一个假设实现。

4. 实现方式选择
按优先级选择实现方式：
A. 配置变体
- 如果新策略只是参数/权重变化，新增 configs/*.yaml。

B. Champion fork
- 如果需要小幅改 ow_proto 逻辑，基于 ow_proto 新增一个变体 Agent 或小扩展。
- 不要破坏原始 ow_proto。

C. 独立 Agent
- 只有当策略结构完全不同，且复用现有 agent 不合理时，才新建独立 Agent。
- 新 Agent 仍应复用 core geometry/state 工具。
- 不要复制粘贴大量重复逻辑，除非构建系统需要。

5. 反退化检查
- 实现后必须检查新策略是否支持：
  - 轨道/移动目标预测
  - 太阳规避
  - 多源协同或至少避免明显过量投入
  - 基础防守或威胁响应
- 如果不支持，必须在报告中明确标注。
- 新策略如果缺失多个冠军能力，只能作为 exploratory baseline，不得直接作为候选冠军。

6. 模型对比
- 新策略不要一开始只和 ow_proto 对比。
- 使用分层评估：

A. 快速筛选
- new vs preset:blitz，5-10 局
- new vs preset:sentinel，5-10 局
- 必要时 new vs random
- 如果连 blitz 都打不过，停止或最多允许 1 轮修正。

B. 冠军挑战
- 只有快速筛选通过后，才挑战 preset:ow_proto。
- new vs preset:ow_proto，10-20 局。

C. 泛化确认
- 如果 new 接近或超过 ow_proto，跑小型 tournament：
  new、preset:ow_proto、preset:blitz、preset:sentinel、preset:peaking、random
- 每组 3-5 局即可作为初步确认。

7. 参数调整规则
- 每个新策略最多允许 3 轮参数调整。
- 每轮只允许改 1-3 个关键参数。
- 每轮调整前必须说明：
  - 观察到了什么问题
  - 为什么调整这些参数
  - 预期改善什么
- 如果连续 2 轮没有提升胜率或 mean reward diff，则停止该策略。

8. 晋级/停止规则
- 如果 new vs preset:blitz 胜率 < 50%，且 mean reward diff 明显为负：
  - 标记为 rejected
  - 停止该策略
- 如果 new vs preset:blitz 胜率在 50%-60%：
  - 允许最多 1-2 轮参数调整
- 如果 new vs preset:blitz 胜率 >= 60%，且不明显输给 sentinel：
  - 晋级挑战 preset:ow_proto
- 如果 new vs preset:ow_proto 胜率 < 48%，且 mean reward diff 为负：
  - 标记为 rejected 或 parked
  - 停止继续调参
- 如果 new vs preset:ow_proto 胜率在 48%-55%：
  - 标记为 candidate
  - 允许最多 2 轮针对性微调
- 如果 new vs preset:ow_proto 胜率 >= 55%：
  - 标记为 candidate champion
  - 扩大样本或跑 tournament
- 如果 tournament 中整体 Elo/胜率超过 ow_proto：
  - 标记为 champion

9. 策略状态分类
每个策略结束时必须标记：
- rejected：明显不行，停止
- parked：有潜力但当前不够强，暂存
- exploratory baseline：有研究价值但功能弱于冠军，不作为候选
- candidate：接近或小胜冠军，值得继续验证
- candidate champion：小样本明显优于冠军，需要扩大验证
- champion：大样本或 tournament 后成为当前最优

10. 可视化分析
- 当某场对局结果异常、策略输得很奇怪、或需要解释失败原因时，生成 replay 并使用可视化。
- 可视化时必须传入双方名字：
  python tools/viz.py <replay.json> -o <out.html> --names new_strategy,ow_proto
- 分析时说明蓝色/红色分别是什么策略。

11. 记忆保存与实验追踪
- 在开始新一轮探索前，必须先阅读 EXPERIMENTS.md 和 CHANGELOG.md。
- 如果当前想法和历史 rejected/parked 实验相似，必须说明为什么这次仍值得尝试，否则换下一个策略方向。
- 每轮实验结束后，必须把关键信息写入 EXPERIMENTS.md。
- 如果 EXPERIMENTS.md 不存在，先创建它。
- 不允许只在最终回答里记录实验结论；重要结论必须写入 EXPERIMENTS.md。
- 每条实验记录必须包含：
  - 日期
  - 策略名称
  - 策略类型：new exploration
  - 核心假设
  - 与 ow_proto 的区别
  - 继承了哪些冠军能力
  - 缺失或替换了哪些冠军能力
  - 修改了哪些文件
  - 参数变化
  - 评估命令
  - 对比对象
  - 胜率、mean reward diff、关键 metrics
  - 结论状态：rejected / parked / exploratory baseline / candidate / candidate champion / champion
  - 停止原因或下一步计划
  - 相关输出文件路径，例如 cmp.jsonl、tourneys/...、replay.html
- CHANGELOG.md 只记录代码和功能变更；EXPERIMENTS.md 记录策略实验过程和结论。

12. 记录与总结
- 每轮实验结束必须更新 CHANGELOG.md。
- 如果有实验结果文件，说明保存路径。
- 最终回答必须包含：
  - 本轮新策略假设
  - 继承了哪些冠军能力
  - 缺失或替换了哪些冠军能力
  - 修改了哪些文件
  - 评估命令
  - 评估结果
  - 策略状态
  - 是否继续该策略
  - 下一个策略建议

13. 工程要求
- 每次修改后运行相关测试。
- 涉及通用代码时运行 python3 -m pytest。
- 不要覆盖用户已有未提交改动。
- 不要删除已有实验结果，除非我明确要求。
- 保持回答简洁，但要给出足够决策依据。

本轮目标：
【在这里填写，例如：
“探索一种更偏防守反击的新 agent”
或
“探索 early-game 高 production 抢占策略，但继承 ow_proto 的移动目标预测”
或
“请自动提出 3 个区别于 ow_proto 的新策略方向，并选择一个最值得实现”】
```
