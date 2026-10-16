#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ashe/Lux查询值+明确标记的手动估计；详见README数据来源。

从项目目录运行：python examples/real_values.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from last_hit_positioning_v3 import Skill, solve_geometry, simulate_window, print_all


def build_example(number, scale=1.0):
    # 查询值：Ashe射程600/移速325/攻速0.658，Lux射程550/移速330，E圆心距离1100/半径310。
    # 手动估计：两英雄玩法半径65、目标兵半径48；坐标是构造案例，不是游戏实测。
    points = ((300, 300), (-100, 100), (100, -100)) if number == 1 else (
        (-300, -150), (50, -50), (-350, 50))
    points = [tuple(scale * v for v in p) for p in points]
    g = solve_geometry(*points, 600 * scale, 550 * scale, 1100 * scale,
                       aa_mode="edge", enemy_radius=65 * scale,
                       self_radius=65 * scale, target_radius=48 * scale,
                       safety_margin=0, own_skill=Skill("circle", 1100 * scale, 310 * scale))
    return g


def main():
    for number in (1, 2):
        print(f"\n===== 案例{number}：敌方Ashe，己方Lux =====")
        print("查询参数与手动估计参数分开记录；真实版本值请运行前复核。")
        g = build_example(number)
        if number == 1:
            print_all(g)
        else:
            # 以下均为手动估计演示，不是玩家实测平均值或英雄真实前摇数据。
            reaction, windup, enemy_windup = .20, .25, .30
            print("时间手动估计：反应0.20秒、Lux前摇0.25秒、Ashe前摇0.30秒。")
            sim = simulate_window(g, 330, 325, .658, reaction, windup,
                                  enemy_windup=enemy_windup)
            print_all(g, sim, reaction, windup, 330, 325, .658)


if __name__ == "__main__":
    main()
