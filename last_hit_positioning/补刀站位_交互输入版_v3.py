#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面向玩家的交互入口；计算与判定由核心模块负责。"""
from math import isfinite
from last_hit_positioning_v3 import (Skill, solve_geometry, simulate_window, print_all,
                              print_window, DEFAULT_REACTION, reference_windup)

def rp(msg):
    while True:
        values = input(msg).strip().replace("，", " ").replace(",", " ").split()
        try:
            result = tuple(float(v) for v in values)
            if len(result) == 2 and all(isfinite(v) for v in result):
                return result
        except ValueError:
            pass
        print("请输入两个数字，格式：x y")

def rn(msg, opt=False, default=None, positive=False):
    while True:
        value = input(msg).strip()
        if not value and (opt or default is not None):
            return default
        try:
            number = float(value)
            if isfinite(number) and (number > 0 if positive else number >= 0):
                return number
        except ValueError:
            pass
        print("请输入大于0的数字。" if positive else "请输入不小于0的数字；可跳过项可直接回车。")

def choice(msg, options, default):
    while True:
        value = input(msg).strip() or str(default)
        if value in tuple(str(v) for v in options):
            return int(value)
        print("请选择列出的编号。")

def read_skill(label, *, distance_label="技能距离", caster="施法英雄"):
    kind = choice(label + "：0暂不考虑 1指向性技能 2圆形范围技能 3直线非指向技能（默认0）：", (0, 1, 2, 3), 0)
    if kind == 0:
        return None
    if kind == 2:
        print(f"圆形技能距离：从{caster}中心到技能圆心的最远距离，不包含圆形范围的半径。")
    elif kind == 3:
        print(f"直线技能距离：从{caster}中心到技能轨迹末端的距离。")
    else:
        print(f"这里按从{caster}中心到目标中心的有效距离填写。")
    reach = rn(distance_label + "（不知道默认0）：", default=0)
    size = 0
    if kind == 2:
        size = rn("圆形范围的半径（不知道可回车，默认0）：", default=0)
    elif kind == 3:
        size = rn("技能宽度（完整宽度，不知道可回车，默认0）：", default=0)
    return Skill({1: "targeted", 2: "circle", 3: "line"}[kind], reach, size)

def read_windup(label, attack_speed=None):
    default = reference_windup(attack_speed)
    mode = choice(label + "：1输入秒数 2按攻速估算（默认1）：", (1, 2), 1)
    if mode == 1:
        return rn(f"{label}（秒，回车约{default:.3f}）：", default=default)
    print("不知道时按攻击周期的20%估算；这是参考值。")
    while True:
        percent = rn("前摇占攻击周期的百分比（默认20）：", default=20)
        if percent < 100:
            break
        print("百分比须小于100。")
    speed = attack_speed or rn("攻击速度（每秒攻击次数）：", positive=True)
    return percent / 100 / speed

def main():
    print("《补刀站位原则》：先找能补刀的位置，再考虑消耗。")
    print("原点是兵线交汇中心。坐标、距离、移速使用同一比例；秒数不缩放。")
    print("不知道的半径、技能大小可回车填0；时间默认值只作参考。")
    who = input("分析对象（可回车）：").strip() or "当前分析方"
    E = rp("敌方英雄坐标（x y）：")
    F = rp("敌方正在A的我方小兵坐标（x y）：")
    while E == F:
        print("英雄与小兵的中心不能重合，请重新输入小兵坐标。")
        F = rp("我方小兵坐标（x y）：")
    T = rp("准备补刀的敌方小兵坐标（x y）：")
    mode = choice("普攻距离：1已估计好中心之间的距离 2游戏显示的普攻距离（默认1）：", (1, 2), 1)
    er = sr = tr = 0
    if mode == 2:
        er = rn("敌方英雄半径（不知道默认0）：", default=0)
        sr = rn("你的英雄半径（不知道默认0）：", default=0)
        tr = rn("敌方小兵半径（不知道默认0）：", default=0)
    ea = rn("敌方普攻距离（默认0）：", default=0)
    sa = rn("你的普攻距离（默认0）：", default=0)
    margin = rn("额外留出的安全距离（默认0）：", default=0)
    print("最大施法范围：当前所有可用技能中，施法范围最大的那个，可能是护盾等非伤害技能。")
    print("它与消耗、补刀技能的距离分开计算；圆形技能的作用半径不加到圆心施法范围里。")
    sc = rn("你的最大施法范围（可跳过，默认0）：", opt=True, default=0)
    ec = rn("敌方最大施法范围（可跳过）：", opt=True)
    print("全图技能没有有限范围；最大范围暂无法用有限数表示时可跳过，具体技能另填。")
    print("消耗技能距离也用于技能补刀估算，无需重复填写；实际能否补到还要看技能和伤害。")
    pressure = rn("你的消耗技能距离（可跳过）：", opt=True)
    enemy_skill = read_skill("需要防范的敌方技能类型", distance_label="需要防范的敌方技能距离",
                             caster="敌方英雄")
    if mode == 1 and enemy_skill and enemy_skill.shape != "targeted":
        sr = rn("你的英雄半径（不知道默认0）：", default=0)
    settings = dict(aa_mode="edge" if mode == 2 else "effective", enemy_radius=er,
                    self_radius=sr, target_radius=tr, safety_margin=margin, enemy_skill=enemy_skill,
                    pressure_range=pressure)
    try:
        g = solve_geometry(E, F, T, ea, sa, sc, ec, skill_range=pressure, **settings)
        if g.safeAaI.empty and pressure is not None:
            print("普攻补刀位置不足，已按你的消耗技能距离自动计算技能补刀位置。")
        print("\n当前分析对象：" + who)
        print_all(g)
        if not g.safeAaI.empty:
            print("\n已有可直接普攻补刀的位置，本次无需计算上前再回撤。")
        elif choice("是否计算上前补一刀再退回来？0跳过 1计算（默认0）：", (0, 1), 0):
            sm = rn("你的移动速度（默认0）：", default=0)
            em = rn("敌方移动速度（默认0）：", default=0)
            reaction = rn("你的反应时间（秒，默认0.28）：", default=DEFAULT_REACTION)
            windup = read_windup("你的普攻前摇")
            timing = choice("敌方下一次普攻：1输入还需几秒 2按攻速估算（默认1）：", (1, 2), 1)
            if timing == 1:
                ready = rn("从敌方A出这一刀起，到下一次普攻转好还需几秒（默认0）：", default=0)
                sim = simulate_window(g, sm, em, reaction=reaction, windup=windup, remaining_cooldown=ready)
            else:
                speed = rn("敌方攻击速度（默认0）：", default=0)
                front = read_windup("敌方普攻前摇", speed if speed > 0 else None)
                sim = simulate_window(g, sm, em, speed, reaction, windup, enemy_windup=front)
            if em == 0:
                print("敌方移动速度为0：本次按敌方不移动估算。")
            print_window(g, sim, reaction, windup, sm, em)
    except ValueError as error:
        print("计算失败：", error)
    input("\n按回车退出。")

if __name__ == "__main__":
    main()
