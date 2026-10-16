#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定英雄参数，只改小兵坐标；验证后台、交互入口及坐标变换。

运行：python examples/four_outcomes.py
生成报告、完整交互记录与示意图；数据来源及估计项见报告。
"""
import contextlib
import importlib
import io
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from last_hit_positioning_v3 import Skill, solve_geometry, simulate_window

CASES = [
    ("普攻补刀并保留施法机会", (0, 0), (True, True, True)),
    ("只用普攻补刀", (2100, 0), (False, True, True)),
    ("技能补刀", (0, -300), (False, False, True)),
    ("短时上前补刀再回撤", (1000, -180), (False, False, True)),
]
E, F = (0, 1000), (0, 600)

def build(target, transform=lambda p: p, scale=1):
    # Lux当前仅E可用：最大圆心施法范围1100，E消耗中心有效距离1410。
    return solve_geometry(transform(E), transform(F), transform(target),
                          600 * scale, 550 * scale, 1100 * scale,
                          aa_mode="edge", safety_margin=20 * scale,
                          enemy_radius=0, self_radius=0, target_radius=0,
                          own_skill=Skill("circle", 1100 * scale, 310 * scale),
                          pressure_range=1410 * scale)

def flags(g):
    return not g.legalI.empty, not g.safeAaI.empty, not g.skillSafeI.empty

def window(g, scale=1):
    return simulate_window(g, 330 * scale, 325 * scale, .658)

def cli_run(index, target):
    cli = importlib.import_module("补刀站位_交互输入版_v3")
    # 选择游戏显示的普攻距离；未知体积全部回车0；敌方技能不纳入本次模拟。
    answers = ["Lux 对 Ashe", "0 1000", "0 600", f"{target[0]} {target[1]}",
               "2", "", "", "", "600", "550", "20", "1100", "", "1410", "0"]
    if index >= 2:
        answers += ["1", "330", "325", "", "", "",
                    "2", "0.658", "", ""]
    answers += [""]
    remaining = iter(answers)
    out = io.StringIO()
    def answer(prompt):
        value = next(remaining)
        print(prompt + value)
        return value
    with patch("builtins.input", side_effect=answer), contextlib.redirect_stdout(out):
        cli.main()
    assert list(remaining) == [], "交互输入没有全部使用"
    result = out.getvalue()
    expected = ["保留施法机会", "先补刀即可", "可以考虑用技能补刀", "可以尝试：来得及"]
    assert expected[index] in result, result
    assert "计算失败" not in result
    if index == 2:
        assert "还没退回等待位置" in result
    return result

def plot(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(2, 2, figsize=(12, 11))
    for ax, (name, target, g, sim) in zip(axes.flat, results):
        ax.add_patch(Circle(E, 600, color="#d44b4b", alpha=.12, label="敌方普攻范围"))
        ax.add_patch(Circle(E, 620, fill=False, color="#d44b4b", linestyle="--"))
        ax.add_patch(Circle(E, 1410, fill=False, color="#ad79bc", linestyle=":", label="Lux E能碰到对面的距离"))
        ax.add_patch(Circle(target, 550, fill=False, color="#438dca", label="小兵周围：普攻够得到"))
        ax.axhline(380, color="#a7a7a7", linewidth=1)
        interval = g.legalI if not g.legalI.empty else g.safeAaI
        if interval.empty:
            interval = g.skillSafeI
        p, q = g.point(interval.lo), g.point(interval.hi)
        ax.plot([p.x, q.x], [p.y, q.y], color="#239c65", linewidth=5, label="推荐站位段")
        for label, point, color in [("Ashe", E, "#c74242"), ("我方兵", F, "#7e5297"),
                                     ("待补兵", target, "#2678ae")]:
            ax.scatter(*point, color=color, s=45, zorder=5)
            ax.annotate(label, point, xytext=(6, 7), textcoords="offset points", fontsize=10)
        if sim:
            ax.scatter(sim.staging.x, sim.staging.y, marker="x", color="black", zorder=6)
            ax.plot([sim.staging.x, sim.hit.x], [sim.staging.y, sim.hit.y], color="black", linewidth=3)
            note = (f"上前 {sim.entry_dist:.0f}；" +
                    (f"{sim.return_time:.3f}秒退回，可尝试" if sim.window_valid else "退回超过冷却窗口"))
            ax.text(.03, .03, note, transform=ax.transAxes, fontsize=10,
                    bbox=dict(facecolor="white", alpha=.9, edgecolor="none"))
        ax.set_title(name + f"\n待补兵 {target}", fontsize=13)
        ax.set_xlim(-1500, 3000)
        ax.set_ylim(-950, 2250)
        ax.set_aspect("equal")
        ax.grid(alpha=.15)
        ax.set_xlabel("x（游戏距离单位）")
        ax.set_ylabel("y（游戏距离单位）")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(.5, .015))
    fig.suptitle("Lux 对 Ashe：固定属性，只改变待补小兵位置\n体积未知按0；安全距离手动留20；时间使用参考值", fontsize=15)
    fig.subplots_adjust(left=.08, right=.98, bottom=.13, top=.86, hspace=.55, wspace=.23)
    fig.savefig(path, dpi=150)
    plt.close(fig)

def main():
    results, transcripts = [], []
    for index, (name, target, expected) in enumerate(CASES):
        g = build(target)
        assert flags(g) == expected
        sim = window(g) if index >= 2 else None
        if sim:
            assert sim.ok and sim.window_valid == (index == 3)
        # 平移/旋转不会改变相对几何；长度与移速同比缩放也不改变时间或判定。
        for transform, scale in [(lambda p: (p[0]+275, p[1]-120), 1),
                                 (lambda p: (-p[1], p[0]), 1),
                                 (lambda p: (.01*p[0], .01*p[1]), .01)]:
            transformed = build(target, transform, scale)
            assert flags(transformed) == expected
            if sim:
                other = window(transformed, scale)
                assert other.window_valid == sim.window_valid
                assert abs(other.margin / scale - sim.margin) < 1e-6
        transcripts.append(f"===== 案例{index+1}：{name} =====\n" + cli_run(index, target))
        results.append((name, target, g, sim))
        print(f"案例{index+1} {target}：{name}；交互验证通过")
    here = Path(__file__).resolve().parent
    (here / "four_outcomes_transcript.txt").write_text("\n".join(transcripts), encoding="utf-8")
    plot(results, here / "four_outcomes.png")
    print("四案例、四次交互，以及平移/旋转/缩放检查全部通过。")
    sim = results[-1][-1]
    print(f"成功窗口：出手{sim.attack_time:.6f}s，退回{sim.return_time:.6f}s，"
          f"敌方转好{sim.ready_time:.6f}s，额外距离余量{sim.margin:.6f}。")

if __name__ == "__main__":
    main()
