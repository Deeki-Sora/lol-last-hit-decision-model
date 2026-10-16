# 短时补兵决策模型与可核验案例

研究一波小兵或约 20–30 秒局部窗口中的目标选择、攻击时机、下一刀保持，以及取得资源所支付的成本。较长案例按局部窗口解释，双方分别评价。

## 主模型

- [主模型 · Analyst v0.91](LoL_补兵时机参数化决策模型_Analyst_PreRelease_v0.91.md)
- [相同内容的 ASCII 文件名](LoL_Model_Analyst_PreRelease_v0.91.md)

文件名沿用 v0.91；正文版本标识为 v0.911。两份文件内容完全相同。

## 亚索 vs 维迦

[案例入口](case_data/yasuo_vs_veigar/README.md)包含原视频、合并后的 A 视频、逐帧图像、原始动作表、合并时间索引、分析记录和固定评分区间。A1/A2 是同一场对线的相邻片段，合并后记为 A；B 是另一场对线。

当前评分引用：[四人 1–3 级评分区间](case_data/yasuo_vs_veigar/reevaluation_v091/AB_1到3级评分区间.md)，固定版本 `AB-L1-L3-interval-1.0`。

这些区间是人工证据编码的敏感性区间，覆盖共同可评项目的原权重 63%，不是统计置信区间、段位映射或完整反事实模拟得分。[数据质量与适用范围](DATA_QUALITY.md)明确了缺失字段和历史分析的边界。

## 运行

需要 Python 3.11+。评分和完整性检查使用标准库；视频操作需要 FFmpeg 和 ffprobe。

主模型尚不是可直接控制游戏的完整程序。可执行部分包括固定评分复算、[站位几何与短时窗口工具](last_hit_positioning/README.md)，以及[有限兵波事件仿真实验](experiments/finite_wave_des/README.md)。仿真实验使用历史条件初态，不作为亚索/维迦评分的反事实证明。

```powershell
python case_data/yasuo_vs_veigar/reevaluation_v091/score_intervals.py
python scripts/verify_repository.py
```

几何工具无需第三方依赖：

```powershell
python -m unittest discover -s last_hit_positioning -p "test_*.py"
```

可选仿真实验依赖与测试：

```powershell
python -m pip install -r requirements-simulation.txt
python -m unittest discover -s experiments/finite_wave_des -p "test_*.py"
```

可选安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
# FFmpeg 未安装时，可显式选择：
powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -InstallFFmpeg
```

重新生成 A 合并视频和动作索引：

```powershell
python scripts/prepare_case_media.py --force
```

FFmpeg 版本或编码器不同可能产生不同视频文件字节；评分证据快照不随视频重编码改变。完整性检查用于验证随仓库交付的归档字节，重生成文件之后应作为独立版本管理。

另取截图时写入新目录，避免覆盖归档证据：

```powershell
python scripts/extract_frames.py case_data/yasuo_vs_veigar/media/A_merged.mp4 review_frames/A --step 0.3
```

## 目录

```text
主模型与 ASCII 别名
case_data/yasuo_vs_veigar/
  media/originals/       A1、A2、B 原视频
  media/A_merged.mp4     A1/A2 去除接缝重叠后的观看版
  frames_*/             历史 0.3 秒截图
  verify_0_1s_B/         B 的局部 0.1 秒核验截图
  reevaluation_v091/    高清证据、分析、脚本与固定评分快照
  A_combined_action_index.csv
scripts/                合并、抽帧、安装和完整性检查
last_hit_positioning/    站位几何、短时窗口和测试
experiments/finite_wave_des/  简化事件仿真、受限策略实验和测试
docs/research/          模型变量审计与算法研究说明
```

视频属于案例研究素材，未在本仓库中授予其再分发许可；代码、模型文字与视频素材的权利不混同。仓库未指定开源许可证。
