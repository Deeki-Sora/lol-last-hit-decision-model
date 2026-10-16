"""Common stat references, event freshness, and propagation into offline exports."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_loadouts import fixture
from workbench.catalog import catalog_path
from workbench.core import read_json, write_json, export_assessment
from workbench.game_tools import draft
from workbench.loadouts import save_configuration, validate_state
from workbench.native_data import character_attributes
from workbench.parameters import evaluate_project, direct_range_reference
from workbench.stat_arithmetic import item_components, subtotal, ordinary_attack_speed_cap


class EventParameters(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        self.catalog,self.config=fixture(self.directory)
        for ident in ('Alpha','Beta'):
            path=catalog_path(self.directory,'16.6.1').parent/f'champion_{ident}.json'
            data=read_json(path);data['locales']['en_US'].update(partype='Mana')
            data['locales']['en_US']['stats'].update(hpregen=8,mp=300,mpperlevel=20,mpregen=6,armor=30,spellblock=32)
            write_json(path,data)
        self.catalog['shards']['5005']['descriptions']={'en_US':'+10% Attack Speed'}
        self.catalog['shards']['5008']['descriptions']={'en_US':'+9 Adaptive Force'}
        self.catalog['shards']['5001']['descriptions']={'en_US':'+10-180 Health (based on level)'}
        self.catalog['items']['1']['stats'].update(FlatPhysicalDamageMod=10,FlatHPRegenMod=.8)
        self.catalog['items']['1']['descriptions']['en_US']='<stats>80 Health<br>10 Attack Damage<br>10 Ability Haste<br>10 Lethality<br>2.5% Omnivamp</stats><br>Passive: 50 Ability Haste'
        write_json(catalog_path(self.directory,'16.6.1'),self.catalog)
        self.project=dict(schema_version=1,start_s=0,end_s=1,step_s=.3,source_name='synthetic.mp4',source_sha256='test',hero_data={},
            units=[dict(id=side+'_hero',side=side,kind='hero') for side in ('blue','red')],
            frames=[dict(id='f0',source_time_s=0,image='frames/test.jpg'),dict(id='f1',source_time_s=.6,image='frames/test.jpg')])
        (self.directory/'frames').mkdir();(self.directory/'frames/test.jpg').write_bytes(b'synthetic')
        write_json(self.directory/'project.json',self.project);write_json(self.directory/'annotations.json',dict(schema_version=1,frames={}))

    def tearDown(self):self.temp.cleanup()

    def save(self):
        save_configuration(self.directory,dict(configuration=self.config,source_time_s=0))
        self.project=read_json(self.directory/'project.json')

    def test_level_items_shards_and_native_growth_are_computed_without_passive_guessing(self):
        # A native growth field corrects a missing/zero growth value in another provider.
        path=catalog_path(self.directory,'16.6.1').parent/'native_Alpha.json'
        native=read_json(path);native['base_stats']={'attackdamageperlevel':4};write_json(path,native)
        self.config['snapshots'][1]['sides']['blue']['items'][0]['id']='1'
        self.save();data=evaluate_project(self.directory,self.project,.6)['sides']['blue'];s=data['stats']
        self.assertAlmostEqual(s['attack_damage']['value'],60+4*.72+10+5.4)
        self.assertAlmostEqual(s['max_hp']['value'],672+80+20)
        self.assertAlmostEqual(s['attack_speed']['value'],.7+.6*.1216)
        self.assertAlmostEqual(data['attack_period_s'],1/(.7+.6*.1216))
        self.assertAlmostEqual(s['health_regen']['value'],8/5+.8)
        self.assertEqual(s['ability_haste']['value'],10)  # Text outside <stats> is not a flat stat.
        self.assertAlmostEqual(s['cooldown_reduction']['value'],1/11)
        self.assertAlmostEqual(data['skills']['Q']['standard_haste_cooldown_reference_s'],5/1.1)
        self.assertAlmostEqual(s['omnivamp']['value'],.025)
        self.assertEqual(data['base_stat_differences']['attackdamageperlevel'],dict(data_dragon=3,native=4))
        self.assertIsNone(data['hp']);self.assertIsNone(data['decision_score'])

    def test_event_inputs_overrides_zero_and_stale_observations(self):
        state=self.config['snapshots'][0]['sides']['blue']
        state['event_state']=dict(hp=430,resource_value=0,passive_stacks=12345,shield_active=False,shield_amount=0,
            rune_stacks={'101':6},skills={'Q':dict(range=475,remaining_cooldown_s=0,damage=120,damage_type='magic',resource_cost=0)})
        state['stat_overrides']=dict(attack_damage=0,attack_speed=1.25,ability_haste=25,magic_penetration_flat=12)
        self.save();current=evaluate_project(self.directory,self.project,0)['sides']['blue']
        self.assertEqual(current['stats']['attack_damage']['value'],0)
        self.assertEqual(current['stats']['attack_damage']['source'],'user_override')
        self.assertEqual(current['passive_stacks'],12345);self.assertFalse(current['shield_active'])
        self.assertEqual(current['resource_value'],0);self.assertEqual(current['rune_stacks'],{'101':6})
        self.assertAlmostEqual(current['attack_period_s'],.8)
        self.assertAlmostEqual(current['skills']['Q']['standard_haste_cooldown_reference_s'],4)
        later=evaluate_project(self.directory,self.project,.3)['sides']['blue']
        self.assertIsNone(later['hp']);self.assertIsNone(later['resource_value']);self.assertEqual(later['rune_stacks'],{})
        self.assertIsNone(later['skills']['Q']['remaining_cooldown_s']['value'])
        self.assertEqual(later['skills']['Q']['range']['value'],400)
        self.assertGreater(later['stats']['attack_damage']['value'],0)
        self.assertFalse(later['event_inputs_are_current'])

    def test_damage_reference_uses_penetration_but_never_assigns_a_grade(self):
        state=self.config['snapshots'][0]['sides']['blue']
        state['event_state']=dict(skills={'Q':dict(range=600,remaining_cooldown_s=0,damage=120,damage_type='physical')})
        state['stat_overrides']=dict(armor_penetration_flat=10,armor_penetration_percent=.5)
        self.save();parameters=evaluate_project(self.directory,self.project,0)
        result=direct_range_reference(parameters,'blue','Q',450)
        self.assertAlmostEqual(result['resistance_after_penetration_reference'],5)
        self.assertAlmostEqual(result['damage_after_resistance_reference'],120/1.05)
        self.assertTrue(result['direct_range_reference']);self.assertTrue(result['skill_learned'])
        self.assertIsNone(result['overall_safety']);self.assertIsNone(result['decision_score'])
        unlearned=direct_range_reference(parameters,'blue','E',450)
        self.assertFalse(unlearned['skill_learned']);self.assertIsNone(unlearned['direct_range_reference'])

    def test_no_resource_unknowns_offline_export_and_optional_draft(self):
        for side in ('blue','red'):
            self.config['snapshots'][0]['sides'][side]['event_state']=dict(resource_type='none',hp=450)
        self.save()
        with patch('workbench.catalog.download',side_effect=AssertionError('offline')):
            data=evaluate_project(self.directory,self.project,0,fetch_native=True)
            export_assessment(self.directory)
        for side in ('blue','red'):
            self.assertIsNone(data['sides'][side]['stats']['max_resource']['value'])
            self.assertIsNone(data['sides'][side]['resource_value'])
        task=draft(self.project,{'frames':{}},'f0',self.directory)
        for side in ('blue','red'):
            unit=task['units'][side+'_hero'];self.assertEqual(unit['hp'],450)
            self.assertEqual(unit['max_hp'],690);self.assertEqual(unit['resource_model'],'none')
            self.assertAlmostEqual(unit['hp_regen_s'],2.4)
        self.assertFalse(task['enabled']);self.assertFalse(task['rules']['verified'])
        exported=read_json(self.directory/'assessment/event_parameters.json')
        self.assertEqual(len(exported),2);self.assertEqual(exported[0]['sides']['blue']['hp'],450)

    def test_bad_numbers_and_unknown_properties_are_rejected(self):
        for bad in [dict(event_state={'hp':True}),dict(event_state={'passive_stacks':-1}),
            dict(event_state={'skills':{'E':{'remaining_cooldown_s':float('nan')}}}),
            dict(stat_overrides={'magic_penetration_percent':40}),dict(stat_overrides={'cooldown_reduction':1}),
            dict(stat_overrides={'invented_stat':12}),dict(event_state={'rune_stacks':None}),dict(stat_overrides=[])]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_state(bad,self.catalog)

    def test_uncrosschecked_zero_growth_does_not_silently_become_a_level_two_estimate(self):
        path=catalog_path(self.directory,'16.6.1').parent/'champion_Alpha.json'
        raw=read_json(path);raw['locales']['en_US']['stats']['attackdamageperlevel']=0;write_json(path,raw)
        self.save();profile=evaluate_project(self.directory,self.project,.6)['sides']['blue']
        self.assertIsNone(profile['stats']['attack_damage']['value'])
        self.assertIn('zero_attack_damage_growth_requires_native_cross_check_or_effective_stat_override',profile['limitations'])


class CommonArithmetic(unittest.TestCase):
    def test_item_text_deduplicates_structured_stats_and_ignores_passive_text(self):
        values,unknown=item_components(dict(stats={'FlatPhysicalDamageMod':20},descriptions={'en_US':
            '<stats><attention>20</attention> Attack Damage<br>40% Armor Penetration<br>15 Magic Penetration<br>50% Base Health Regen</stats><br>Gain 100 Ability Power when attacking'}))
        self.assertEqual(values,dict(attack_damage=20,armor_penetration_percent=.4,magic_penetration_flat=15,base_health_regen_percent=.5))
        self.assertEqual(unknown,[])

    def test_independent_shards_regeneration_and_mixed_adaptive_choice(self):
        ref=dict(base_growth_reference={'values':dict(hp=600,hpregen=10,mpregen=5,move_speed=400,base_attack_speed=.7,attack_speed_growth_percent=0)},
            effective_state={'level':18},items=[dict(id='x',quantity=1,data=dict(stats={'FlatPhysicalDamageMod':10,'FlatMagicDamageMod':20},
                descriptions={'en_US':'<stats>50% Base Health Regen<br>30% Tenacity</stats>'}))],
            shards=[dict(id=i,descriptions={'en_US':text}) for i,text in [(5001,'+10-180 Health (based on level)'),
                (5007,'+8 Ability Haste'),(5010,'+2.5% Move Speed'),(5013,'+15% Tenacity and Slow Resist'),(5008,'+9 Adaptive Force')]])
        auto,trace,notes=subtotal(ref,{},{});self.assertEqual(auto['max_hp'],780)
        self.assertEqual(auto['health_regen'],3);self.assertEqual(auto['resource_regen'],1)
        self.assertAlmostEqual(auto['move_speed'],410);self.assertEqual(auto['ability_haste'],8)
        self.assertAlmostEqual(auto['tenacity'],1-.7*.85);self.assertAlmostEqual(auto['slow_resist'],.15)
        self.assertIn('mixed_ad_ap_equipment_select_adaptive_stat',notes)
        self.assertIsNone(auto['attack_damage']);self.assertIsNone(auto['ability_power'])
        ref['effective_state']['event_state']={'adaptive_stat':'ap'}
        auto,_,_=subtotal(ref,{},{});self.assertEqual(auto['ability_power'],29)

    def test_native_fields_are_general_and_regen_units_are_normalized(self):
        data=character_attributes(dict(mCharacterName='Any',baseDamageModifiable={'baseValue':60},
            damagePerLevelModifiable={'baseValue':2.5},baseStaticHPRegenModifiable={'baseValue':1.3}), '16.6.1',{'url':'synthetic'})
        self.assertEqual(data['base_stats'],dict(attackdamage=60,attackdamageperlevel=2.5,hpregen=6.5))
        self.assertEqual(data['adaptive_default'],'ad')

    def test_attack_speed_cap_follows_patch_baselines(self):
        self.assertEqual(ordinary_attack_speed_cap('15.2.1'),2.5)
        self.assertEqual(ordinary_attack_speed_cap('15.3.1'),3)
        self.assertEqual(ordinary_attack_speed_cap('16.6.1'),3)
        self.assertIsNone(ordinary_attack_speed_cap('17.1.1'))
        ref=dict(patch='16.6.1',effective_state={'level':1},base_growth_reference={'values':dict(base_attack_speed=.7,attack_speed_growth_percent=500)})
        auto,_,_=subtotal(ref,{'character':{'attackSpeedRatioModifiable':{'baseValue':.6}}},{})
        self.assertEqual(auto['attack_speed'],3)


if __name__=='__main__':unittest.main()
