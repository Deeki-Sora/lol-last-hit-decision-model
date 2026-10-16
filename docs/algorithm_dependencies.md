# 算法工具与依赖

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

## 视频编辑工具

[FFmpeg](https://ffmpeg.org/)用于视频剪辑、合并和抽帧，`ffprobe` 用于读取媒体元数据。它不是博弈求解器，也不是模型的决策算法。

Windows 可使用：

```powershell
winget install --id Gyan.FFmpeg --exact
```

macOS 可使用 `brew install ffmpeg`；Debian/Ubuntu 可使用 `sudo apt install ffmpeg`。也可通过 FFmpeg 官方下载入口选择相应平台构建。
