# 采样、标注与评估流程

## 1. 输入与采样

将录像放入 input_videos/，或从任意文件夹选择。运行 `python main.py`，按提示选择一个或多个视频、每段开始/结束时间、0.1–0.5 秒采样间隔及可选距离标尺。时间指源视频时间，不是游戏时钟。多视频逐个生成工作区并打开标注页面；关闭前一工作区的服务（终端 Ctrl+C）后进入下一工作区。

无交互调用：

```sh
python main.py sample --video input_videos/match.mp4 --start 1:00 --end 1:30 --step 0.3 --scale 189=350 --output runs/session/clip_01 --review
python main.py review runs/session/clip_01
```

输出目录必须不存在，避免覆盖采样。FFmpeg 选择实际解码帧，保存 showinfo 时间戳，不生成插值帧。低帧率或可变帧率视频的实际采样间隔可能略大于设定值；以 project.json 的 source_time_s 为准。切片不改变源录像。

## 2. 单位、坐标和状态

每帧先选择单位，再点击完整血条中心；也可拖框选择完整血条后自动取中心。默认只建立双方英雄，实际小兵需在页面或 AI 名册中加入。若片段确实从第一波普通兵线开始，可在交互启动时明确启用首波模板，命令行加 `--first-wave-template`；模板为双方各三近战和三远程小兵，不是检测结果。后续兵波、炮车等新增独立 ID，不复用阵亡单位编号。新增时选择阵营、兵种和波次，ID 留空自动生成，例如 red_siege_w3_1、red_melee_w4_1；序号不限制为 1–6，波次不确定可填 0。页面新增单位从当前帧起进入名册；AI 可指定 first_seen_s。

可选 `sample --proposals` 提供颜色填充区域候选，需要 `requirements-vision.txt`。候选不推断单位身份、炮车或其他兵种，也不自动确认为完整血条；残血填充、特效和界面可能造成误检。炮车选择 siege，未知兵种可先选 minion；人工指定或 AI 识别后写入名册，不根据血条宽度冒充可靠分类。无确认坐标时距离保持未知。用户或 AI 可直接批量提供 annotations.json，页面用于复核。

同一帧的距离只记录：蓝红英雄之间，以及各英雄到对方小兵，项数为 `1+n_blue+n_red`。第一波双方各六只存活小兵时为 `1+6+6=13` 项，但这不是上限；炮车与前波存活小兵均可加入。

默认用名册中所有未确认阵亡的小兵。单方超过六只且未明确距离对象时，导出要求先显式选择，程序不会自行编号、挑选或截断。页面可逐项勾选，或点击“选取名册内当前全部未确认阵亡的小兵”；数量不限。选择写入 distance_minions，并沿用到后续帧直到重新选择；新增单位需再明确加入选择，阵亡单位自动排除。JSON 的空列表 `[]` 表示只测英雄之间。未纳入距离范围的单位仍可记录动作，距离留空，并通过 in_distance_scope 标记。没有己方小兵距离或小兵两两距离。

在确认阵亡帧设置 `alive=false`，或动作填 `death`，该单位从这帧起不再生成记录与距离。看不清不等于死亡，设置未知；撤销误判需回到对应帧更正。名册中的波次不等于自动识别出的波次。

需要计算跨帧移动时，在每帧标出同一地图纹理点为原点，程序扣除其像素坐标。没有原点仍可算同帧距离，但不能报告经镜头平移修正的位移。换缩放或明显投影变化时，在对应帧标注 scale_id，程序不会跨不同 scale_id 计算位移。单个平移原点不校正旋转、缩放或透视。

## 3. 事件与表格

动作、目标、相位、生命值、动作开始/结束时间和备注人工或 AI 填写。开始/结束时间为视频秒数，不能把同一动作跨帧持续当成多次攻击。不同单位拥有独立时间序列。

保存并导出，或运行：

```sh
python main.py export runs/session/clip_01
```

| 文件 | 含义 |
| --- | --- |
| project.json | 源视频名称/哈希、采样时间、相对截图路径、名册、标尺、英雄资料、策略文字 |
| annotations.json | 每帧原点、单位中心、动作与人工复核标识 |
| frames/ | 实际采样截图 |
| tables/events.csv | 帧×未确认阵亡单位，明确 side/unit_id/enemy_hero_id/target 及对应距离 |
| tables/distances.csv | 每帧有方向标识的单位对、双方阵营/兵种、像素距离、可选游戏距离、复核标识 |
| tables/actions.csv | 按单位及明确动作开始时间去重后的动作；相邻动作开始时间之差 |
| tables/deaths.csv | 最后确认存活时间与确认阵亡时间上界；未知死亡时刻不补成精确值 |
| tables/coverage.json | 已测/未测、已标注/未标注、复核覆盖率 |
| assessment_bundle.zip | 框架、预输入、截图、表格、原始标注及评估请求的独立资料包 |

所有 CSV 均 UTF-8 BOM。`hero_minion_distance_band` 这种无法区分双方/目标的字段不作为数值输入；距离由明确两个单位 ID 的中心重算。未知留空，绝不填 0。建议保留原文件再用电子表格编辑；导回时自动重新计算距离，忽略手改的派生距离列：

```sh
python main.py import-table runs/session/clip_01 edited_events.csv
```

默认 UTF-8 BOM，可显式指定 `--encoding gb18030`。字面 `??` 或替换字符提示原文字已损坏，程序拒绝导入；更换编码无法恢复已丢失字符。重复 frame_id/unit_id 行拒绝导入。

## 4. AI/工程接口

```json
{
  "schema_version": 1,
  "frames": {
    "f000001": {
      "origin": [800, 450],
      "units": {
        "blue_hero": {"center": [600, 390], "coordinate_method": "ai_health_bar_center", "reviewed": false, "alive": true, "action": "attack", "target": "red_melee_w1_1", "action_start_s": 60.1},
        "red_melee_w1_1": {"center": [650, 420], "reviewed": false, "alive": true}
      }
    }
  }
}
```

写入工作区 annotations.json 或使用页面导入；frame_id、单位 ID 必须已存在，坐标为原图像素。AI 标注保持 reviewed=false，人工确认后设 true。截图和 CSV 提供给任何支持文件的 AI 工具，主程序不需要其账号、插件或 API 密钥。

## 5. 参数查询与评估

版本目录见 [Riot Data Dragon 文档](https://developer.riotgames.com/docs/lol#data-dragon)。精确快照版本与游戏补丁名未必一一对应，必须核验：

```sh
python main.py fetch-data --version 16.6.1 --blue Yasuo --red Veigar --output hero_data.json
```

命令仅下载官方基础数据，不自动计算装备/符文/技能等级后的有效参数；填好后将 JSON 内容粘贴页面的英雄资料区。每方应有 champion、patch、runes、items、effective_state（例如 level、attack_speed、attack_range、move_speed、spell_ranks、cooldowns、mana_costs、passive_state），并人工确认 verified_effective_state=true。评估资料包会报告是否声明核验，但不会以勾选代替真实证据。

某些 Python 安装未附带完整根证书，可运行 `python -m pip install -r requirements-data.txt` 使用公共 CA 包；程序始终验证 HTTPS 证书。需要专用证书的环境可通过 SSL_CERT_FILE 指定可信 CA。离线使用时直接填写已核验的英雄 JSON。

可选纯文字策略参考应写来源、适用等级、触发条件、成本与失效条件。将资料包交给 AI 或人工，按 evaluation_request.md 分别评价双方。未来推演、反事实以及评分需要补全机制、候选动作、敌方回应与固定评分配置；工作台不从画面自动推导可靠总分。当前为录像/暂停画面工作流，实时工程可接入同一数据结构，未提供游戏内自动控制或实时采集器。

## 6. 评估后的可选博弈求解

```sh
python -m pip install -r requirements-algorithms.txt
python main.py solve --matrix assessed_matrix.json --output matrix_solution.json
```

输入格式：

```json
{"game_type":"two_player_zero_sum","assessment_reference":"assessment/result.md#decision-1","row_actions":["a","b"],"column_actions":["x","y"],"payoff_matrix":[[1,-1],[-1,1]],"payoff_unit":"declared normalized resource differential"}
```

行是我方动作，列是对方回应，收益为行方的明确标量。程序返回双方混合策略、有限矩阵价值和对偶误差。一般对线可能不是零和；无法合理映射成零和时不要使用此入口，使用 Nashpy 等自行实现一般和求解。外部收益矩阵依赖评估中的假设；求解结果不代表完整游戏均衡或玩家段位。

通用离散事件调度见 algorithms/event_queue.py，调用方提供机制转移函数。它不含特定英雄初态或完整伤害/寻路规则。评估者可以用它运行已声明的有限兵链及反事实，再把结果转成收益矩阵；主程序没有预设任何对局分支。
