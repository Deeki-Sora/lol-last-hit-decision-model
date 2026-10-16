# 短时补兵决策模型 / Short-window Last-Hit Decision Model

以一方为中心，在一波小兵或约 20–30 秒的局部窗口内评估攻击目标、出手时机、下一刀可行性，以及双方取得金币和经验所支付的状态成本。

A player-centered framework for choosing minion targets and attack timing over a finite window, accounting for subsequent last hits, opposing responses, resource acquisition and state costs.

## 模型文档 / Model documents

- **[中文主模型](LoL_补兵时机参数化决策模型_Analyst_PreRelease_v0.91.md)**
- **[English model](LoL_Model_Analyst_PreRelease_v0.91.md)**

两份文档分别为中文与英文版本，章节、数学定义和编号对应。发布文件名为 v0.91，正文标识为 Analyst v0.911。

模型包含状态信念、合法动作、攻击提交与命中、小兵死亡序列、补刀窗口、自由时间、风险调整和有限策略搜索。它是研究与评估框架；本仓库的基础工具不构成完整的游戏机制实现。

## 算法工具与依赖 / Tools and dependencies

- [通用事件队列](algorithms/event_queue.py)：外部传入状态、事件和转移函数，不内置特定英雄或对局初态。
- [像素距离记录](docs/pixel_distance.md)与[计算工具](algorithms/pixel_distance.py)：使用血条中心和地图纹理原点，计算相对像素距离及跨帧位移。
- [算法依赖说明](docs/algorithm_dependencies.md)：SimPy、NumPy、SciPy、Nashpy，以及可选的信念搜索和博弈工具。

基础工具要求 Python 3.11+，仅使用标准库。主模型中引用的基本数值和博弈工具可安装为：

```sh
python -m pip install -r requirements-algorithms.txt
```

FFmpeg 是视频剪辑、合并和抽帧工具，不参与决策或博弈求解。各平台安装命令见[依赖说明](docs/algorithm_dependencies.md#视频编辑工具)。

## 参考案例 / Reference cases

[亚索 vs 维迦案例资料](case_data/yasuo_vs_veigar/README.md)提供 A、B 两场对线的视频、截图、动作数据和分析记录。A1/A2 是同一场对线的相邻素材，合并为 A，原片一并保留。

案例用于展示观测与评估过程，不限定模型适用的英雄。其[固定评分区间](case_data/yasuo_vs_veigar/reevaluation_v091/AB_1到3级评分区间.md)属于人工证据编码的敏感性分析，不是玩家段位或完整反事实模拟分数。原始动作表的缺失情况见[数据质量说明](DATA_QUALITY.md)。

## 检查 / Checks

从仓库根目录运行：

```sh
python -m unittest discover -s algorithms -p "test_*.py"
python scripts/verify_repository.py
```

完整性检查核对文档、资料文件和固定案例结果，不重新为案例打分。使用媒体元数据检查时需要 `ffprobe`。

## 许可证 / License

模型文档与原创代码采用 [MIT](LICENSE)。第三方录像及其截图等素材不纳入 MIT 授权，详见[许可范围](LICENSE_SCOPE.md)。
