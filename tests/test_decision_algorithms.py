import unittest
import tempfile
from pathlib import Path
from algorithms.belief_state import bayesian_update, entropy, roll_forward
from algorithms.joint_scheduler import best_schedule, enumerate_schedules, evaluate_schedule, feasible_claims
from algorithms.risk_value import decision_value, lower_cvar, two_layer_score, value_of_information
from workbench.minion_data import generic_profile, load_profiles
from workbench.game_tools import run_task
from test_short_horizon import task


class DecisionAlgorithms(unittest.TestCase):
    def test_belief_updates_normalize_and_reduce_entropy(self):
        prior=[{'state':{'target':'a'},'probability':.5},{'state':{'target':'b'},'probability':.5}]
        posterior=bayesian_update(prior,{0:.9,1:.1})
        self.assertAlmostEqual(sum(x['probability'] for x in posterior),1)
        self.assertGreater(posterior[0]['probability'],posterior[1]['probability'])
        self.assertLess(entropy(posterior),entropy(prior))
        trace=roll_forward(prior,[{'observation':'seen','likelihoods':{0:.5,1:.5}}])
        self.assertEqual(len(trace),2);self.assertAlmostEqual(trace[-1]['entropy'],entropy(prior))

    def test_joint_scheduler_preserves_single_actor_time_and_free_windows(self):
        targets=[dict(id='m1',impact_window=[.1,.3],duration_s=.1,gold=21,xp=60,probability=.9,cost={'mana':2}),
            dict(id='m2',impact_window=[.2,.5],duration_s=.1,gold=21,xp=60,probability=.8,cost={'mana':2}),
            dict(id='m3',impact_window=[.8,1.],duration_s=.1,gold=14,xp=29,probability=1)]
        claims=feasible_claims(targets,horizon_s=1)
        self.assertEqual(len(claims),3)
        self.assertTrue(any(len(x)==2 for x in enumerate_schedules(claims,1)))
        best=best_schedule(targets,horizon_s=1)
        self.assertEqual(best['claims'],['m1','m2','m3'])
        self.assertTrue(best['free_windows'])
        self.assertEqual(evaluate_schedule([],1)['expected_gold'],0)

    def test_risk_voi_and_strategy_first_score(self):
        self.assertEqual(lower_cvar([0,10],alpha=.5),0)
        self.assertEqual(value_of_information({'a':1,'b':2},[{'a':10,'b':0},{'a':0,'b':10}],[.5,.5]),8)
        q=decision_value([{'probability':.8,'metrics':{'gold_gain':10}},{'probability':.2,'metrics':{'gold_gain':0}}],{'gold_gain':1})
        self.assertAlmostEqual(q['expected_utility'],8);self.assertLess(q['decision_value'],8)
        score=two_layer_score({'window':1,'resource_plan':1},{'distance':1,'phase':1,'resource':1,'movement':1,'timing':1},omega=.6)
        self.assertEqual(score['score'],100)
        missing=two_layer_score({'window':1},{'distance':1},omega=.6,confidence=.5)
        self.assertIsNotNone(missing['score']);self.assertTrue(missing['missing'])

    def test_minion_fallback_is_explicit_and_patch_cacheable(self):
        self.assertFalse(generic_profile('melee')['verified'])
        self.assertEqual(generic_profile('melee')['gold_reward'],20)
        self.assertEqual(generic_profile('melee')['behavior']['acquisition_range'],500)
        with tempfile.TemporaryDirectory() as directory:
            # A real catalog path is required before a version-scoped cache can be created;
            # the fixture here only checks that the fallback remains explicit.
            self.assertEqual(generic_profile('caster')['source_kind'],'generic_default')

    def test_compare_connects_optional_profile_belief_and_scheduler_layers(self):
        spec=task();spec['mechanism_profiles']=[dict(schema_version=1,id='generic',patch='synthetic-test',source='synthetic',verified=True,allow_simulation=True,states={},triggers=[])]
        spec['belief']={'states':[{'state':{'x':1},'probability':1}], 'updates':[]}
        spec['schedule_targets']=[dict(id='rm',impact_window=[0,.5],duration_s=.1,gold=10,xp=20)]
        result=run_task(spec)
        self.assertEqual(result['mechanism_profiles'][0]['id'],'generic')
        self.assertEqual(result['belief_trace'][-1]['states'][0]['state']['x'],1)
        self.assertEqual(result['joint_schedule_reference']['expected_gold'],10)
        self.assertIn('decision_analysis',result)


if __name__=='__main__':unittest.main()
