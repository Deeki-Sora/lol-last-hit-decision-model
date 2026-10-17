"""Version isolation, legal selections and absence of future-state leakage."""
from pathlib import Path
import copy
import tempfile
import unittest
from unittest.mock import patch
from workbench.core import read_json, write_json, export_assessment
from workbench.catalog import catalog_path, resolve_version
from workbench.loadouts import rune_page, rune_counter_spec, validate_state, save_configuration, configuration_at, base_growth_reference
from workbench.name_aliases import CHAMPION_ALIASES
from workbench.game_tools import draft
from workbench.external_selectors import aramonly_preview


def fixture(directory):
    paths = [dict(id=n, names={'en_US': 'Path '+str(n), 'zh_CN': '路径'+str(n)},
        slots=[[n+1,n+2], [n+3,n+4], [n+5,n+6], [n+7,n+8]]) for n in (100, 200)]
    runes={str(i):dict(id=i,names={'en_US':'Rune '+str(i),'zh_CN':'符文'+str(i)},descriptions={'en_US':'Description','zh_CN':'说明'})
        for p in paths for row in p['slots'] for i in row}
    def item(ident,trinket=False):return dict(id=ident,names={'en_US':'Item '+ident,'zh_CN':'装备'+ident},
        descriptions={'en_US':'Item description','zh_CN':'装备说明'},maps={'11':True},tags=['Trinket'] if trinket else [],stacks=5 if ident=='3' else 1,stats={'FlatHPPoolMod':80})
    stats=dict(hp=600,hpperlevel=100,attackdamage=60,attackdamageperlevel=3,attackspeed=.7,attackspeedperlevel=3,attackrange=175,movespeed=340)
    champions={ident:dict(id=ident,key=str(i),names={'en_US':ident,'zh_CN':'英雄'+str(i)},stats=stats)
        for i,ident in enumerate(('Alpha','Beta'),1)}
    catalog=dict(schema_version=1,version='16.6.1',champions=champions,items={i:item(i,i=='9') for i in ['1','2','3','9']},
        rune_paths=paths,runes=runes,shard_slots=[[5005],[5008],[5001]],shards={str(i):dict(id=i,names={'en_US':str(i),'zh_CN':str(i)}) for i in [5005,5008,5001]},sources={},warnings=[])
    destination=catalog_path(directory,'16.6.1');destination.parent.mkdir(parents=True);write_json(destination,catalog)
    for ident in champions:
        raw=dict(name=ident,title='test',stats=stats,passive={'name':'Passive','description':'Test'},
            spells=[dict(id=k,name=k,maxrank=5,range=[400]*5,cooldown=[5]*5,cost=[10]*5) for k in ['Q','W','E','R']])
        write_json(destination.parent/f'champion_{ident}.json',dict(id=ident,version='16.6.1',locales={'en_US':raw},sources={}))
        write_json(destination.parent/f'native_{ident}.json',dict(schema_version=2,version='16.6.1',source={'url':'synthetic-test'},base_stats={},adaptive_default='ad',character={'attackSpeedRatioModifiable':{'baseValue':.6}}))
    page=dict(primary_path=100,secondary_path=200,primary=[101,103,105,107],secondary=[203,205],shards=[5005,5008,5001])
    setup=dict(patch='16.6.1',sides={side:dict(champion=champ,rune_page=copy.deepcopy(page)) for side,champ in [('blue','Alpha'),('red','Beta')]})
    def snapshot(time,ident):return dict(source_time_s=time,sides={side:dict(level=1 if time==0 else 2,
        spell_ranks=dict(Q=1,W=0,E=0,R=0),inventory_known=True,items=[dict(slot=0,id=ident,quantity=1)]) for side in ['blue','red']})
    config=dict(schema_version=1,match_setup=setup,snapshots=[snapshot(0,'1'),snapshot(.6,'2')])
    return catalog,config


class Loadouts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        self.catalog,self.config=fixture(self.directory)
        self.project=dict(schema_version=1,start_s=0,end_s=1,step_s=.3,source_name='synthetic.mp4',source_sha256='test',
            units=[dict(id=side+'_hero',side=side,kind='hero') for side in ['blue','red']],
            frames=[dict(id='f0',source_time_s=0,image='frames/test.jpg'),dict(id='f1',source_time_s=.6,image='frames/test.jpg')],hero_data={})
        (self.directory/'frames').mkdir();(self.directory/'frames/test.jpg').write_bytes(b'test')
        write_json(self.directory/'project.json',self.project);write_json(self.directory/'annotations.json',dict(schema_version=1,frames={}))

    def tearDown(self):self.temp.cleanup()

    def save(self):return save_configuration(self.directory,dict(configuration=self.config,source_time_s=0))

    def test_2026_patch_label_resolves_only_matching_patch(self):
        self.assertEqual(resolve_version('26.6',['16.6.1','16.6.2','16.7.1']),'16.6.2')
        with self.assertRaises(ValueError):resolve_version('26.8',['16.7.1'])
        with self.assertRaises(ValueError):resolve_version('latest',['16.7.1'])

    def test_invalid_rune_rows_and_inventory_are_rejected(self):
        page=copy.deepcopy(self.config['match_setup']['sides']['blue']['rune_page']);page['secondary']=[203,204]
        with self.assertRaisesRegex(ValueError,'different rows'):rune_page(page,self.catalog)
        with self.assertRaises(ValueError):validate_state({'items':[dict(id='9',slot=0)]},self.catalog)
        with self.assertRaises(ValueError):validate_state({'items':[dict(id='1',slot=0),dict(id='2',slot=0)]},self.catalog)
        with self.assertRaises(ValueError):validate_state({'level':True},self.catalog)

    def test_alias_table_and_rune_counter_constraints(self):
        self.assertIn('大头', CHAMPION_ALIASES['Heimerdinger'])
        self.assertEqual(rune_counter_spec('101', self.catalog), ('stack', None))
        self.catalog['runes']['8473'] = dict(id=8473, names={'en_US':'Bone Plating','zh_CN':'骸骨镀层'})
        with self.assertRaisesRegex(ValueError, 'binary rune state'):
            validate_state({'event_state': {'rune_stacks': {'8473': 2}}}, self.catalog)
        self.assertEqual(validate_state({'event_state': {'rune_stacks': {'8473': 1}}}, self.catalog)['event_state']['rune_stacks']['8473'], 1)

    def test_future_inventory_never_flows_backwards_or_into_draft(self):
        self.save();p=read_json(self.directory/'project.json')
        before=configuration_at(self.directory,p,0)['blue'];after=configuration_at(self.directory,p,.7)['blue']
        self.assertEqual(before['items'][0]['id'],'1');self.assertEqual(after['items'][0]['id'],'2')
        self.assertFalse(before['verified_effective_state']);self.assertEqual(before['spells']['Q']['rank_reference']['cooldown'],5)
        task=draft(p,{'frames':{}},'f0',self.directory)
        self.assertEqual(task['observations']['selected_hero_references']['blue']['items'][0]['id'],'1')
        self.assertNotIn('snapshots',task['observations']['match_configuration'])
        self.assertEqual(task['rules']['patch'],'16.6.1');self.assertFalse(task['rules']['verified'])
        p['configuration']['snapshots']=p['configuration']['snapshots'][1:]
        early=configuration_at(self.directory,p,0)['blue']
        self.assertIsNone(early['effective_state']['level']);self.assertFalse(early['effective_state']['inventory_known'])

    def test_fixed_config_changes_require_unlock_and_new_hero_clears_old_state(self):
        self.save();self.config['match_setup']['sides']['blue']['champion']='Beta'
        with self.assertRaisesRegex(ValueError,'unlock'):self.save()
        with self.assertRaisesRegex(ValueError,'clearing old snapshots'):save_configuration(self.directory,dict(configuration=self.config,replace_fixed_setup=True))
        self.config['snapshots']=[]
        save_configuration(self.directory,dict(configuration=self.config,replace_fixed_setup=True))

    def test_bundle_contains_offline_data_and_separate_timed_states(self):
        self.save()
        with patch('workbench.catalog.download',side_effect=AssertionError('must stay offline')):
            export_assessment(self.directory)
        self.assertTrue((self.directory/'assessment/configuration.json').exists())
        states=read_json(self.directory/'assessment/hero_states.json')
        self.assertEqual([s['sides']['blue']['items'][0]['id'] for s in states],['1','2'])
        self.assertEqual(read_json(self.directory/'assessment/hero_data.json')['blue']['items'][0]['id'],'1')

    def test_reference_growth_uses_level_minus_one_and_never_claims_effective_as(self):
        ref=base_growth_reference(dict(hp=600,hpperlevel=100,attackspeed=.7,attackspeedperlevel=3),2)
        self.assertAlmostEqual(ref['values']['hp'],672)
        self.assertAlmostEqual(ref['values']['attack_speed_growth_percent'],2.16)
        self.assertNotIn('attack_speed',ref['values']);self.assertFalse(ref['verified'])

    def test_optional_aramonly_import_preserves_champion_and_decodes_external_rows(self):
        schema=dict(patch='26.10',source={'url':'synthetic schema','sha256':'test'},trees=[
            dict(name=p['names']['en_US'],rows=[[self.catalog['runes'][str(i)]['names']['en_US'] for i in ids] for ids in p['slots']])
            for p in self.catalog['rune_paths']])
        schema['trees'].append(dict(name='Passive',rows=[[str(i) for i in row] for row in self.catalog['shard_slots']]))
        write_json(self.directory/'catalogs/aramonly_schema.json',schema)
        url='https://www.aramonly.com/lol-runes-builder/?champion=unknown-future-hero&runes=01000-11121-000&items=1,3'
        result=aramonly_preview(self.directory,url,'16.6.1')
        self.assertTrue(result['champion_ignored']);self.assertEqual(result['rune_page']['primary'],[102,103,105,107])
        self.assertEqual(result['rune_page']['secondary'],[204,206])
        self.assertEqual([i['id'] for i in result['items']],['1','3'])
        self.assertFalse(result['inventory_complete']);self.assertEqual(result['provider_patch'],'26.10')
        self.assertEqual(result['target_patch'],'16.6.1')
        with self.assertRaises(ValueError):aramonly_preview(self.directory,'https://example.com/?items=1','16.6.1')


if __name__=='__main__':unittest.main()
