"""Synthetic mechanism invariants, not data for any particular champion."""
from copy import deepcopy
import importlib.util
import tempfile
from pathlib import Path
import unittest
import subprocess
import sys
import json
from algorithms.short_horizon import compare,validate
from workbench.game_tools import run_task,save_run,draft


def damage(base=50,kind='physical'):
    return dict(type=kind,base=base,target_current_hp_ratio=0,target_max_hp_ratio=0)


def unit(side,kind,position):
    u=dict(side=side,kind=kind,position=position,hp=100,max_hp=100,radius=10,move_speed=100,hp_regen_s=0,
        armor=0,magic_resist=0,mana=100,max_mana=100,mana_regen_s=0,resource_model='mana',phase='idle',
        movement=dict(verified=True,destination=None),effects_inactive_verified=True,
        effects_scope_note='Synthetic fixture with no stateful effects',skills={},shields=[],
        attack=dict(attack_speed=1,period_s=1,windup_s=.1,range=100,range_mode='edge_to_edge',missile_speed=0,ready_in_s=0,damage=damage()))
    if kind=='hero':u.update(level=1,xp=0,next_level_xp=1000,gold_multiplier=1,xp_multiplier=1)
    else:u.update(gold_reward=10,xp_reward=20,locked_target=None,idle_verified_until_s=30)
    return u


def task():
    spec=dict(schema_version=1,enabled=True,entry_time_s=60,horizon_s=1,backend='compare',
        rules=dict(verified=True,patch='synthetic-test',sources=['synthetic invariant fixture'],unit_scope_verified=True,unit_scope_note='Synthetic closed test scope',
            geometry='verified_game_ground_coordinates',level_up='replan',retarget='replan',hero_aggro='replan',aggro_triggers=[],
            unmodelled_effects='replan',pathing='verified_clear_straight_segments',xp_mode='solo_lane',xp_range=1000,
            solo_xp_multiplier=1,last_hitter_xp_outside_range=True,projectile_step_s=.01,unsupported_mechanics=[]),
        units={'bh':unit('blue','hero',[0,0]),'rh':unit('red','hero',[300,0]),'rm':unit('red','melee',[50,0])},
        policies={'blue':[dict(id='wait',commands=[dict(at_s=0,kind='wait')]),dict(id='hit',commands=[dict(at_s=0,kind='attack',target='rm')])],
                  'red':[dict(id='wait',commands=[dict(at_s=0,kind='wait')])]},in_progress_actions=[],committed_attacks=[])
    spec['units']['rm']['hp']=30
    return spec


def skill(effect='damage'):
    return dict(delivery='targeted',range_mode='center_to_center',commit='start',interruptible_by_move=False,
        effect=effect,rank=1,cast_s=.1,cooldown_s=3,cost=10,range=200,missile_speed=0,ready_in_s=0,
        damage=damage(),amount=25,duration_s=.5)


class ShortHorizon(unittest.TestCase):
    def test_gold_xp_and_unsettled_resources_are_separate(self):
        result=compare(task());wait,hit=result['branches']
        self.assertEqual(wait['metrics']['blue']['gold_gain'],0)
        self.assertEqual(wait['metrics']['blue']['pending_enemy_gold'],10)
        self.assertEqual(hit['metrics']['blue']['gold_gain'],10)
        self.assertEqual(hit['metrics']['blue']['xp_gain'],20)
        self.assertNotIn('winner',result)

    def test_minion_kill_grants_xp_without_cs(self):
        s=task();s['units']['bm']=unit('blue','melee',[0,0]);s['units']['bm']['locked_target']='rm'
        result=compare(s)
        self.assertEqual(result['branches'][0]['metrics']['blue']['gold_gain'],0)
        self.assertEqual(result['branches'][0]['metrics']['blue']['xp_gain'],20)
        self.assertAlmostEqual(result['effective_horizon_s'],.1)

    def test_locked_target_movement_stops_before_guessing_minion_pursuit(self):
        s=task();s['units']['rm']['locked_target']='bh'
        s['policies']['blue'][1]['commands']=[dict(at_s=.2,kind='move',to=[-10,0])]
        r=compare(s)
        self.assertAlmostEqual(r['effective_horizon_s'],.2)
        self.assertTrue(any('pursuit' in reason['reason'] for reason in r['replan_reasons']))

    def test_upgrade_truncates_every_branch_at_same_time(self):
        s=task();s['units']['bh']['next_level_xp']=20
        result=compare(s)
        self.assertAlmostEqual(result['effective_horizon_s'],.1)
        self.assertTrue(all(abs(r['end_s']-.1)<1e-9 for r in result['branches']))
        self.assertTrue(any('level_up' in r['reason'] for r in result['replan_reasons']))

    def test_windup_and_attack_frequency_are_enforced(self):
        s=task();s['units']['rm']['hp']=100
        s['policies']['blue'][1]['commands'].append(dict(at_s=.2,kind='attack',target='rm'))
        result=compare(s)['branches'][1]
        self.assertFalse(result['legal'])
        self.assertEqual(sum(e['kind']=='damage' for e in result['events']),1)
        self.assertEqual(next(e for e in result['events'] if e['kind']=='damage')['t_s'],.1)

    def test_move_cancels_windup_without_spending_attack_cooldown(self):
        s=task();s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='attack',target='rm'),dict(at_s=.05,kind='move',to=[1,0]),dict(at_s=.2,kind='attack',target='rm')]
        r=compare(s)['branches'][1]
        self.assertTrue(r['legal'])
        hits=[e for e in r['events'] if e['kind']=='damage']
        self.assertEqual(len(hits),1);self.assertAlmostEqual(hits[0]['t_s'],.3)

    def test_range_armor_shield_and_mana_rules(self):
        s=task();s['units']['rm'].update(armor=100,hp=100,shields=[dict(type='all',amount=10,remaining_s=1)])
        r=compare(s)['branches'][1]
        self.assertEqual(r['terminal_units']['rm']['hp'],85)
        s['units']['rm']['position']=[500,0]
        self.assertFalse(compare(s)['branches'][1]['legal'])
        s=task();s['units']['bh']['skills']['S']=skill();s['units']['bh']['mana']=5
        s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='cast',skill='S',target='rm')]
        r=compare(s)['branches'][1]
        self.assertFalse(r['legal']);self.assertEqual(r['metrics']['blue']['mana_spent'],0)

    def test_cast_cost_cooldown_and_not_learned_skill(self):
        s=task();s['units']['bh']['skills']['S']=skill();s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='cast',skill='S',target='rm')]
        r=compare(s)['branches'][1]
        self.assertEqual(r['metrics']['blue']['mana_spent'],10)
        self.assertEqual(r['metrics']['blue']['cooldown_remaining_s'],2)
        s['units']['bh']['skills']['S']['rank']=0
        self.assertFalse(compare(s)['branches'][1]['legal'])

    def test_target_kind_damage_does_not_leak_to_other_targets(self):
        s=task();s['units']['rm']['hp']=100
        s['units']['bh']['attack']['damage']=dict(damage(1),by_target_kind={'melee':damage(15)})
        r=compare(s)['branches'][1]
        self.assertEqual(r['terminal_units']['rm']['hp'],85)
        s['units']['rh']['position']=[50,0];s['policies']['blue'][1]['commands'][0]['target']='rh'
        self.assertEqual(compare(s)['branches'][1]['metrics']['red']['hp_damage'],1)

    def test_in_progress_windup_is_not_lost_at_entry(self):
        s=task();s['units']['bh']['phase']='windup'
        s['in_progress_actions']=[dict(actor='bh',target='rm',kind='attack',release_in_s=.05,started_ago_s=.05)]
        s['policies']['blue']=[dict(id='continue',commands=[dict(at_s=0,kind='wait')])]
        r=compare(s)['branches'][0]
        self.assertEqual(r['metrics']['blue']['gold_gain'],10)
        self.assertAlmostEqual(next(e['t_s'] for e in r['events'] if e['kind']=='damage'),.05)

    def test_projectile_and_pending_event_survive_short_horizon(self):
        s=task();s['horizon_s']=.2;s['units']['bh']['attack']['missile_speed']=10
        result=compare(s)['branches'][1]
        self.assertEqual(result['metrics']['blue']['gold_gain'],0)
        self.assertTrue(any(e['kind']=='projectile' for e in result['pending_events']))
        self.assertEqual(result['terminal_units']['rm']['hp'],30)

    def test_aggro_and_unsupported_effects_do_not_silently_continue(self):
        s=task();s['rules']['aggro_triggers']=[dict(action='attack',target_kind='minion',radius=200)]
        result=compare(s)
        self.assertEqual(result['effective_horizon_s'],0)
        self.assertTrue(any('aggro' in r['reason'] for r in result['replan_reasons']))
        s=task();s['units']['bh']['effects_inactive_verified']=False
        with self.assertRaises(ValueError):compare(s)
        s=task();s['rules']['geometry']='health_bar_pixels'
        with self.assertRaises(ValueError):compare(s)

    def test_explicit_boundary_prevents_unknown_future_skill_effects(self):
        s=task();s['rules'].update(valid_until_s=.08,boundary_reason='stateful effect may activate')
        r=compare(s)
        self.assertAlmostEqual(r['effective_horizon_s'],.08)
        self.assertEqual(r['branches'][1]['metrics']['blue']['gold_gain'],0)

    def test_disabled_option_needs_no_inputs_or_solvers(self):
        self.assertEqual(run_task(dict(enabled=False))['status'],'disabled')

    def test_compare_cli_without_site_packages(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'task.json';path.write_text(json.dumps(task()),encoding='utf-8')
            output=subprocess.check_output([sys.executable,'-S',str(root/'main.py'),'game-run',directory,'--task',str(path)])
            self.assertEqual(json.loads(output)['status'],'conditional_finite_window_comparison')

    def test_solver_is_optional_and_requires_declared_utility(self):
        s=task();self.assertNotIn('solver',run_task(s))
        if not importlib.util.find_spec('scipy'):self.skipTest('optional SciPy missing')
        s['backend']='zero_sum'
        with self.assertRaises(ValueError):run_task(s)
        s['utility']=dict(reference='test objective',valid_for_entry_time_s=60,valid_for_horizon_s=1,terminal_scope_note='synthetic finite window only',
            blue=dict(weights=dict(gold_gain=1,mana_spent=-1),scales=dict(gold_gain=10,mana_spent=100)),
            red=dict(weights=dict(gold_gain=1),scales=dict(gold_gain=10)))
        s['relative_resource_proxy']=True
        r=run_task(s)
        self.assertAlmostEqual(r['solver']['row_policy'][1],1)
        self.assertIn('not victory',r['solver_scope'])

    def test_terminal_assumption_can_change_local_preference_without_changing_accounts(self):
        s=task();s.update(backend='zero_sum',relative_resource_proxy=True)
        if not importlib.util.find_spec('scipy'):self.skipTest('optional SciPy missing')
        s['utility']=dict(reference='test',valid_for_entry_time_s=60,valid_for_horizon_s=1,terminal_scope_note='external future state assumption',
            blue=dict(weights=dict(gold_gain=1),scales=dict(gold_gain=10)),
            red=dict(weights=dict(gold_gain=1),scales=dict(gold_gain=10)))
        s['terminal_values']={'["wait","wait"]':dict(blue=2,red=0,reason='synthetic deferred opportunity')}
        r=run_task(s)
        self.assertAlmostEqual(r['solver']['row_policy'][0],1)
        self.assertEqual(r['branches'][0]['metrics']['blue']['gold_gain'],0)

    def test_general_sum_backend_keeps_both_utilities(self):
        if not importlib.util.find_spec('nashpy'):self.skipTest('optional Nashpy missing')
        s=task();s['backend']='general_sum'
        s['utility']=dict(reference='synthetic independent utilities',valid_for_entry_time_s=60,valid_for_horizon_s=1,terminal_scope_note='finite fixture',
            blue=dict(weights=dict(gold_gain=1),scales=dict(gold_gain=10)),
            red=dict(weights=dict(hp_end=1),scales=dict(hp_end=100)))
        result=run_task(s)
        self.assertEqual(result['utility_matrices']['red'],[[1],[1]])
        self.assertTrue(result['solver']['equilibria'])

    def test_utility_from_another_horizon_is_rejected(self):
        if not importlib.util.find_spec('scipy'):self.skipTest('optional SciPy missing')
        s=task();s['backend']='zero_sum';s['utility']=dict(reference='old context',terminal_scope_note='old',valid_for_entry_time_s=60,valid_for_horizon_s=30)
        with self.assertRaisesRegex(ValueError,'effective window'):run_task(s)

    def test_draft_has_no_champion_data_or_implied_pixel_ground_transform(self):
        p=dict(frames=[dict(id='f1',source_time_s=5,image='frames/1.jpg')],units=[dict(id='h1',side='blue',kind='hero')])
        d=draft(p,dict(frames={'f1':dict(units={'h1':dict(center=[189,350])})}),'f1')
        self.assertEqual(d['units']['h1']['position'],[None,None]);self.assertFalse(d['enabled'])
        self.assertIsNone(d['units']['h1']['attack']['range'])

    def test_save_is_reproducible_and_has_events(self):
        with tempfile.TemporaryDirectory() as directory:
            first=save_run(directory,task());second=save_run(directory,task())
            self.assertEqual(first['result']['branches'],second['result']['branches'])
            self.assertTrue((Path(directory)/'game_analysis'/first['folder']/'task.json').is_file())


if __name__=='__main__':unittest.main()
