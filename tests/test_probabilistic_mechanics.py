import csv
import io
import unittest
from copy import deepcopy
from test_short_horizon import task,skill,damage,unit
from algorithms.short_horizon import compare
from workbench.mechanic_observations import FIELDS,estimate


def stochastic(spec,samples=32):
    spec['stochastic']=dict(samples=samples,seed=47,models=[],effects=[])
    return spec['stochastic']


def joint_model(probability=.5):
    return dict(id='joint',kind='joint_hits',sampling='fixed',context_verified=True,context_note='synthetic fixed context',source='synthetic',
        distance_interval=[0,200],target_motion='any',outcomes=[dict(id='miss',hits=[],probability=1-probability),dict(id='hit',hits=['rm'],probability=probability)])


def effect(actor='bh',trigger='attack_hit',kind='damage'):
    return dict(id='proc',actor=actor,trigger=trigger,verified=True,source='synthetic',ready_in_s=0,cooldown_s=10,
        counter=dict(threshold=3,window_s=3,unique_casts=True,initial_hits=[]),probability_model=None,
        effect=dict(kind=kind,target='event_target',damage=damage(10),amount=20,duration_s=.5))


class Probabilities(unittest.TestCase):
    def test_joint_hit_miss_consumes_mana_even_when_every_shot_misses(self):
        s=task();data=stochastic(s);data['models']=[joint_model(0)]
        s['units']['bh']['skills']['S']=dict(skill(),delivery='skillshot_probability',outcome_model='joint',collateral_scope_verified=True,impact_delay_s=.1,max_hits=1)
        s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='cast',skill='S',target='rm')]
        r=compare(s)['branches'][1]
        self.assertEqual(r['metrics']['blue']['gold_gain'],0)
        self.assertEqual(r['metrics']['blue']['mana_spent'],10)
        self.assertEqual(r['metrics']['blue']['cooldown_remaining_s'],2)

    def test_reproducible_paired_scenarios_and_not_confidence_intervals(self):
        s=task();data=stochastic(s);data['models']=[joint_model()]
        s['units']['bh']['skills']['S']=dict(skill(),delivery='skillshot_probability',outcome_model='joint',collateral_scope_verified=True,impact_delay_s=.1,max_hits=1)
        s['policies']['blue']=[dict(id=name,commands=[dict(at_s=0,kind='cast',skill='S',target='rm')]) for name in ('a','b')]
        first=compare(s);second=compare(s)
        self.assertEqual(first,second)
        a,b=first['branches'];self.assertEqual(a['scenario_results'],b['scenario_results'])
        self.assertGreater(a['metrics']['blue']['gold_gain'],0);self.assertLess(a['metrics']['blue']['gold_gain'],10)
        self.assertEqual(a['metric_scenario_ranges']['blue']['gold_gain']['max'],10)
        self.assertIn('not calibrated',first['probability_note'])

    def test_deterministic_proc_counter_and_initial_cooldown(self):
        s=task();s['horizon_s']=3;s['units']['bh']['attack']['damage']=damage(1)
        data=stochastic(s,1);data['effects']=[effect()]
        s['policies']['blue'][1]['commands']=[dict(at_s=t,kind='attack',target='rm') for t in (0,1,2)]
        r=compare(s)['branches'][1]
        self.assertEqual(sum(e['kind']=='effect_applied' for e in r['events']),1)
        self.assertEqual(r['terminal_units']['rm']['hp'],17)
        data['effects'][0]['ready_in_s']=5
        self.assertFalse(any(e['kind']=='effect_applied' for e in compare(s)['branches'][1]['events']))

    def test_unknown_initial_counter_is_a_state_distribution(self):
        s=task();data=stochastic(s);e=effect();data['effects']=[e]
        e['initial_state_scenarios']=[dict(probability=.5,ready_in_s=0,initial_hits=[]),
            dict(probability=.5,ready_in_s=0,initial_hits=[dict(age_s=.3,instance='old1'),dict(age_s=.2,instance='old2')])]
        s['units']['bh']['attack']['damage']=damage(1)
        r=compare(s)['branches'][1]
        activations=[any(e['kind']=='effect_applied' for e in scenario['events']) for scenario in r['scenario_results']]
        self.assertTrue(any(activations));self.assertFalse(all(activations))

    def test_pre_damage_shield_is_applied_before_hp_damage(self):
        s=task();data=stochastic(s,1);e=effect('rh','before_damage','shield');e['counter']['threshold']=1;e['effect']['target']='self';data['effects']=[e]
        s['units']['rh']['position']=[50,0]
        s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='attack',target='rh')]
        r=compare(s)['branches'][1]
        self.assertEqual(r['metrics']['red']['hp_damage'],30)

    def test_resource_stack_invalidates_dependent_skill_profiles(self):
        s=task();data=stochastic(s,1);e=effect(kind='bank_resource');e['counter']['threshold']=1
        e['effect'].update(target='self',resource='growth',amount=1,invalidates_labels=['S']);data['effects']=[e]
        s['units']['bh']['attack']['damage']=damage(1);s['units']['bh']['skills']['S']=skill()
        s['policies']['blue'][1]['commands'].append(dict(at_s=.2,kind='cast',skill='S',target='rm'))
        r=compare(s)
        self.assertAlmostEqual(r['effective_horizon_s'],.2)
        self.assertTrue(any('updated_combat_profile' in x['reason'] for x in r['replan_reasons']))
        self.assertEqual(r['branches'][1]['metrics']['blue']['resource:growth'],1)

    def test_joint_model_applies_collateral_and_penetration_caps(self):
        s=task();data=stochastic(s,1);m=joint_model(1)
        s['units']['rm2']=unit('red','caster',[60,0]);s['units']['rm2']['hp']=30
        m['outcomes'][1]['hits']=['rm','rm2'];data['models']=[m]
        s['units']['bh']['skills']['S']=dict(skill(),delivery='skillshot_probability',outcome_model='joint',collateral_scope_verified=True,impact_delay_s=.1,max_hits=2)
        s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='cast',skill='S',target='rm')]
        self.assertEqual(compare(s)['branches'][1]['metrics']['blue']['gold_gain'],20)
        s['units']['bh']['skills']['S']['max_hits']=1
        with self.assertRaises(ValueError):compare(s)

    def test_probability_does_not_override_eligibility_and_context(self):
        s=task();data=stochastic(s,1);m=joint_model();m['distance_interval']=[0,10];data['models']=[m]
        s['units']['bh']['skills']['S']=dict(skill(),delivery='skillshot_probability',outcome_model='joint',collateral_scope_verified=True,impact_delay_s=.1,max_hits=1)
        s['policies']['blue'][1]['commands']=[dict(at_s=0,kind='cast',skill='S',target='rm')]
        self.assertAlmostEqual(compare(s)['effective_horizon_s'],.1)
        m['context_verified']=False
        with self.assertRaises(ValueError):compare(s)

    def test_conditional_proc_probability_and_explicit_posterior(self):
        s=task();data=stochastic(s);e=effect();e['counter']['threshold']=1;e['probability_model']='binary';data['effects']=[e]
        s['units']['bh']['attack']['damage']=damage(1)
        data['models']=[dict(id='binary',kind='binary',sampling='posterior',eligible_trials=10,successes=4,prior_alpha=1,prior_beta=1,
            context_verified=True,context_note='synthetic conditional opportunity',source='test')]
        r=compare(s)['branches'][1]
        counts=[len([e for e in scenario['events'] if e['kind']=='effect_applied']) for scenario in r['scenario_results']]
        self.assertTrue(0<sum(counts)<len(counts))

    def test_joint_initial_states_preserve_mutually_exclusive_effects(self):
        s=task();data=stochastic(s);a=effect();b=effect();a['id']='a';b['id']='b'
        a['counter']['threshold']=b['counter']['threshold']=1
        data['effects']=[a,b];s['units']['bh']['attack']['damage']=damage(1)
        ready=dict(ready_in_s=0,initial_hits=[]);locked=dict(ready_in_s=10,initial_hits=[])
        data['initial_joint_states']=[dict(probability=.5,effects={'a':ready,'b':locked}),dict(probability=.5,effects={'a':locked,'b':ready})]
        r=compare(s)['branches'][1]
        self.assertTrue(all(sum(e['kind']=='effect_applied' for e in scenario['events'])==1 for scenario in r['scenario_results']))


class ObservationLedger(unittest.TestCase):
    def text(self,rows):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows);return stream.getvalue()

    def row(self,uid,success='true',eligible='true'):
        return dict(opportunity_id=uid,mechanism_id='rune',kind='binary',event_type='rune_activation',actor='bh',target='rh',
            source_time_s='5',eligible=eligible,success=success,outcome_id='',hit_unit_ids='',window_start_s='0',window_end_s='20',context='fixed level/range/movement',source='frame1')

    def test_distinct_opportunities_unknowns_and_rates(self):
        a=self.row('one');repeated=dict(a,source_time_s='5.3');b=self.row('two','false');c=self.row('three','')
        r=estimate(self.text([a,repeated,b,c]));m=r['models'][0];rate=r['observed_rates'][0]
        self.assertEqual(m['eligible_trials'],2);self.assertEqual(m['successes'],1)
        self.assertEqual(r['coverage']['unique_opportunities'],3)
        self.assertEqual(rate['success_rate'],.5);self.assertEqual(rate['observed_activations_per_minute'],3)
        self.assertTrue(rate['frequency_is_lower_bound']);self.assertFalse(m['context_verified'])

    def test_conflicts_and_different_contexts_are_rejected(self):
        with self.assertRaises(ValueError):estimate(self.text([self.row('one'),self.row('one','false')]))
        with self.assertRaises(ValueError):estimate(self.text([self.row('one'),dict(self.row('two'),context='different')]))


if __name__=='__main__':unittest.main()
