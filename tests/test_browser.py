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
    def test_visual_configuration_language_snapshots_and_reload(self):
        from playwright.sync_api import sync_playwright, Error
        from test_loadouts import fixture
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);video=directory/'synthetic.mp4';project=directory/'project'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=30',
                '-t','1','-c:v','libx264',str(video)],check=True)
            sample(video,project,0,.8,.3)
            fixture(project)
            server=make_server(project);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    try:browser=pw.chromium.launch(headless=True,channel=os.environ.get('LOL_BROWSER_CHANNEL') or None)
                    except Error as error:self.skipTest(str(error).splitlines()[0])
                    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(server.session_url);page.wait_for_selector('#patchVersion')
                    page.locator('#patchVersion').fill('16.6.1');page.locator('#loadCatalog').click()
                    page.wait_for_selector('#blueChampion');page.locator('#blueChampion').fill('Alpha');page.locator('#redChampion').fill('Beta')
                    page.locator('#blue_primary_path').select_option('100')
                    page.locator('#blue_primary0').select_option('101')
                    page.locator('#blue_secondary_path').select_option('200')
                    page.locator('#blue_secondary0').select_option('203');page.locator('#blue_secondary1').select_option('205')
                    page.locator('#saveFixed').click();page.wait_for_function("document.querySelector('#loadoutStatus').textContent.includes('锁定')")
                    page.locator('#blueLevel').select_option('1');page.locator('#blueRankQ').select_option('1')
                    page.locator('#blueInventoryKnown').check();page.locator('#blueItem0').fill('1');page.locator('#blueItem0').press('Tab')
                    with page.expect_response(lambda r:'/api/configuration-save?' in r.url,timeout=4000) as saved_response:
                        page.locator('#recordSnapshot').click()
                    self.assertEqual(saved_response.value.status,200,saved_response.value.text())
                    page.wait_for_function("p.configuration.snapshots.length===1")
                    page.locator('#next').click();page.wait_for_function("document.querySelector('#time').textContent.includes('2/')")
                    page.locator('#blueLevel').select_option('2');page.locator('#blueItem0').fill('2');page.locator('#blueItem0').press('Tab')
                    with page.expect_response(lambda r:'/api/configuration-save?' in r.url):page.locator('#recordSnapshot').click()
                    page.locator('#uiLanguage').select_option('en');page.wait_for_function("document.documentElement.lang==='en'")
                    self.assertIn('Champion',page.locator('#loadoutPanel h3').first.inner_text())
                    self.assertEqual(page.locator('#blueLevel').input_value(),'2')
                    page.reload();page.wait_for_selector('#blueChampion');page.locator('#loadState').click()
                    self.assertEqual(page.locator('#blueLevel').input_value(),'1')
                    self.assertIn('1',page.locator('#blueItem0').input_value())
                    self.assertTrue(page.locator('#blueChampion').is_disabled())
                    # Exercise an actual second-origin selector popup, not a forged local API call.
                    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
                    class Selector(BaseHTTPRequestHandler):
                        def log_message(self,*args):pass
                        def do_GET(self):
                            html=b'''<script>
                            const q=new URLSearchParams(location.search),o=q.get('workbench_origin'),n=q.get('bridge_nonce');
                            addEventListener('message',e=>{if(e.origin!==o||e.data.nonce!==n||e.data.type!=='lol-workbench.selector.init')return;
                              const c=e.data.configuration;c.match_setup.sides.blue.rune_page.primary[0]=102;
                              opener.postMessage({type:'lol-workbench.selector.result',nonce:n,
                                provider:{project_url:location.origin,updated_at:'2026-10-16',data_patch:'16.6.1'},configuration:c},o)});
                            opener.postMessage({type:'lol-workbench.selector.ready',nonce:n},o);
                            </script>'''
                            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html)
                    provider=ThreadingHTTPServer(('127.0.0.1',0),Selector)
                    provider_thread=threading.Thread(target=provider.serve_forever,daemon=True);provider_thread.start()
                    try:
                        page.locator('summary').filter(has_text='External selector return').click()
                        page.locator('#externalSelectorUrl').fill(f'http://127.0.0.1:{provider.server_port}/')
                        page.on('dialog',lambda dialog:dialog.accept())
                        with page.expect_popup() as popup_info:page.locator('#openExternal').click()
                        popup=popup_info.value
                        self.assertNotIn('token=',popup.url)
                        page.wait_for_function("p.configuration.match_setup.sides.blue.rune_page.primary[0]===102")
                        self.assertEqual(page.locator('#blueChampion').input_value().split('[')[-1],'Alpha]')
                        popup.close()
                    finally:provider.shutdown();provider.server_close();provider_thread.join()
                    page.locator('#export').click();page.wait_for_selector('#downloads a')
                    saved=read_json(project/'project.json')['configuration']
                    self.assertEqual([s['sides']['blue']['items'][0]['id'] for s in saved['snapshots']],['1','2'])
                    self.assertEqual(saved['match_setup']['sides']['blue']['rune_page']['primary'][0],102)
                    with zipfile.ZipFile(project/'assessment_bundle.zip') as archive:
                        self.assertIn('assessment/hero_states.json',archive.namelist())
                        self.assertIn('catalogs/16.6.1/catalog.json',archive.namelist())
                    self.assertEqual(errors,[])
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()

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
