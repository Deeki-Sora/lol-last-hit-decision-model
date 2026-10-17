from pathlib import Path
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from workbench.core import (sample,read_json,write_json,default_units,export_tables,
    export_assessment,calibration,default_calibration,validate_annotations,seconds)
from workbench.operations import import_csv,solve_matrix
from workbench.server import make_server


class Tables(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        (self.directory/'frames').mkdir()
        (self.directory/'frames/test.jpg').write_bytes(b'test-image')
        self.project=dict(schema_version=1,source_name='video.mp4',source_sha256='abc',
            start_s=0,end_s=1,step_s=.3,frames=[dict(id=f'f{i}',source_time_s=i*.3,image='frames/test.jpg') for i in range(3)],
            units=default_units(),calibration=calibration('189=350'),hero_data={'blue':{},'red':{}},strategy_text='')
        self.ann=dict(schema_version=1,frames={
            'f0':dict(origin=[0,0],units={'blue_hero':dict(center=[0,0],reviewed=True,action='attack',target='red_melee_w1_1',action_start_s=0),
                'red_hero':dict(center=[3,4],reviewed=True),'red_melee_w1_1':dict(center=[6,8])}),
            'f1':dict(origin=[10,0],units={'blue_hero':dict(center=[12,0],action='attack',target='red_melee_w1_1',action_start_s=.3),
                'red_hero':dict(center=[13,4]),'red_melee_w1_1':dict(alive=False)}),
            'f2':dict(units={'blue_hero':dict(center=[12,0]),'red_hero':dict(center=[15,4])})})
        write_json(self.directory/'project.json',self.project)
        write_json(self.directory/'annotations.json',self.ann)

    def tearDown(self):self.temp.cleanup()

    def test_default_calibration_is_editable_midpoint_of_local_range(self):
        value=default_calibration()
        self.assertAlmostEqual(value['pixels'], .459)
        self.assertEqual(value['pixel_per_game_unit_range'], [.453, .465])
        self.assertAlmostEqual(calibration('189=350')['units_per_pixel'], 350/189)

    def rows(self,name):
        return list(csv.DictReader((self.directory/'tables'/name).read_text(encoding='utf-8-sig').splitlines()))

    def test_pairs_have_sides_and_only_opposing_units(self):
        export_tables(self.directory)
        rows=self.rows('distances.csv')
        self.assertEqual([sum(x['frame_id']==f'f{i}' for x in rows) for i in range(3)],[13,12,12])
        for row in rows:
            self.assertNotEqual(row['first_side'],row['second_side'])
            self.assertEqual(row['first_kind'],'hero')
        row=next(r for r in rows if r['frame_id']=='f0' and r['second']=='red_hero')
        self.assertEqual(float(row['distance_px']),5)
        self.assertAlmostEqual(float(row['distance_game_units_estimate']),5*350/189)
        self.assertEqual(row['both_reviewed'],'True')

    def test_death_missingness_camera_and_action_clock(self):
        summary=export_tables(self.directory)
        events=self.rows('events.csv')
        self.assertFalse(any(r['unit_id']=='red_melee_w1_1' and r['frame_id']!='f0' for r in events))
        moved=next(r for r in events if r['frame_id']=='f1' and r['unit_id']=='blue_hero')
        self.assertEqual(float(moved['movement_px']),2)
        self.assertEqual(moved['target_distance_px'],'')
        self.assertTrue(summary['unknown_distance_rows']>0)
        actions=self.rows('actions.csv')
        self.assertEqual(len(actions),2)
        self.assertEqual(float(actions[1]['previous_action_start_gap_s']),.3)
        self.assertTrue((self.directory/'tables/events.csv').read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_custom_hero_ids(self):
        self.project['units'][0]['id']='hero_A'
        self.ann['frames']['f0']['units']['hero_A']=self.ann['frames']['f0']['units'].pop('blue_hero')
        for f in ('f1','f2'):self.ann['frames'][f]['units'].pop('blue_hero')
        write_json(self.directory/'project.json',self.project);write_json(self.directory/'annotations.json',self.ann)
        export_tables(self.directory)
        row=next(r for r in self.rows('events.csv') if r['unit_id']=='red_hero' and r['frame_id']=='f0')
        self.assertEqual(row['enemy_hero_id'],'hero_A')
        self.assertEqual(float(row['enemy_hero_distance_px']),5)

    def test_cannon_wave_requires_explicit_focus_without_count_limit(self):
        self.project['units'].append(dict(id='red_siege_w3_1',side='red',kind='siege',wave=3,first_seen_s=0))
        write_json(self.directory/'project.json',self.project)
        with self.assertRaisesRegex(ValueError,'distance_minions'):export_tables(self.directory)
        self.ann['frames']['f0']['distance_minions']=[u['id'] for u in self.project['units'] if u['kind']!='hero']
        write_json(self.directory/'annotations.json',self.ann)
        export_tables(self.directory)
        self.assertEqual([sum(r['frame_id']==f'f{i}' for r in self.rows('distances.csv')) for i in range(3)],[14,13,13])

    def test_minion_to_minion_distances_are_excluded(self):
        self.ann['frames']['f0']['units']['blue_melee_w1_1']=dict(center=[10,10],target='red_melee_w1_1')
        write_json(self.directory/'annotations.json',self.ann)
        export_tables(self.directory)
        row=next(r for r in self.rows('events.csv') if r['unit_id']=='blue_melee_w1_1' and r['frame_id']=='f0')
        self.assertEqual(row['target_distance_px'],'')
        self.assertEqual(len(self.rows('deaths.csv')),1)

    def test_all_dead_produces_no_distance_rows_but_retains_schema(self):
        self.ann['frames']['f0']['units']={u['id']:dict(alive=False) for u in self.project['units']}
        write_json(self.directory/'annotations.json',self.ann)
        export_tables(self.directory)
        self.assertEqual(self.rows('events.csv'),[])
        self.assertEqual(self.rows('distances.csv'),[])
        header=(self.directory/'tables/events.csv').read_text(encoding='utf-8-sig').splitlines()[0]
        self.assertIn('enemy_hero_id',header)

    def test_csv_roundtrip_recalculates_distances(self):
        export_tables(self.directory)
        edited=self.directory/'edit.csv'
        rows=self.rows('events.csv');rows[0]['x_px']='1';rows[0]['enemy_hero_distance_px']='999'
        with edited.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        import_csv(self.directory,edited)
        self.assertAlmostEqual(float(self.rows('events.csv')[0]['enemy_hero_distance_px']),20**.5)

    def test_reject_unknown_or_nonfinite_annotation_and_damaged_csv(self):
        self.ann['frames']['f0']['units']['blue_hero']['center']=[float('nan'),0]
        with self.assertRaises(ValueError):validate_annotations(self.project,self.ann)
        (self.directory/'broken.csv').write_text('frame_id,unit_id,action\nf0,blue_hero,??\n')
        with self.assertRaises(ValueError):import_csv(self.directory,self.directory/'broken.csv')

    def test_portable_bundle(self):
        export_assessment(self.directory)
        with zipfile.ZipFile(self.directory/'assessment_bundle.zip') as archive:
            names=archive.namelist()
            self.assertIn('assessment/evaluation_request.md',names)
            self.assertIn('tables/distances.csv',names)
            self.assertTrue(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names))
            manifest=json.loads(archive.read('assessment/manifest.json'))
            self.assertFalse(manifest['hero_parameters_declared_verified'])
            self.assertEqual(len(manifest['framework_sha256']),2)

    def test_server_token_save_and_path_scope(self):
        server=make_server(self.directory)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base,query=server.session_url.split('?')
        try:
            with urllib.request.urlopen(base+'api/state?'+query) as response:
                self.assertEqual(json.load(response)['project']['source_name'],'video.mp4')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'api/state')
            request=urllib.request.Request(base+'api/save?'+query,data=json.dumps({'project':self.project,'annotations':self.ann}).encode(),headers={'Content-Type':'application/json','X-Session-Token':query.split('=')[1]},method='POST')
            with urllib.request.urlopen(request) as response:self.assertTrue(json.load(response)['saved'])
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'../README.md?'+query)
        finally:
            server.shutdown();server.server_close();thread.join()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class Sampling(unittest.TestCase):
    def test_actual_sampling_for_all_supported_intervals(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);video=directory/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            for step in (.1,.3,.5):
                p=sample(video,directory/str(step),.1,1.6,step)
                times=[f['source_time_s'] for f in p['frames']]
                self.assertTrue(len(times)>=3)
                self.assertTrue(all(abs(b-a-step)<.034 for a,b in zip(times,times[1:])))
                self.assertTrue(all(.1<=t<1.6 for t in times))
                self.assertTrue(all((directory/str(step)/f['image']).is_file() for f in p['frames']))
            with self.assertRaises(ValueError):sample(video,directory/'invalid',0,1,.05)

    def test_cli_works_after_relocation_without_reference_cases(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);distribution=directory/'independent_distribution';distribution.mkdir()
            for name in ('main.py','framework_documents.json'):
                shutil.copy2(root/name,distribution/name)
            for name in ('workbench','algorithms'):
                shutil.copytree(root/name,distribution/name,ignore=shutil.ignore_patterns('__pycache__'))
            for name in read_json(root/'framework_documents.json').values():shutil.copy2(root/name,distribution/name)
            (distribution/'docs').mkdir()
            shutil.copy2(root/'docs/evaluation_request_template.md',distribution/'docs/evaluation_request_template.md')
            video=directory/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','1','-c:v','libx264',str(video)],check=True)
            subprocess.run([sys.executable,'-S','main.py','sample','--video',str(video),'--start','0','--end','.8','--step','.3','--output','runs/session'],cwd=distribution,stdout=subprocess.PIPE,check=True)
            subprocess.run([sys.executable,'-S','main.py','export','runs/session'],cwd=distribution,stdout=subprocess.PIPE,check=True)
            self.assertTrue((distribution/'runs/session/assessment_bundle.zip').is_file())
            self.assertFalse((distribution/'example').exists())


class OptionalSolver(unittest.TestCase):
    def test_zero_sum_matching_pennies(self):
        try:import scipy
        except ImportError:self.skipTest('optional SciPy not installed')
        result=solve_matrix(dict(game_type='two_player_zero_sum',assessment_reference='report#1',payoff_matrix=[[1,-1],[-1,1]]))
        self.assertAlmostEqual(result['value'],0)
        self.assertAlmostEqual(result['row_policy'][0],.5)
        self.assertLess(result['duality_gap'],1e-8)
        with self.assertRaises(ValueError):solve_matrix(dict(game_type='general_sum',assessment_reference='x',payoff_matrix=[[1]]))


if __name__=='__main__':unittest.main()
