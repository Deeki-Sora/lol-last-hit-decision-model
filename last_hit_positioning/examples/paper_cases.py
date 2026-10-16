#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文两组数值例的独立核验；数据、场景假设及引用见论文第12、13节。

保持论文为独立推导；本文件仅供复算，不作为论文操作指南。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from last_hit_positioning_v3 import V, Skill, solve_geometry, simulate_window


def equal_range_case():
    red = V(0, 600)
    blue_minion, red_minion = (0, 100), (200, -100)
    blue = solve_geometry((red.x, red.y), blue_minion, red_minion, 550, 550, 1240,
                          1000, aa_mode="edge", enemy_radius=65, self_radius=65,
                          target_radius=48, safety_margin=20)
    assert blue.legalI.lo == 0 and blue.legalI.hi == 863
    selected = blue.conservative_point()
    assert selected == V(863, -100)
    response = solve_geometry((selected.x, selected.y), red_minion, blue_minion,
                              550, 550, 1000, 1240, aa_mode="edge", enemy_radius=65,
                              self_radius=65, target_radius=48, safety_margin=20)
    projection = response.legalI.clamp((red-response.Q).dot(response.n))
    moved = response.point(projection)
    assert moved == V(163, 600)
    # 原点不变，只交换双方角色以及两只小兵的用途。
    assert moved.dist(V(*blue_minion)) < response.self_aa
    assert response.safety_radius < moved.dist(selected) < response.self_cast
    # 整条最短直线路径也处于蓝方普攻范围外。
    for i in range(101):
        point = red + (moved-red)*(i/100)
        assert point.dist(selected) > response.safety_radius
    return dict(blue_interval=[blue.legalI.lo, blue.legalI.hi],
                blue_cast_interval=[blue.castI.lo, blue.castI.hi],
                blue_points=[[p.x, p.y] for p in (blue.aggressive_point(), blue.midpoint(), selected)],
                initial_separation=selected.dist(red), red_q=[response.Q.x, response.Q.y],
                red_a=response.a, red_b=response.b,
                red_aa_interval=[response.aaI.lo, response.aaI.hi],
                red_interval=[response.legalI.lo, response.legalI.hi],
                red_position=[moved.x, moved.y], red_move_distance=moved.dist(red),
                final_separation=moved.dist(selected), red_target_distance=moved.dist(V(*blue_minion)))


def large_range_case():
    def geometry(target):
        return solve_geometry((0, 900), (0, 400), target, 650, 125, 650,
                              aa_mode="edge", enemy_radius=65, self_radius=80,
                              target_radius=48, safety_margin=20,
                              own_skill=Skill("circle", 650, 400))
    static = geometry((300, -100))
    assert static.legalI.empty and not static.safeAaI.empty
    assert static.aggressive_point() == V(300, 85)
    assert static.aggressive_point().dist(static.T) == 185
    fronts = .2014/.638, .17708/.681
    ready = (1-.17708)/.681
    records = []
    for target, valid in [((900, -180), True), ((0, -180), False)]:
        g = geometry(target)
        assert g.safeAaI.empty and not g.skillSafeI.empty
        values = []
        for step in (.002, .0002):
            sim = simulate_window(g, 350, 325, .681, .28, fronts[0],
                                  enemy_windup=fronts[1], dt=step)
            assert sim.ok and sim.attack_completed and sim.returned
            assert sim.window_valid == valid
            values.append(sim)
        sim = values[-1]
        assert abs(values[0].dist_ready-sim.dist_ready) < .001
        initial = sim.staging.dist(g.E)
        # 返程结束后双方沿同一径向运动，距离增长率为350-325。
        bound = initial-325*sim.return_time+25*(ready-sim.return_time)
        assert sim.dist_ready >= bound-1e-6
        if valid:
            assert bound > g.safety_radius
        records.append(dict(target=target, entry=sim.entry_dist,
                            attack_time=sim.attack_time, return_time=sim.return_time,
                            ready_time=ready, initial_distance=initial,
                            distance_lower_bound=bound, final_distance=sim.dist_ready,
                            margin=sim.margin, valid=sim.window_valid,
                            skill_interval=[g.skillSafeI.lo, g.skillSafeI.hi]))
    return dict(aa_interval=[static.safeAaI.lo, static.safeAaI.hi],
                static_position=[300, 85], static_separation=static.aggressive_point().dist(static.E),
                static_skill_interval=[static.skillSafeI.lo, static.skillSafeI.hi],
                nasus_windup=fronts[0], caitlyn_windup=fronts[1],
                attack_range=static.enemy_aa, nasus_target_range=static.self_aa,
                safety_radius=static.safety_radius, windows=records,
                temporal_entry_limit=350/2*(ready-.28-fronts[0]))


def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    here = Path(__file__).resolve().parent
    def point(ax, xy, label, color):
        ax.scatter(*xy, color=color, s=35, zorder=5)
        offset = {"红方原位": (-55, 12), "红方响应": (8, -18)}.get(label, (6, 6))
        ax.annotate(label, xy, xytext=offset, textcoords="offset points", fontsize=9)
    def setup(ax, title, xlim, ylim):
        ax.set_title(title, fontsize=11)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect("equal")
        ax.grid(alpha=.15)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    fig, axes = plt.subplots(1, 2, figsize=(12, 7))
    red, blue = (0, 600), (863, -100)
    ax = axes[0]
    for radius, style, color in [(680, "-", "#cc5555"), (1000, "--", "#cc5555"),
                                 (1240, ":", "#4488bb")]:
        ax.add_patch(Circle(red, radius, fill=False, linestyle=style, edgecolor=color))
    ax.add_patch(Circle((200, -100), 663, color="#4488bb", alpha=.08))
    ax.plot([0, 863], [-100, -100], color="#239c65", linewidth=5)
    for xy, label, color in [(red, "红：Ahri", "#cc5555"), (blue, "蓝：Lux选定点", "#4488bb"),
                              ((0, 100), "蓝方兵", "#4488bb"), ((200, -100), "红方兵", "#cc5555")]:
        point(ax, xy, label, color)
    setup(ax, "先固定红方，求蓝方站位\n实线：红方普攻；虚线：红方最大范围1000\n点线：蓝方最大范围1240的候选包络", (-1400, 1550), (-950, 2000))
    ax = axes[1]
    ax.add_patch(Circle(blue, 680, color="#4488bb", alpha=.08))
    ax.add_patch(Circle(blue, 1000, fill=False, linestyle="--", edgecolor="#cc5555"))
    ax.add_patch(Circle((0, 100), 663, fill=False, linestyle=":", edgecolor="#cc5555"))
    ax.plot([163, 163], [-100, 614.142842854285], color="#239c65", linewidth=5)
    ax.annotate("", (163, 600), red, arrowprops=dict(arrowstyle="->", color="#cc5555", lw=2))
    for xy, label, color in [(blue, "固定蓝方", "#4488bb"), (red, "红方原位", "#cc5555"),
                              ((163, 600), "红方响应", "#cc5555"), ((0, 100), "红方待补兵", "#888888")]:
        point(ax, xy, label, color)
    ax.text(.03, .04, "切线候选段内最短移动：163", transform=ax.transAxes, fontsize=10)
    setup(ax, "再固定蓝方，交换双方视角\n蓝色圆盘：蓝方普攻；虚线：红方最大范围包络\n点线：红方补刀可达范围", (-1000, 1850), (-1000, 1750))
    fig.tight_layout()
    fig.savefig(here/"paper_equal_range.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax in axes:
        ax.add_patch(Circle((0, 900), 795, color="#cc5555", alpha=.08))
        ax.add_patch(Circle((0, 900), 815, fill=False, linestyle="--", edgecolor="#cc5555"))
        ax.axhline(85, color="#aaaaaa", lw=1)
        point(ax, (0, 900), "Caitlyn", "#cc5555")
        point(ax, (0, 400), "蓝方兵", "#888888")
    ax = axes[0]
    ax.add_patch(Circle((300, -100), 253, fill=False, edgecolor="#4488bb"))
    ax.plot([127.419584, 472.580416], [85, 85], color="#239c65", lw=5)
    point(ax, (300, -100), "待补兵", "#cc5555")
    point(ax, (300, 85), "Nasus可直接普攻", "#4488bb")
    setup(ax, "短手也可存在安全普攻补刀段\n红色圆盘：敌方普攻；虚线：含20裕量\n蓝色圆：己方对目标兵的普攻可达范围", (-1100, 1500), (-450, 1800))
    ax = axes[1]
    for x, tag, color in [(900, "成功例", "#239c65"), (0, "失败对照", "#cc5555")]:
        ax.add_patch(Circle((x, -180), 253, fill=False, edgecolor=color, alpha=.7))
        ax.plot([x, x], [85, 73], color=color, linewidth=5)
        point(ax, (x, -180), tag + "待补兵", color)
        point(ax, (x, 85), tag + "等待点", color)
    ax.text(.03, .03, "两例均上前12、约0.664秒退回\n截止距离：成功约1011.905；失败约612.724", transform=ax.transAxes, fontsize=9,
            bbox=dict(facecolor="white", alpha=.9, edgecolor="none"))
    setup(ax, "同样的时间计划，不同的追击结果\n均计入英雄与小兵体积\n仅研究普通普攻追击，不涵盖技能", (-1100, 1600), (-450, 1800))
    fig.tight_layout()
    fig.savefig(here/"paper_large_range.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    results = dict(equal_range=equal_range_case(), large_range=large_range_case())
    here = Path(__file__).resolve().parent
    (here/"paper_cases_values.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    figures()
    print(json.dumps(results, indent=2))
