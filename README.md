# LOL 短时补兵决策评估框架

## 1. 框架简介

以双方各自可见的信息为起点，在一波小兵或约 20–30 秒的短时窗口内，评价攻击目标、补兵时机、后续补刀可行性，以及资源取得所需的生命、蓝量、冷却和时间成本。双方分别评估，区分策略选择与执行质量；用明确参数、事件链和不确定区间支持结论。

**[中文框架](LOL_短时补兵决策评估框架_v0.91.md)** · **[English framework](LOL_Short_Window_Last_Hit_Decision_Evaluation_Framework_v0.91.md)**

配套工作台将录像变成可核验的截图、单位标注、距离和动作表，再导出独立资料包供人工或 AI 工具评估。它支持任意对线片段，不依赖其他项目、固定英雄、外部工程文档或本机路径。框架公式覆盖短时决策、反事实和事件推演；工具的自动化范围见下表。

| 环节 | 工作台负责 | 人工 / AI 负责 |
| --- | --- | --- |
| 视频采样 | 时间段截取式采样、实际帧时间记录、保存截图 | 选择可观察片段 |
| 单位定位 | 标注画布、可选颜色区域候选 | 确认阵营、单位身份、完整血条中心和死亡 |
| 距离与动作表 | 按单位 ID 重算距离、位移、已标注动作间隔，导出表格 | 填写动作、目标、相位、时间与状态，复核坐标 |
| 英雄与策略预输入 | 中英文名称选择、版本目录、符文页、按时间记录的等级/加点/装备、参数与策略存储 | 确认实际配置与背包完整性；核验有效机制；可选策略文字 |
| 评分与未来分支 | 打包框架、证据及评估请求 | 使用固定配置计算双边评分、未来兵链及反事实 |
| 概率观察 | 独立机会去重、命中/触发成功率、频率、缺失覆盖 | 核验技能、被动、符文的资格与适用条件 |
| 可选短时推演 | 事件分支、共同有效终点、条件情景抽样、双方资源/成本 | 提供有效游戏规则、初态、候选及复杂机制适配 |
| 可选有限博弈 | SciPy 零和代理或 Nashpy 双方独立收益求解 | 声明收益权重、边界价值和适用窗口 |

## 2. 必需工具与可选项

必需：Python 3.11+、FFmpeg（含 ffprobe）、本地浏览器。基础工作台仅使用 Python 标准库。安装 FFmpeg 后重新打开终端：

```sh
# Windows
winget install --id Gyan.FFmpeg -e
# macOS
brew install ffmpeg
# Ubuntu / Debian
sudo apt-get install ffmpeg
```

检查并启动：

```sh
python --version
ffmpeg -version
ffprobe -version
python main.py
```

可选颜色区域候选（仍须确认完整血条中心）：

```sh
python -m pip install -r requirements-vision.txt
python main.py sample --video input_videos/match.mp4 --start 60 --end 90 --step 0.3 --output runs/demo --proposals --review
```

可选矩阵求解包（不开启求解无需安装）：

```sh
python -m pip install -r requirements-game.txt
```

工作台提供 [SciPy 下载链接](https://pypi.org/project/scipy/)、[Nashpy 下载链接](https://pypi.org/project/nashpy/)和安装状态，不自动下载安装。内置事件推演与概率统计仅需标准库；SciPy / HiGHS 用于有限零和代理，Nashpy 用于双方独立收益矩阵。SimPy 等外部扩展可另用 requirements-algorithms.txt 安装。各工具用途见 [依赖说明](docs/algorithm_dependencies.md)。FFmpeg 只负责视频处理。

官方数据查询需要 HTTPS 连接。Python 环境缺少根证书时，可安装可选证书包：`python -m pip install -r requirements-data.txt`。查询失败也可自行核验资料后手动填写，不影响采样和表格功能。

工作台提供中文 / English 界面切换。内置英雄、符文和装备选择器使用标准库接口获取锁定版本的 Riot Data Dragon 数据，以及同补丁 CommunityDragon 属性碎片目录；无需安装独立模拟器。下载后缓存到工作区并随评估包导出，可离线复用。[ARAMonly](https://www.aramonly.com/lol-runes-builder/)是可选的名称/ID 选择入口，通过分享链接导入符文、装备，不负责英雄选择或游戏数值。外部站点不可用时继续使用内置选择器。详情见 [配置选择与外部接口](docs/loadout_selection.md)。

## 3. 操作指南

1. 将一个或多个录像放入空白的 `input_videos/` 文件夹，或启动后输入自己的文件夹路径；输入 `choose` 可打开文件夹选择器。
2. 运行 `python main.py`，选择视频、源视频开始/结束时间，以及 **0.1–0.5 秒**的采样间隔。可输入 `189=350`，表示 189 像素约为 350 游戏单位；留空则只使用像素。
3. 程序在新的 `runs/<时间>/clip_XX/` 保存截图与初始表格，并打开本地标注页面。默认先建立双方英雄，再按实际画面添加小兵；第一波普通兵线可明确启用首波模板。按蓝红阵营和永久唯一单位编号，以**完整血条中心**记录英雄、小兵；在确认阵亡帧设置死亡，后续不再记录该单位。填入动作、目标、相位与动作起止时间，可使用 AI 生成同一格式的标注再复核。
4. 距离只含**双方英雄之间**及**各英雄到对方存活小兵**，项数为 `1+n_blue+n_red`，不设六只或十三项上限。第一波双方各六只时恰好是 13 项。炮车线和多波重叠时，先在名册加入实际单位，再显式勾选距离对象；编号由阵营、兵种、波次、序号组成且永久唯一，阵亡后不复用。程序自动计算明确对象的像素距离及可选游戏距离估计。跨帧位移另需逐帧追踪同一地图纹理原点。
5. 在“英雄、符文与时点装备选择”输入录像补丁（如 `26.6`）并加载目录，以中英文名称或 ID 选择双方英雄、符文和属性碎片，保存并锁定对局配置。切到对应帧选择等级、Q/W/E/R 加点、六槽装备及独立饰品，确认背包完整性后记录时间快照；后续购买的装备只作用于后续时点。选择结果自动传给后台，无需手填 JSON。普攻、技能、符文和装备的静态资料自动携带，实际攻速、特殊射程、被动状态及条件效果仍需核验。可选外部选择器只导入身份，不导入网页数值。一般对线策略可作为可选纯文字参考，注明来源和适用条件。
6. 保存并导出。程序生成 UTF-8 BOM 事件表、距离表、动作间隔表及覆盖率报告。未知留空；人工或 AI 可编辑表格，通过 `import-table` 导回并重算距离，或在页面复核。
7. 可选：切到决策介入帧，生成短时推演任务，填写经过核验的地面坐标、有效机制、当前攻击相位和双方候选动作。先用 compare 比较事件、金币、经验、血蓝及冷却成本，无需安装求解包。升级、未知转火或机制失效会截断共同窗口，更新状态后再规划。
8. 可选：下载机制观察 CSV，按独立释放/触发机会记录非指向命中、被动、符文结果，导入后生成条件概率模型。已知规则使用确定计数器，隐藏初态使用状态情景；非指向多目标技能保留联合命中与小兵附带伤害。固定种子的场景抽样可复算，未知不算失败，命中率不能绕过射程、冷却或触发资格。
9. 可选：如需博弈求解，再声明适用于当前有效窗口的双方效用与终端价值，选择 zero_sum 或 general_sum。短时少得金币不直接判为失败；未兑现小兵资源单列。工具没有预置特定英雄状态、通用胜负结论或任意玩家分数。
10. 将 `assessment_bundle.zip` 交给支持文件输入的 AI 工具，或自行按框架评估。资料包包含截图、数据、英雄资料、策略、双语框架，以及可选的机制观察和推演结果。单片段分别评分；多片段统一窗口、条件和固定配置后比较。普通评估无需使用概率推演或博弈工具。

逐按钮操作、恢复工作区和表格编辑见 **[工作台详细指南](docs/workbench_guide.md)**；JSON/CSV 与 AI 接口见 **[操作与数据格式](docs/workflow.md)**；机制参数、概率输入和求解过程见 **[短时推演详细说明](docs/short_horizon.md)**。

英雄/符文/装备选择、时间快照、ARAMonly 分享链接和外部网页回传协议见 **[配置选择指南](docs/loadout_selection.md)**。固定配置可以导出再导入；第三方网站接入需支持相应分享格式或回传协议，不要求用户依赖指定网站。

通用脚本包括 [主程序](main.py)、[采样与表格计算](workbench/core.py)、[像素距离算法](algorithms/pixel_distance.py)、[事件推演](algorithms/short_horizon.py)、[概率与效果适配](algorithms/probabilistic_mechanics.py)、[机制观察统计](workbench/mechanic_observations.py)、[可选博弈接口](workbench/game_tools.py) 和 [通用事件队列](algorithms/event_queue.py)。

版本化资料与选择配置使用 [目录接口](workbench/catalog.py)、[时点配置解析](workbench/loadouts.py)、[可视化选择器](workbench/loadouts.js)、[外部分享链接适配](workbench/external_selectors.py)及 [网页回传适配器](integrations/selector_bridge.js)。

## 4. 其他说明

血条中心是画面测量口径。统一比例下的游戏距离只是估计，受投影、缩放和血条垂直偏移影响，不直接等于攻击判定距离。截图中缺失坐标时不会虚构距离或动作。实际时间精度受视频帧率限制。

评分需要核验参数、证据和固定规则。工作台不会独立给出可靠玩家水平分数，也不提供游戏内控制或实时采集；其他 AI 工程可通过 JSON/CSV 接口接入。内置推演是明确机制范围内的条件模型，不是全英雄游戏服务器模拟器。经验概率需核验迁移条件，情景分位数不自动等于置信区间或胜率；未实现的机制不得用任意概率掩盖。

测试与发布文件校验：

```sh
python -m unittest discover -s algorithms -p "test_*.py"
python -m unittest discover -s tests -p "test_*.py"
python scripts/verify_repository.py
```

原创建模文档和代码采用 [MIT](LICENSE)；第三方素材的许可范围见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)。

LOL Short-Window Last-Hit Decision Evaluation Framework is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
