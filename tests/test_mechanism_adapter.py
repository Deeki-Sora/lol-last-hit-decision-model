import unittest
from algorithms.mechanism_adapter import apply_event,evaluate_expression,validate_profile


def profile(verified=True):
    return dict(schema_version=1,id='generic',patch='16.6.1',source='synthetic',verified=verified,allow_simulation=verified,
        states={'stacks':0},triggers=[dict(id='on_hit',event='spell_hit',conditions=[dict(field='stacks',op='lt',value=3)],
            effects=[dict(kind='counter',state='stacks',value='1'),dict(kind='damage',target='enemy',amount='base_damage+stacks')])])


class MechanismAdapter(unittest.TestCase):
    def test_safe_formula_and_generic_counter_transition(self):
        self.assertEqual(evaluate_expression('base_damage * 0.5 + stacks',dict(base_damage=100,stacks=2)),52)
        result=apply_event(profile(),{'stacks':2},{'type':'spell_hit'},{'base_damage':100})
        self.assertEqual(result['state']['stacks'],3);self.assertEqual(result['applied'][0]['amount'],102)
        self.assertEqual(result['missing'],[])

    def test_unknown_effect_stays_a_missing_transition(self):
        result=apply_event(profile(),{'stacks':3},{'type':'spell_hit'},{'base_damage':100})
        self.assertEqual(result['applied'],[])
        self.assertFalse(result['missing'])
        bad=profile(False);bad['allow_simulation']=True
        with self.assertRaises(ValueError):validate_profile(bad)


if __name__=='__main__':unittest.main()
