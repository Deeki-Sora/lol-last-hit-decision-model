# 可选短时事件推演与博弈工具

## 1. 介入位置与安装

流程是：观测核验 → 选择介入时刻 → 填写共同初态和候选策略 → 事件推演 → 比较收益及成本 → 可选矩阵求解 → 人工或 AI 评价选择。工具可以用于最终评分之前，不要求先人为填一个收益矩阵。

工作台的“可选：从当前时刻进行短时事件与博弈推演”默认关闭。关闭时不加载数值求解器，不影响视频采样、表格、概率观察统计或评估包导出。

| 模式 | 计算 | 依赖 |
| --- | --- | --- |
| compare | 确定或随机情景的事件分支、双方资源/成本、共同有效窗口 | Python 标准库 |
| zero_sum | 对明确选择的相对收益代理做 maximin 求解 | NumPy、SciPy / HiGHS |
| general_sum | 保留双方不同收益，求有限矩阵的支持枚举均衡 | NumPy、Nashpy 及其依赖 |

工作台显示安装状态及 [SciPy 下载页](https://pypi.org/project/scipy/)、[Nashpy 下载页](https://pypi.org/project/nashpy/)，不会自动下载安装。需要时在运行工作台的同一个 Python 环境执行：

```sh
python -m pip install -r requirements-game.txt
```

不分发大体积安装包、特定英雄初态、旧对局参数或训练权重。SimPy 等可通过 requirements-algorithms.txt 安装供外部适配器使用；内置事件推演使用标准库事件执行，不需要 SimPy。

## 2. 工作台操作

1. 先在截图页完成双方单位、攻击目标、相位与死亡核验，保存。
2. 切到打算开始决策的帧，点击“以当前帧生成任务”。entry_time_s 为该帧视频时间；任务内所有 at_s、ready_in_s 和 horizon_s 均相对该时刻。默认预测三秒，可设置正数至三十秒。
3. 草稿只有可追踪单位身份与观察引用，没有推测出来的英雄数值。以人工或 AI 填完下面的参数，核验后设置 rules.verified=true。不要直接把血条像素或统一像素比例当成精确地面位置。
4. 输入双方候选策略，每方 1–8 种，可只输入一方的多种候选和另一方的一个条件回应。最初建议少量候选，先运行 compare。概率任务最多 16 个策略组合、每组 1–64 个同种子情景。
5. 勾选启用，选择 compare 并运行。结果显示实际共同有效窗口、重规划原因和每个组合双方的指标。详细事件、终端状态、概率统计和随机种子写入 game_analysis/ 的独立运行目录。
6. 如需排序或博弈求解，再声明效用权重、量纲、适用终点与边界价值。选择 zero_sum 或 general_sum 后运行。无需此步骤也能获得事件比较。
7. 遇到升级、未知仇恨/转火、超出概率样本适用条件或需要更新的属性时，使用新截图及有效技能组建立下一任务。不要直接将旧结果延伸。
8. 回到“保存并导出评估包”，推演任务、结果和机制观察记录会一起打包，其他人可以用同一 JSON 复算。

命令行等价操作：

```sh
python main.py game-draft runs/session/clip_01 --frame f000010 --output task.json
# 人工或 AI 补齐 task.json，核验规则，设置 enabled=true
python main.py game-run runs/session/clip_01 --task task.json
```

## 3. 必需状态与参数

| 位置 | 字段与含义 |
| --- | --- |
| rules | patch、sources、verified；有效规则来源、版本与核验声明 |
| rules.unit_scope_verified / unit_scope_note | 核验相关单位集合，说明为何没有遗漏能影响窗口的小兵等单位；任务 ID、阵营与兵种必须对应工作区名册 |
| rules.geometry | verified_game_ground_coordinates；须有地面位置依据，不能只是血条像素 |
| rules.pathing | verified_clear_straight_segments；只支持已核验无阻挡直线路径 |
| rules.xp_mode | solo_lane；不自动处理多人分摊经验、特殊任务或模式规则 |
| rules.xp_range / solo_xp_multiplier | 该版本经验范围与有效单人倍率；不内置历史值 |
| rules.aggro_triggers | 该版本已核验的仇恨触发条件列表；每项 action、target_kind、radius；命中触发范围时停止以更新小兵目标 |
| rules.level_up / retarget / hero_aggro / unmodelled_effects | 均为 replan，未知转移不能自动忽略 |
| rules.valid_until_s / boundary_reason | 可选的更早有效边界及原因，例如药水结束、未知效果可能生效 |
| rules.projectile_step_s | 指向弹道的数值积分步长，0.005–0.05 秒；不是游戏服务器时钟 |
| units[id] | side、kind、position、hp/max_hp、radius、move_speed、hp_regen_s、armor、magic_resist |
| units[id].resource_model | mana 或 none；mana、max_mana、mana_regen_s 必须与之匹配。能量、怒气等不在这个适配器内 |
| units[id].attack | 有效 attack_speed、period_s=1/attack_speed、windup_s、range、edge_to_edge 范围、missile_speed、ready_in_s、damage |
| units[id].phase / movement | 当前攻击/施法相位，以及 verified 和 destination；已有移动不能隐去 |
| 英雄额外字段 | level、累计 xp、next_level_xp、有效 gold_multiplier / xp_multiplier |
| 小兵额外字段 | gold_reward、xp_reward、locked_target；无目标时需 idle_verified_until_s 证明预测窗口内保持该状态 |
| units[id].skills | 使用的技能有效参数，见下文；未学习的 rank=0 不可释放 |
| units[id].effects_inactive_verified | 确认窗口内没有未建模的被动/符文/装备/控制状态；不能为了运行而随意设为 true |
| units[id].effects_adapter_verified / covered_effect_ids | 使用通用效果适配器时，声明已核验覆盖，并列出该单位全部适配效果 ID |

每个单位还应填写 effects_scope_note，说明未建模状态为何在窗口内无影响、或已由哪些规则覆盖。未知状态可以缩短有效窗口，或通过已核验的状态情景表示；不能把“未知”直接当成“不存在”。

普通 damage 为 `{"type":"physical","base":null,"target_current_hp_ratio":null,"target_max_hp_ratio":null}`，三个数值都必须补齐。支持 physical/magic/true；穿透、减伤、暴击、特殊 on-hit 等须已经进入有效参数或专用适配器，不能遗漏。护盾与真实血量损失分开结算。

只对特定兵种生效的伤害应使用 damage.by_target_kind，为对应 kind 提供完整伤害包，不能把小兵互殴加成误用到英雄。来源相关的穿透或最终减伤可提供已经核验的 mitigation_multiplier 覆盖通常的护甲/魔抗倍率，并说明来源；不提供时使用目标护甲/魔抗。护盾按声明顺序吸收，特殊优先级需另外适配。

## 4. 候选动作和初始相位

```json
{"id":"candidate","commands":[
  {"at_s":0,"kind":"wait"},
  {"at_s":0.3,"kind":"attack","target":"red_melee_w2_1","if":{"target":"red_melee_w2_1","hp_at_most":40,"alive":true}},
  {"at_s":0.6,"kind":"move","to":[100,200]}
]}
```

数字只展示字段格式，不是某个英雄的推荐时间或距离。wait 表示不发出新指令，已有移动仍继续；move 会取消尚未提交的普通攻击前摇。已启动且本适配器声明不可打断的施法不允许靠移动取消。攻击和技能分别检查可用性，非法指令记入结果；含非法候选的矩阵不能直接求解。

当前已在前摇/施法中的动作放入 in_progress_actions，写 actor、target、kind、release_in_s、started_ago_s；cast 还需 skill。phase 必须一致。已经发射但尚未命中的攻击放入 committed_attacks，写 source、target、already_launched=true、remaining_s 和 damage。已发射攻击不会因为攻击者后来死亡而自动取消；未知额外取消机制需要适配器。

小兵先按已核验的 locked_target 攻击；目标死亡、离开射程后需要重新观察转火和路径。脚本没有用“最近单位”冒充完整服务器索敌。仇恨条件由版本输入，避免把不同时期的小兵规则混用。

锁定目标死亡时立即要求更新，不等到下一次攻击。已锁定目标开始移动时也需要追击适配器，不能假设小兵继续原地攻击；当前适配器要求初始锁定目标保持静止，并在相关移动指令处重规划。

## 5. 技能与复杂机制的输入方式

可在工作台下载通用 JSON 模板，也可直接打开 [机制结构模板](../templates/mechanic_adapters.json)。包含 binary、joint_hits、非指向技能和效果适配器的完整字段框架；所有未知参数为 null，核验标志为 false，不含英雄数据。按实际机制填写后，分别放入 stochastic.models、units[id].skills 和 stochastic.effects。不要把模板本身当成已经验证的机制。

确定的技能描述可以使用 targeted 或 self，字段包括 rank、cast_s、cooldown_s、cost、range、range_mode、missile_speed、effect（damage/heal/shield）、commit=start、interruptible_by_move=false。只支持已核验属于这一类提交方式和取消规则的技能。多充能、位移、持续引导、墙体阻挡等需要另外适配，不能通过改几个标志强行运行。

复杂机制按优先级选择：

| 情况 | 合法输入 |
| --- | --- |
| 规则和初态都已知 | 确定计数器、冷却、逐事件效果；无需随机化 |
| 规则已知，初始层数或冷却未知 | initial_state_scenarios，对隐藏初态抽样，规则仍然确定 |
| 非指向技能是否命中难以确定 | 经条件核验的联合命中结果模型，保留耗蓝/CD及小兵附带命中 |
| 已满足触发资格，仍有真实随机性或明确的剩余观测不确定性 | 条件 binary 模型；不能用总体触发频率代替资格判断 |
| 效果改变尚未支持的属性或机制 | replan 或使依赖技能失效，等待新有效参数；不继续用旧参数 |

这是一种有条件的事件近似，不是全英雄服务器模拟器。联合命中模型替代的是这次命中结果的不确定性，不是宣称已经还原精确的技能弹道、瞄准或碰撞。

## 6. 记录命中、被动和符文概率

在工作台展开“非指向技能、被动、符文的观察概率与频率”，下载空白 UTF-8 BOM CSV；逐机会标注后导入。也可运行：

```sh
python main.py mechanics-template --output observations.csv
python main.py estimate-probabilities --csv observations.csv --output estimated_models.json
```

| 列 | 填写方法 |
| --- | --- |
| opportunity_id | 一次释放/独立触发机会的永久 ID。重复截图沿用同一 ID，不重复计数 |
| mechanism_id | 同一机制、同一观察条件的 ID；换英雄、等级、距离组、移动条件或观察窗口应换 ID |
| kind / event_type | binary 或 joint_hits；event_type 分别写 skillshot_hit、passive_activation、rune_activation 等 |
| actor / target / source_time_s | 对应单位与源视频时间；不得用结果倒推资格 |
| eligible | true/false/空白。符文需检查有效目标、计数阈值、冷却等；空白为未知 |
| success | binary 的 true/false/空白；未知不记为未命中或触发失败 |
| outcome_id / hit_unit_ids | joint_hits 的整次结果类别；命中单位用分号分隔；未命中仍填写类别，hit_unit_ids 留空 |
| window_start_s / window_end_s | 完整观察窗口，不是第一次到最后一次触发之间的时间 |
| context / source | 距离、移动、等级、版本、资格等适用条件和证据引用 |

导入后分别报告有效机会、结果缺失、成功率、单位时间确认触发数和覆盖情况。资格未知但已经确认的触发计入频率，不计入条件成功率分母。不同条件混用、同一机会矛盾或损坏字符会报错。

点击“将统计模型写入任务”。context_verified 默认仍为 false；人工或 AI 必须确认它适用于当前候选和敌方回应，而不只是适用于原录像。联合结果另需填写 distance_interval=[下限,上限]、target_motion（moving/stationary/any）。离开核验距离或移动条件就停止，不能沿用原命中率。

## 7. 随机情景与联合结果

stochastic 中提供 samples、seed、models、effects。模型的三种 sampling：

- empirical：条件样本频率，保留来源、数量与缺失说明。
- posterior：binary 用明确的 prior_alpha/prior_beta；joint_hits 用明确的 prior_per_outcome。先抽参数再抽事件，表达小样本参数不确定性。
- fixed：已知机制概率或明确声明的情景概率，不从玩家段位推定。

非指向技能使用 delivery=skillshot_probability、outcome_model、impact_delay_s、max_hits、collateral_scope_verified=true。outcome_model 的 kind=joint_hits，outcomes 列出整次攻击的命中集合，例如 `{"id":"hero_and_minion","hits":["red_hero","red_melee_w2_1"],"count":3}`。必须包含所有可能受影响单位，并核验穿透上限、碰撞及互斥结果；不能把穿过小兵后命中英雄拆成互不相关的投币。

miss 集合为空，但仍执行施法及已提交冷却。后续被动和符文在实际命中结果上检查资格。固定同一 seed 和输入会得到相同输出；各策略组合在对应条件机会使用相同随机流。结果保留事件、抽样参数、条件试验数、场景均值和分位数。分位数是所声明情景下的范围，不是自动校准的置信区间或真实胜率。

## 8. 被动/符文效果适配器

每个 effects 条目填写：id、actor、verified=true、source、trigger、ready_in_s、cooldown_s、counter、probability_model（确定规则填 null）及 effect。

trigger 支持 attack_hit、spell_hit、before_damage、minion_kill；可用 labels 和 target_kinds 筛选。counter 必须有 threshold、window_s、unique_casts、initial_hits。initial_hits 写 age_s 和 instance；initial_state_scenarios 可给初始冷却及计数的离散概率分布，概率和必须为一。

多个被动/符文初态相关时，使用 stochastic.initial_joint_states：每个情景写 probability 和 effects，后者按效果 ID 给 ready_in_s/initial_hits。所有效果共享同一次初态抽样，可表达互斥状态，不会把“各有 50%”独立抽成不可能同时发生的组合。其他模型若需要相关性也必须显式建模；程序不会从边际频率自动恢复联合分布。

支持的效果为 damage、shield、heal、mana、bank_resource、replan。shield 在 before_damage 时可以先生成再抵扣该次伤害；效果有独立冷却。unique_casts 防止一次多目标技能被重复算作多次独立技能。派生效果不会自动递归触发其他效果，复杂连锁须另行核验适配。

bank_resource 保存层数/永久资源，并通过 invalidates_labels 声明哪些攻击或技能参数随后过期；再次使用这些动作时必须更新有效参数。不能在获得改变伤害或攻速的资源后继续用旧伤害/CD。需要即时更改尚未支持的属性时使用 replan，不能用触发概率绕过真实属性更新。

## 9. 共同终点、终端价值与求解

各分支/随机情景先找有效边界，再全部重算至最早共同终点。升级后不自动学习技能；结果要求重新取得等级属性和技能组。边界处的快照不是完整升级后状态，不能直接当作下一任务的已核验初态。

默认 compare 不需要效用权重，也不判断谁胜谁负。输出 gold_gain、xp_gain、hp_damage、hp_deficit_change、mana_spent、cooldown_remaining_s、shield_remaining、xp_to_next_level、pending_enemy_gold/xp 和适配资源等。待结算小兵不作为已得收入或永久损失。

求解时 utility 需声明 reference、terminal_scope_note、valid_for_entry_time_s、valid_for_horizon_s，以及 blue/red 各自的 weights 与 scales。正权重表示偏好增加，负权重表示成本；scales 为正的量纲基准。有效终点改变后旧配置失效。禁止把 pending_* 直接计为已获收益。

若结果标记 terminal_state_requires_refresh，边界后的有效状态尚未完整建立，矩阵求解拒绝继续；compare 仍保留截断前事件证据。先取得新观测或适配新规则，再建立新任务，避免用升级前血量上限/技能参数给升级后局面估值。

可选 terminal_values 用策略 ID 对作为 JSON 字符串键，例如 `["a","b"]`，每项包含 blue、red 和 reason；这是外部边界估值，原始结算不随之修改。没有估值时结果标记 unpriced_local_state_only，只讨论局部目标。不能把短时舍弃金币等同于博弈失败。

zero_sum 还需 relative_resource_proxy=true，求解双方标量收益差；general_sum 使用双方各自收益，可能有多个或退化均衡。策略概率只是这个有限矩阵的解，不是对手真实行动频率。工具不自动给玩家打 0–100 分，普通评分仍由框架与固定配置完成。

## 10. 机制核验与复算

有效属性、前摇与弹道要按版本核验；Riot 的 [13.22 更新](https://www.leagueoflegends.com/en-us/news/game-updates/patch-13-22-notes/)直接涉及这些属性。[25.S1.1 更新](https://www.leagueoflegends.com/en-au/news/game-updates/patch-25-s1-1-notes/)涉及小兵生命、伤害与经验范围；[26.1 更新](https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/)涉及经验结算与任务修正。因此脚本没有写死某一历史版本的小兵或英雄数值。

```sh
python -m unittest discover -s tests -p "test_short_horizon.py"
python -m unittest discover -s tests -p "test_probabilistic_mechanics.py"
```

测试是无特定英雄数据的合成机制不变量检查，包括攻击频率、取消前摇、射程、护盾、耗蓝、无最后一击经验、共同升级截断、未命中仍耗蓝、条件计数、初始状态不确定性、联合附带命中和固定种子复现。通过测试不意味着已验证全部英雄或证明所有概率模型可迁移。
