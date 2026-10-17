# 参数到算法的连接

工作台把录像观测、版本资料和人工确认的有效值分开。未知量保持未知；通用默认值标记为 `generic_default`，不能当作已核验规则。

## 属性和状态

| 参数 | 自动来源 | 计算入口 | 需要人工/AI确认 |
|---|---|---|---|
| 等级、基础生命、资源、攻击力、护甲、魔抗、移速、普攻距离 | 锁定补丁的 Data Dragon 与同补丁 CommunityDragon | `workbench/parameters.py`、`workbench/native_data.py` | 数据源冲突时选择有效值或覆盖 |
| 装备明确属性和碎片 | 结构化字段、装备 `<stats>` 区块、碎片说明 | `workbench/stat_arithmetic.py` | 被动、主动和条件效果不从说明文字猜测 |
| 当前生命、资源、护盾、剩余冷却、被动/符文层数 | 事件点表单 | `event_state` | 来自截图、客户端记录或 AI；不会沿用过时观测 |
| 复杂效果后的最终属性 | 人工或 AI 覆盖 | `stat_overrides` | 填写触发条件、证据和失效时间 |

自动值同时保存 `value`、`automatic_value`、`source`、来源和限制。自动属性只用于攻击频率、资源成本、范围和伤害参考，不代表决策正确。

## 小兵与攻击事件

小兵数据入口为 `workbench/minion_data.py`。它尝试读取版本化 CommunityDragon 候选路径，并保存原始响应；由于小兵数据结构没有稳定公共模式，无法映射的字段使用明确标记的通用 profile。通用 profile 只能用于草稿和量纲预估，正式推演应替换或确认生命、抗性、移速、攻击前摇、攻速、攻击距离、弹速、伤害、金币/经验奖励和目标状态。

`algorithms/short_horizon.py` 按事件推进：攻击起手检查阶段、资源、冷却、射程和目标；前摇结束后提交攻击；有弹速的攻击进入在途队列；命中时按当时生命、抗性、护盾和兵种伤害结算；死亡时结算金币、经验和待结算资源。升级、未知转火、仇恨变化或未建模效果在共同有效终点重规划。脚本不会用“最近单位”替代服务器仇恨。

`workbench/minion_data.py` 可尝试读取版本化 CommunityDragon 候选资料，也可保存 Riot Codex/League Wiki 的人工核验结果。Riot Codex 的小兵页还提供波次间隔、组成、目标优先级、重新索敌、获取范围、金币/经验和兵种统计；它是非官方页面，League Wiki 的页面适合人工核对统计定义，两者均不能绕过补丁号、来源、访问日期和有效规则核验。机器不能读取到的字段使用通用 profile，并在 `source_kind`、`profile_version` 和 `verified` 中显式标记。

## 特殊英雄接入

`templates/mechanism_profile.json` 和 `algorithms/mechanism_adapter.py` 是特殊机制的统一入口，不要求为每个英雄写 Python 分支。一个 profile 可以描述：

- 多段技能的 `sequences`、每段前摇/冷却/消耗/范围和是否重置普攻；
- `triggers` 的事件、条件、计数器、冷却和效果；
- 伤害、治疗、护盾、资源、计数器和最终属性覆盖；
- 尚未核验的命中几何、位移、特殊索敌和连锁效果。

表达式只允许数值、变量和基本算术，不能执行网页或 Python 代码。profile 必须带补丁、来源、核验状态和 unsupported 清单；未核验 profile 只能保存和解释，不能启用仿真。Aatrox 这类有被动强化普攻、多段 Q、W 对小兵倍率和 E 重置普攻的英雄，先由资料页填入一个结构化 profile，再由人工/AI确认命中几何与事件点状态；这不会把 Aatrox 写入主算法。

## 状态信念

`algorithms/belief_state.py` 实现离散粒子信念：

\[
 b_{t+1}(s') \propto P(o_{t+1}\mid s')\sum_s P(s'\mid s,a_t)b_t(s).
\]

`bayesian_update` 处理观测似然，`predict` 处理转移分支，`roll_forward` 保留每一步后验和熵。未知目标、冷却、命中状态和符文初态可用有限情景表示；未知不是失败，也不能当成零值。

## 补刀联合调度

`algorithms/joint_scheduler.py` 把每个小兵表示为可补窗口 `[t_low,t_high]`、提交时长、成功概率、金币、经验和成本，枚举同一攻击者不能重叠的联合方案，输出预期金币、经验、成本、占用时间、自由时间和冲突目标。它是候选调度器，不是小兵伤害模拟器；窗口应由事件推演或人工确认提供。

## 风险、信息价值和双层评分

`algorithms/risk_value.py` 对动作结果先计算声明权重下的效用，再计算：

\[
E[J(a)] = \sum_j p_j u_j,
\qquad Q(a)=E[J(a)]-\lambda(E[J(a)]-\operatorname{CVaR}_{\alpha}(J(a)))+\nu\operatorname{VOI}(a)-\kappa C_{execute}(a).
\]

`lower_cvar` 取最差 \(\alpha\) 的预期效用，`value_of_information` 计算观察后重新选择动作的预期增益。金币、经验、血量、资源、冷却和待结算资源须用当前窗口的权重和正尺度。

事后评分采用策略层优先：

\[
K=\sum_i w_iK_i,\qquad O=\sum_j v_jO_j,\qquad S=100c[\omega K+(1-\omega)O],\quad \omega\ge0.60.
\]

策略层包括窗口识别、资源计划、冷却纪律、成本转换、被动、符文和适应；执行层包括距离、相位、资源、移动和时机。缺项会列出并重新归一化，不假定满分；双方分别评分。`decision_analysis` 是候选动作局部值，`player_scores` 是事后双层评分，两者不混用。

## 公开方法的适用边界

- POMCP 用粒子和蒙特卡洛树搜索推进部分可观测状态；本仓库采用可审计的离散贝叶斯更新，未引入训练权重。
- Counterfactual Regret Minimization 适合不完全信息扩展式博弈；本仓库只有在声明效用、终点和候选策略后调用有限矩阵求解。
- OpenAI Five 的 Dota 2 系统和 AlphaStar 的 StarCraft II 联盟训练说明了自博弈、策略人口和价值函数的可行性，但依赖完整环境和大规模训练，不能替代录像证据与版本规则。

