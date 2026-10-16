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
| 英雄与策略预输入 | 官方基础数据下载、参数与策略存储 | 必需的版本与有效参数核验；可选策略文字 |
| 评分与未来分支 | 打包框架、证据及评估请求 | 使用固定配置计算双边评分、未来兵链及反事实 |
| 有限博弈 | 可选评估收益矩阵求解入口、通用事件队列 | 定义候选、回应、机制及收益 |

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

可选数值、事件及博弈包：

```sh
python -m pip install -r requirements-algorithms.txt
python main.py solve --matrix assessed_matrix.json --output matrix_solution.json
```

NumPy / SciPy 用于数值及有限零和矩阵求解；SimPy 和 Nashpy 可供自定义事件机制、一般和博弈扩展。各工具用途见 [依赖说明](docs/algorithm_dependencies.md)。FFmpeg 只负责视频处理，不参与评分或博弈计算。

官方数据查询需要 HTTPS 连接。Python 环境缺少根证书时，可安装可选证书包：`python -m pip install -r requirements-data.txt`。查询失败也可自行核验资料后手动填写，不影响采样和表格功能。

## 3. 操作指南

1. 将一个或多个录像放入空白的 `input_videos/` 文件夹，或启动后输入自己的文件夹路径；输入 `choose` 可打开文件夹选择器。
2. 运行 `python main.py`，选择视频、源视频开始/结束时间，以及 **0.1–0.5 秒**的采样间隔。可输入 `189=350`，表示 189 像素约为 350 游戏单位；留空则只使用像素。
3. 程序在新的 `runs/<时间>/clip_XX/` 保存截图与初始表格，并打开本地标注页面。默认先建立双方英雄，再按实际画面添加小兵；第一波普通兵线可明确启用首波模板。按蓝红阵营和永久唯一单位编号，以**完整血条中心**记录英雄、小兵；在确认阵亡帧设置死亡，后续不再记录该单位。填入动作、目标、相位与动作起止时间，可使用 AI 生成同一格式的标注再复核。
4. 距离只含**双方英雄之间**及**各英雄到对方存活小兵**，项数为 `1+n_blue+n_red`，不设六只或十三项上限。第一波双方各六只时恰好是 13 项。炮车线和多波重叠时，先在名册加入实际单位，再显式勾选距离对象；编号由阵营、兵种、波次、序号组成且永久唯一，阵亡后不复用。程序自动计算明确对象的像素距离及可选游戏距离估计。跨帧位移另需逐帧追踪同一地图纹理原点。
5. 查询并输入双方英雄的版本、等级、普攻/技能范围、实际攻速、移速、技能加点、装备、符文与被动状态（必需）。可通过 `fetch-data` 获取官方基础数据；有效参数仍需核验。一般对线策略可作为可选纯文字参考，注明来源和适用条件。
6. 保存并导出。程序生成 UTF-8 BOM 事件表、距离表、动作间隔表及覆盖率报告。未知留空；人工或 AI 可编辑表格，通过 `import-table` 导回并重算距离，或在页面复核。
7. 将 `assessment_bundle.zip` 交给支持文件输入的 AI 工具，或自行按框架评估。资料包包含截图、数据、英雄资料、策略、双语框架和评估请求，无需访问原工程文件。单片段分别评分；多片段统一窗口、条件和评分配置后比较。未完成对局从最后可确认状态向未来推演，反事实从同一初态建立分支。
8. 评估后如需博弈计算，将已明确候选与收益的有限零和矩阵交给 `solve`。其他博弈类型和完整游戏机制由调用方实现；工具不会从录像自动产生可靠收益矩阵。

完整命令、JSON/CSV 格式、AI 接口、参数查询及可选求解示例见 **[操作与数据指南](docs/workflow.md)**。通用脚本包括 [主程序](main.py)、[采样与表格计算](workbench/core.py)、[像素距离算法](algorithms/pixel_distance.py)、[标注与预输入工具](workbench/operations.py) 和 [有限事件队列](algorithms/event_queue.py)。

## 4. 其他说明

血条中心是画面测量口径。统一比例下的游戏距离只是估计，受投影、缩放和血条垂直偏移影响，不直接等于攻击判定距离。截图中缺失坐标时不会虚构距离或动作。实际时间精度受视频帧率限制。

评分需要核验参数、证据和固定规则。当前工作台不会独立给出可靠玩家水平分数，也不提供游戏内控制或实时采集；其他 AI 工程可通过开放的 JSON/CSV 接口接入。未来分支与反事实的可信度取决于所声明的机制、初态和敌方回应假设。

测试与发布文件校验：

```sh
python -m unittest discover -s algorithms -p "test_*.py"
python -m unittest discover -s tests -p "test_*.py"
python scripts/verify_repository.py
```

原创建模文档和代码采用 [MIT](LICENSE)；第三方素材的许可范围见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)。

LOL Short-Window Last-Hit Decision Evaluation Framework is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
