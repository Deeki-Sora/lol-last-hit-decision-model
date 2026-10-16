"""覆盖距离口径、技能碰撞、缩放一致性和窗口误报的回归检查。"""
import contextlib
import importlib
import io
import math
import unittest
from unittest.mock import patch

from last_hit_positioning_v3 import (Skill, V, solve_geometry, simulate_window, print_all,
                              DEFAULT_REACTION, DEFAULT_WINDUP, reference_windup)


class GeometryTests(unittest.TestCase):
    def test_skill_fallback_reports_max_cast_for_each_position(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 550, 150, 650,
                           skill_range=700)
        self.assertTrue(g.safeAaI.empty)
        self.assertFalse(g.skillSafeI.empty)
        self.assertLess(g.aggressive_point().dist(g.E), g.self_cast)
        self.assertGreater(g.conservative_point().dist(g.E), g.self_cast)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): print_all(g)
        self.assertIn("己方最大施法范围：敌方在范围内。", out.getvalue())
        self.assertIn("己方最大施法范围：敌方在范围外。", out.getvalue())

    def test_fixed_direction_miss_does_not_claim_a_completed_dodge(self):
        g = solve_geometry((0, 0), (100, 0), (550, 200), 550, 150, 1000,
                           self_radius=30, enemy_skill=Skill("line", 800, 10))
        self.assertFalse(g.enemy_skill.aimed_at_q_hits(g.E, g.Q, g.aggressive_point(), g.self_radius))
        out = io.StringIO()
        with contextlib.redirect_stdout(out): print_all(g)
        self.assertIn("技能范围未覆盖这里", out.getvalue())
        self.assertIn("改换落点或方向仍可能命中", out.getvalue())
        self.assertIn("尚未计算技能飞行时间与躲避过程", out.getvalue())
        self.assertNotIn("避开了技能范围", out.getvalue())

    def test_max_cast_does_not_imply_damage_and_skill_ranges_are_independent(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 550, 550, 1000,
                           pressure_range=100, own_skill=Skill("circle", 300, 50))
        self.assertFalse(g.legalI.empty)
        self.assertEqual(g.self_cast, 1000)
        self.assertEqual(g.pressure_range, 100)
        self.assertEqual(g.skill_range, 350)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): print_all(g)
        self.assertIn("保留施法机会", out.getvalue())
        self.assertIn("你的消耗技能：这个位置暂时够不到对面", out.getvalue())
        self.assertNotIn("保留消耗对面的机会", out.getvalue())

    def test_original_example(self):
        g = solve_geometry((300, 300), (-100, 100), (100, -100), 550, 550, 800)
        self.assertAlmostEqual(g.legalI.hi, 580.9475019311126)
        self.assertEqual(g.legalI.lo, 0)

    def test_edge_mode_and_margin(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 600, 550, 1100,
                           aa_mode="edge", enemy_radius=65, self_radius=65,
                           target_radius=48, safety_margin=20)
        self.assertEqual(g.enemy_aa, 730)
        self.assertEqual(g.self_aa, 663)
        self.assertEqual(g.Q, V(750, 0))

    def test_effective_mode_does_not_double_count(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 730, 663, 1100,
                           enemy_radius=65, self_radius=65, target_radius=48)
        self.assertEqual(g.enemy_aa, 730)
        self.assertEqual(g.self_aa, 663)

    def test_circle_reach_and_line_width(self):
        self.assertEqual(Skill("circle", 1100, 310).target_reach(48), 1458)
        self.assertEqual(Skill("line", 1100, 140).target_reach(48), 1148)
        self.assertEqual(Skill("line", 1100, 500).target_reach(48), 1148)

    def test_circle_q_risk(self):
        skill = Skill("circle", 1000, 100)
        self.assertTrue(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(500, 150), 50))
        self.assertFalse(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(500, 151), 50))
        self.assertFalse(Skill("circle", 400, 200).aimed_at_q_hits(
            V(0, 0), V(500, 0), V(500, 0), 50))

    def test_line_full_width_and_endpoint(self):
        skill = Skill("line", 800, 140)
        self.assertTrue(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(500, 120), 50))
        self.assertFalse(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(500, 121), 50))
        self.assertTrue(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(850, 0), 50))
        self.assertFalse(skill.aimed_at_q_hits(V(0, 0), V(500, 0), V(851, 0), 50))

    def test_invalid_data_and_no_official_bounds(self):
        g = solve_geometry((0, 0), (1, 0), (4, 1), 5, 3, 8)
        self.assertEqual(g.enemy_aa, 5)
        for value in (-1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                solve_geometry((0, 0), (1, 0), (4, 1), value, 3, 8)
        with self.assertRaises(ValueError):
            solve_geometry((math.nan, 0), (1, 0), (4, 1), 5, 3, 8)

    def test_ambiguous_skill_input_rejected(self):
        with self.assertRaises(ValueError):
            solve_geometry((0, 0), (1, 0), (4, 1), 5, 3, 8,
                           skill_range=7, own_skill=Skill("circle", 5, 2))

    def test_zero_margin_boundary_is_explicit(self):
        g = solve_geometry((0, 0), (1, 0), (5, 0), 5, 1, 8)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): print_all(g)
        self.assertIn("仍可能被A到", out.getvalue())

    def test_screenshot_falls_back_to_aa_without_pressure(self):
        g = solve_geometry((-600, 400), (-100, 100), (100, -100), 550, 250, 600,
                           800, 400, aa_mode="edge", enemy_radius=20, self_radius=30,
                           target_radius=10, safety_margin=10)
        self.assertTrue(g.legalI.empty)
        self.assertFalse(g.safeAaI.empty)
        self.assertAlmostEqual(g.safeAaI.lo, -219.75250786711518)
        for point in (g.aggressive_point(), g.midpoint(), g.conservative_point()):
            self.assertLessEqual(point.dist(g.T), g.self_aa + 1e-9)
            self.assertGreaterEqual(point.dist(g.E), g.safety_radius - 1e-9)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): print_all(g)
        self.assertIn("先补刀即可", out.getvalue())
        self.assertNotIn("普攻补兵", out.getvalue())
        self.assertNotIn("切点Q", out.getvalue())

    def test_skill_fallback_does_not_require_pressure(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 550, 150, 100,
                           own_skill=Skill("targeted", 400, 0))
        self.assertTrue(g.safeAaI.empty)
        self.assertIsNone(g.castI)
        self.assertFalse(g.skillSafeI.empty)
        self.assertTrue(g.skillPressureI.empty)
        self.assertIsNotNone(g.aggressive_point())

    def test_targeted_distance_does_not_add_target_radius(self):
        self.assertEqual(Skill("targeted", 600, 0).target_reach(50), 600)
        self.assertTrue(Skill("targeted", 600, 0).aimed_at_q_hits(
            V(0, 0), V(500, 0), V(600, 0), 50))
        self.assertFalse(Skill("targeted", 600, 0).aimed_at_q_hits(
            V(0, 0), V(500, 0), V(601, 0), 50))


class WindowTests(unittest.TestCase):
    def geometry(self, scale=1, margin=0):
        return solve_geometry((0, 0), (100 * scale, 0), (800 * scale, 200 * scale),
                              550 * scale, 150 * scale, 1000 * scale,
                              safety_margin=margin * scale)

    def test_reaction_longer_than_window_cannot_succeed(self):
        sim = simulate_window(self.geometry(), 350, 0, reaction=2, windup=.2,
                              remaining_cooldown=1)
        self.assertTrue(sim.ok)
        self.assertGreater(sim.margin, 0)
        self.assertFalse(sim.attack_completed)
        self.assertFalse(sim.window_valid)

    def test_completed_attack_without_return_is_rejected(self):
        sim = simulate_window(self.geometry(), 350, 0, reaction=0, windup=.1,
                              remaining_cooldown=.45)
        self.assertTrue(sim.attack_completed)
        self.assertFalse(sim.returned)
        self.assertFalse(sim.window_valid)

    def test_success_requires_attack_return_and_margin(self):
        sim = simulate_window(self.geometry(), 350, 0, reaction=.1, windup=.2,
                              remaining_cooldown=2)
        self.assertTrue(sim.window_valid)
        self.assertAlmostEqual(sim.return_time, .1 + .2 + 200 / 350)

    def test_default_times_and_cooldown_origin(self):
        g = self.geometry()
        default = simulate_window(g, 350, 0, 1)
        self.assertTrue(default.ok)
        self.assertEqual(default.reaction_time, DEFAULT_REACTION)
        self.assertEqual(default.windup_time, DEFAULT_WINDUP)
        self.assertAlmostEqual(default.ready_time, 1 - reference_windup(1))
        self.assertTrue(simulate_window(g, 350, 0, 1, .1, .2).ok)
        sim = simulate_window(g, 350, 0, 1, .1, .2, enemy_windup=.3)
        self.assertAlmostEqual(sim.ready_time, .7)
        self.assertEqual(sim.period, 1)
        self.assertFalse(simulate_window(g, 350, 0, 1, .1, .2, enemy_windup=1).ok)

    def test_window_remains_available_when_pressure_range_is_too_short(self):
        g = solve_geometry((0, 0), (100, 0), (800, 200), 550, 150, 100)
        self.assertIsNone(g.castI)
        sim = simulate_window(g, 350, 0, reaction=.1, windup=.2, remaining_cooldown=2)
        self.assertTrue(sim.ok)
        self.assertTrue(sim.window_valid)

    def test_scaled_geometry_speeds_and_decisions(self):
        for enemy_speed in (0, 350):
            base = simulate_window(self.geometry(margin=10), 350, enemy_speed,
                                   reaction=.1, windup=.2, remaining_cooldown=2)
            for scale in (.1, .01, 10):
                sim = simulate_window(self.geometry(scale, 10), 350 * scale,
                                      enemy_speed * scale, reaction=.1, windup=.2,
                                      remaining_cooldown=2)
                self.assertAlmostEqual(sim.margin, base.margin * scale)
                self.assertAlmostEqual(sim.distance_tolerance, base.distance_tolerance * scale)
                self.assertAlmostEqual(sim.return_time, base.return_time)
                self.assertEqual(sim.classification, base.classification)

    def test_phase_times_do_not_round_to_dt(self):
        times = []
        for dt in (.01, .002, .0002):
            sim = simulate_window(self.geometry(), 350, 350, reaction=.153, windup=.157,
                                  remaining_cooldown=2, dt=dt)
            times.append(sim.return_time)
        self.assertEqual(times[0], times[1])
        self.assertEqual(times[1], times[2])

    def test_invalid_time_inputs(self):
        for arguments in ({"dt": 0}, {"reaction": -1}, {"windup": math.inf},
                          {"remaining_cooldown": 0}):
            defaults = dict(reaction=.1, windup=.2, remaining_cooldown=1)
            defaults.update(arguments)
            self.assertFalse(simulate_window(self.geometry(), 350, 0, **defaults).ok)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.cli = importlib.import_module("补刀站位_交互输入版_v3")

    def test_margin_default_and_small_value(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(self.cli.rn("", default=0), 0)
        with patch("builtins.input", return_value="5"):
            self.assertEqual(self.cli.rn(""), 5)

    def test_invalid_nonfinite_then_valid(self):
        with patch("builtins.input", side_effect=["nan", "inf", "-1", "0", "0.658"]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.cli.rn("", positive=True), .658)

    def test_full_static_flow_skips_dynamic_inputs(self):
        inputs = ["", "300 300", "-100 100", "100 -100", "1", "550", "550",
                  "", "800", "", "", "0", ""]
        out = io.StringIO()
        with patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
            self.cli.main()
        self.assertIn("已有可直接普攻补刀的位置", out.getvalue())

    def test_full_no_solution_flow_with_estimated_times(self):
        inputs = ["", "0 0", "100 0", "800 200", "1", "550", "150", "", "1000",
                  "", "", "0", "1", "350", "0", "2", "1", ".2", "1", "1", ""]
        out = io.StringIO()
        with patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
            self.cli.main()
        self.assertIn("还没A出这一刀", out.getvalue())

    def test_unknown_windup_uses_default(self):
        with patch("builtins.input", side_effect=["", ""]):
            self.assertEqual(self.cli.read_windup("普攻前摇"), DEFAULT_WINDUP)
        with patch("builtins.input", side_effect=["", ""]):
            self.assertAlmostEqual(self.cli.read_windup("普攻前摇", 2), .1)

    def test_unknown_skill_dimensions_are_zero(self):
        with patch("builtins.input", side_effect=["2", "", ""]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.read_skill("技能类型"), Skill("circle", 0, 0))
        with patch("builtins.input", side_effect=["3", "1000", ""]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.cli.read_skill("技能类型"), Skill("line", 1000, 0))

    def test_full_flow_unknown_radii_are_zero(self):
        inputs = ["", "300 300", "-100 100", "100 -100", "2", "", "", "",
                  "550", "550", "", "800", "", "", "0", ""]
        out = io.StringIO()
        with patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
            self.cli.main()
        self.assertIn("敌方普攻距离：550.000", out.getvalue())

    def test_full_flow_window_with_unknown_times_and_no_pressure(self):
        inputs = ["", "0 0", "100 0", "800 200", "1", "550", "150", "", "",
                  "", "", "0", "1", "350", "0", "", "", "", "2", "1", "", "", ""]
        out = io.StringIO()
        with patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
            self.cli.main()
        self.assertIn("能不能上前补一刀再退回来", out.getvalue())
        self.assertIn("你的反应时间 0.280 秒，普攻前摇 0.300 秒", out.getvalue())

    def test_consumption_distance_automatically_provides_skill_fallback(self):
        inputs = ["", "0 0", "100 0", "800 200", "1", "550", "150", "",
                  "1000", "", "400", "0", "0", ""]
        prompts, out = [], io.StringIO()
        answers = iter(inputs)
        def answer(prompt):
            prompts.append(prompt)
            return next(answers)
        with patch("builtins.input", side_effect=answer), contextlib.redirect_stdout(out):
            self.cli.main()
        self.assertEqual(list(answers), [])
        self.assertIn("你的消耗技能距离（可跳过）：", prompts)
        self.assertIn("自动计算技能补刀位置", out.getvalue())
        self.assertIn("可以考虑用技能补刀", out.getvalue())
        self.assertFalse(any("补刀的具体技能类型" in prompt for prompt in prompts))

    def test_enemy_circle_distance_prompt_defines_origin(self):
        answers = iter(["2", "800", "100"])
        prompts, out = [], io.StringIO()
        def answer(prompt):
            prompts.append(prompt)
            return next(answers)
        with patch("builtins.input", side_effect=answer), contextlib.redirect_stdout(out):
            skill = self.cli.read_skill("需要防范的敌方技能类型",
                                        distance_label="需要防范的敌方技能距离", caster="敌方英雄")
        self.assertEqual(skill, Skill("circle", 800, 100))
        self.assertIn("需要防范的敌方技能距离（不知道默认0）：", prompts)
        self.assertIn("从敌方英雄中心到技能圆心", out.getvalue())
        self.assertIn("不包含圆形范围的半径", out.getvalue())


if __name__ == "__main__":
    unittest.main()
