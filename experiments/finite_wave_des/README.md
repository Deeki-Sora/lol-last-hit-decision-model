# 有限兵波离散事件实验

保留可检查的 SimPy 事件推进、固定随机种子的成对策略实验、受限矩阵博弈求解与机制测试。`initial_state.json` 是历史沙皇/永恩实验的条件初态，包含明确假设；不是亚索/维迦的重建输入，也不参与 A/B 的固定评分。

依赖只提供安装清单，不提交第三方包和平台二进制。

```powershell
python -m pip install -r requirements-simulation.txt
python -m unittest discover -s experiments/finite_wave_des -p "test_*.py"
python experiments/finite_wave_des/run_experiment.py --particles 16
```

测试检验该简化模型内的经验到账、弹道、伤害结算、死亡与资源守恒，不证明它与游戏服务器的完整机制一致。规则和参数的适用版本以初态文件为准。
