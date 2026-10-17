# 算法工具与依赖

本仓库还提供可审计的离散事件、有限状态信念、联合调度和风险调整效用实现。POMCP、Counterfactual Regret Minimization、OpenAI Five 和 AlphaStar 仅作为方法参照；不下载训练权重，也不把它们当作完整英雄机制模拟器。详见 [参数到算法的连接](parameter_algorithm_mapping.md)。

主模型第 48 节中的库可用于不同实现路线，不要求全部安装。它们提供调度、搜索或博弈求解工具，游戏状态、合法动作和机制规则仍由模型实现提供。

| 工具 | 用途 | 安装命令 |
|---|---|---|
| [SimPy](https://simpy.readthedocs.io/en/stable/) | 离散事件调度 | `python -m pip install simpy` |
| [NumPy](https://numpy.org/)、[SciPy](https://scipy.org/) | 数值计算、线性规划和受限 maximin | `python -m pip install numpy scipy` |
| [Nashpy](https://nashpy.readthedocs.io/en/stable/) | 有限策略矩阵与最优回应 | `python -m pip install nashpy` |
| [pomdp_py](https://h2r.github.io/pomdp-py/html/) | POUCT/POMCP 信念搜索 | `python -m pip install pomdp-py` |
| [PyGambit](https://gambitproject.readthedocs.io/en/stable/pygambit.html) | 一般和博弈求解 | `python -m pip install pygambit` |
| [OpenSpiel](https://openspiel.readthedocs.io/en/latest/) | MCTS、信息集搜索与 CFR 等算法 | `python -m pip install open_spiel` |

基本数值与矩阵工具也可按仓库清单安装：

```sh
python -m pip install -r requirements-algorithms.txt
```

仓库中的事件队列、像素距离工具和固定区间复算只使用 Python 标准库，不依赖上述可选库。

主程序 `python main.py` 的采样、标注、机制观察统计和 compare 事件推演使用标准库；采样需要 FFmpeg。可选 `python -m pip install -r requirements-game.txt` 安装矩阵工具；game-run 的 zero_sum 使用 NumPy/SciPy，general_sum 使用 Nashpy，输入收益来自已声明机制和初态的事件分支。独立的 solve 命令可处理外部已算好的零和矩阵。工作台提供 PyPI 下载链接，不会自动安装。

SimPy、pomdp_py、PyGambit、OpenSpiel 等仍供外部机制适配与搜索扩展；内置推演不依赖这些库，也不宣称已实现其完整算法。状态、合法动作和游戏规则不会通过安装库自动补齐。完整操作及机制范围见 [短时推演说明](short_horizon.md)。

颜色填充候选可用 `python -m pip install -r requirements-vision.txt` 安装 Pillow，再在 sample 子命令加 `--proposals`。候选不是已确认的血条中心，需要复核。

浏览器自动化测试为开发可选项：`python -m pip install -r requirements-test.txt` 后运行 `python -m playwright install chromium`；再运行 tests/ 下的测试。使用本机 Edge 时可设置环境变量 `LOL_BROWSER_CHANNEL=msedge`，不需要安装 Chromium。实际使用工作台只需普通浏览器，不需要 Playwright。

## 视频编辑工具

[FFmpeg](https://ffmpeg.org/)用于视频剪辑、合并和抽帧，`ffprobe` 用于读取媒体元数据。它不是博弈求解器，也不是模型的决策算法。

Windows 可使用：

```powershell
winget install --id Gyan.FFmpeg --exact
```

macOS 可使用 `brew install ffmpeg`；Debian/Ubuntu 可使用 `sudo apt install ffmpeg`。也可通过 FFmpeg 官方下载入口选择相应平台构建。
