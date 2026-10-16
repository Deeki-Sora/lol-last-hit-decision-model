# 参考案例档案

[亚索与维迦：两场对线的录像、数据和分析过程](yasuo_vs_veigar/README.md)。A1/A2 为同一场对线的相邻片段，合并观看版本与原片同时保留；B 为另一场对线。

这些资料用于复核研究过程，不是主程序运行依赖。历史动作表包含已损坏文本及未区分单位身份的距离带，不能直接作为新的定量距离输入；见 [数据质量说明](DATA_QUALITY.md)。固定评分是人工证据编码后的区间复算，不能证明工作台已经自动恢复动作或重建全部反事实。

冻结快照与脚本保持原字节。复算：

```sh
python example/yasuo_vs_veigar/reevaluation_v091/score_intervals.py
python scripts/verify_repository.py --examples
```

需要重做距离与动作时，使用主程序对原片建立新的工作区，遵循蓝红阵营、单位 ID、完整血条中心和死亡状态口径。不要把旧字段 `hero_minion_distance_band` 拆成凭空猜测的双方数值。

## 按双方拆分的复核入口

| 素材 | 原始视频 | 历史表 | 需要复核的距离 |
| --- | --- | --- | --- |
| A1 | [A1.webm](yasuo_vs_veigar/media/originals/A1.webm) | [动作表](yasuo_vs_veigar/action_table_0_3s.csv) | 英雄间；蓝方英雄→各红方存活小兵；红方英雄→各蓝方存活小兵 |
| A2 | [A2.webm](yasuo_vs_veigar/media/originals/A2.webm) | [动作表](yasuo_vs_veigar/action_table_v2_0_3s.csv) | 同上；波次、小兵编号重新核对 |
| B | [B.mp4](yasuo_vs_veigar/media/originals/B.mp4) | [动作表](yasuo_vs_veigar/action_table_2606_0_3s.csv) | 同上；不从身份不明的距离带反推坐标 |

第三方录像与截图不纳入原创代码的 MIT 授权，来源见案例内媒体 manifest。
