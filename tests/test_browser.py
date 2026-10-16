"""Optional end-to-end UI check; pip install -r requirements-test.txt first."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import json
import zipfile
from workbench.core import sample, read_json
from workbench.server import make_server


@unittest.skipUnless(importlib.util.find_spec('playwright') and shutil.which('ffmpeg'),'optional Playwright and FFmpeg required')
class BrowserWorkflow(unittest.TestCase):
    def test_annotation_switch_save_and_export(self):
        from playwright.sync_api import sync_playwright, Error
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);video=directory/'synthetic.mp4';project=directory/'project'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=1280x720:rate=30',
                '-t','1','-c:v','libx264',str(video)],check=True)
            sample(video,project,0,.8,.3,first_wave_template=True)
            server=make_server(project)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    try:
                        browser=pw.chromium.launch(headless=True,channel=os.environ.get('LOL_BROWSER_CHANNEL') or None)
                    except Error as error:self.skipTest('Install a Playwright browser or set LOL_BROWSER_CHANNEL: '+str(error).splitlines()[0])
                    page=browser.new_page(viewport={'width':1440,'height':1100})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(server.session_url)
                    page.wait_for_function("document.querySelector('#canvas').width===1280")
                    box=page.locator('#canvas').bounding_box()
                    def click_point(x,y):page.mouse.click(box['x']+x*box['width']/1280,box['y']+y*box['height']/720)
                    click_point(100,100)
                    page.locator('#act').fill('attack')
                    page.locator('#start').fill('0.1')
                    page.locator('#target').select_option('red_melee_w1_1')
                    page.locator('#unit').select_option('red_hero')
                    click_point(300,250)
                    page.locator('#act').fill('Q')
                    page.locator('#scale').fill('189=350')
                    page.locator('#save').click()
                    page.wait_for_function("document.querySelector('#status').textContent.includes('已保存')")
                    annotations=read_json(project/'annotations.json')['frames']['f000001']['units']
                    self.assertEqual(annotations['blue_hero']['action'],'attack')
                    self.assertEqual(annotations['red_hero']['action'],'Q')
                    self.assertAlmostEqual(annotations['blue_hero']['center'][0],100,delta=1)
                    page.locator('summary').filter(has_text='单位列表与新增单位').click()
                    page.locator('#side').select_option('red')
                    page.locator('#kind').select_option('siege')
                    page.locator('#add').click()
                    page.locator('#add').click()
                    page.locator('#selectAllMinions').click()
                    page.locator('#export').click()
                    page.wait_for_selector('#downloads a',timeout=20000)
                    self.assertTrue((project/'assessment_bundle.zip').is_file())
                    roster=read_json(project/'project.json')['units']
                    self.assertIn('red_siege_w2_1',[u['id'] for u in roster])
                    self.assertIn('red_siege_w2_2',[u['id'] for u in roster])
                    self.assertEqual(len(read_json(project/'annotations.json')['frames']['f000001']['distance_minions']),14)
                    page.locator('#gameRun').click()
                    self.assertFalse((project/'game_analysis').exists())
                    page.locator('#gameDraft').click()
                    page.wait_for_function("document.querySelector('#gameTask').value.includes('entry_time_s')")
                    page.locator('summary').filter(has_text='非指向技能、被动、符文的观察概率与频率').click()
                    observed='opportunity_id,mechanism_id,kind,event_type,actor,target,source_time_s,eligible,success,outcome_id,hit_unit_ids,window_start_s,window_end_s,context,source\none,hit,binary,skillshot_hit,blue_hero,red_hero,0.1,true,true,,,0,0.8,synthetic,frame1\n'
                    page.locator('#mechanicsCsv').set_input_files({'name':'observations.csv','mimeType':'text/csv','buffer':observed.encode()})
                    page.wait_for_function("document.querySelector('#mechanicsStatus').textContent.includes('eligible_trials')")
                    page.locator('#useModels').click()
                    self.assertFalse(json.loads(page.locator('#gameTask').input_value())['stochastic']['models'][0]['context_verified'])
                    from test_short_horizon import task
                    complete=json.loads(json.dumps(task()).replace('"bh"','"blue_hero"').replace('"rh"','"red_hero"').replace('"rm"','"red_melee_w1_1"'))
                    complete['frame_id']='f000001';complete['entry_time_s']=0
                    page.locator('#gameTask').fill(json.dumps(complete));page.locator('#gameEnabled').check()
                    page.locator('#gameRun').click()
                    page.wait_for_selector('#gameResults a',timeout=20000)
                    with page.expect_response(lambda response:'/api/export?' in response.url) as response:
                        page.locator('#export').click()
                    response.value.json()
                    with zipfile.ZipFile(project/'assessment_bundle.zip') as bundle:
                        self.assertIn('mechanics/estimated_models.json',bundle.namelist())
                        self.assertTrue(any(n.startswith('game_analysis/') and n.endswith('/result.json') for n in bundle.namelist()))
                    self.assertFalse(errors)
                    screenshot=os.environ.get('LOL_UI_SCREENSHOT')
                    if screenshot:page.screenshot(path=screenshot,full_page=True)
                    browser.close()
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
