"""Loopback-only annotation UI. Coordinates are accepted only through explicit annotation."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import secrets
import threading
import urllib.parse
import webbrowser
from .core import read_json, write_json, validate_annotations, calibration, export_assessment


def make_server(directory, port=0):
    directory = Path(directory).resolve()
    nonce = secrets.token_urlsafe(24)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, data, mime='application/json; charset=utf-8', status=200):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('token') == [nonce]

        def do_GET(self):
            asset = urllib.parse.urlsplit(self.path).path
            if asset in {'/assets/i18n.js', '/assets/loadouts.js'}:
                return self.respond((Path(__file__).parent / asset.split('/')[-1]).read_bytes(), 'text/javascript; charset=utf-8')
            if not self.authorized():
                return self.respond({'error':'invalid session token'},status=403)
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if path == '/':
                return self.respond((Path(__file__).parent/'review.html').read_bytes(),'text/html; charset=utf-8')
            if path == '/api/state':
                with lock:
                    state = {k:read_json(directory/f'{k}.json') for k in ['project','annotations']}
                    state['proposals'] = read_json(directory/'proposals.json') if (directory/'proposals.json').exists() else {}
                return self.respond(state)
            if path == '/api/game-tools':
                from .game_tools import availability
                return self.respond(availability())
            if path == '/api/mechanics-template':
                from .mechanic_observations import template
                return self.respond(b'\xef\xbb\xbf'+template().encode('utf-8'),'text/csv; charset=utf-8')
            if path == '/api/mechanics-adapters':
                return self.respond(read_json(Path(__file__).resolve().parents[1]/'templates/mechanic_adapters.json'))
            target = (directory/path.lstrip('/')).resolve()
            if not target.is_relative_to(directory) or not target.is_file() or target.suffix.lower() not in {'.jpg','.csv','.zip','.json'}:
                return self.respond({'error':'not found'},status=404)
            mime = {'.jpg':'image/jpeg','.csv':'text/csv; charset=utf-8','.zip':'application/zip','.json':'application/json; charset=utf-8'}[target.suffix.lower()]
            return self.respond(target.read_bytes(),mime)

        def do_POST(self):
            if not self.authorized() or self.headers.get('X-Session-Token') != nonce:
                return self.respond({'error':'invalid session token'},status=403)
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 32*1024*1024:
                    raise ValueError('invalid request size')
                body = json.loads(self.rfile.read(length))
                path = urllib.parse.urlsplit(self.path).path
                with lock:
                    if path == '/api/save':
                        original = read_json(directory/'project.json')
                        # Keep source/frame paths immutable; only editable project fields cross the API.
                        for key in ['units','hero_data','strategy_text','calibration']:
                            if key in body['project']:
                                original[key] = body['project'][key]
                        value = original.get('calibration')
                        original['calibration'] = calibration(f"{value['pixels']}={value['game_units']}") if value else None
                        validate_annotations(original,body['annotations'])
                        write_json(directory/'project.json',original)
                        write_json(directory/'annotations.json',body['annotations'])
                        self.respond({'saved':True})
                    elif path == '/api/catalog':
                        from .catalog import load_catalog
                        self.respond(load_catalog(directory, body['version']))
                    elif path == '/api/champion-details':
                        from .catalog import champion_details
                        self.respond(champion_details(directory, body['version'], body['champion']))
                    elif path == '/api/aramonly-preview':
                        from .external_selectors import aramonly_preview
                        self.respond(aramonly_preview(directory,body['url'],body['version']))
                    elif path == '/api/configuration-save':
                        from .loadouts import save_configuration
                        self.respond(save_configuration(directory, body))
                    elif path == '/api/configuration-at':
                        from .loadouts import configuration_at, number
                        time = number(body['source_time_s'], 'source time')
                        self.respond(configuration_at(directory, read_json(directory/'project.json'), time))
                    elif path == '/api/export':
                        self.respond(export_assessment(directory))
                    elif path == '/api/game-draft':
                        from .game_tools import draft
                        self.respond(draft(read_json(directory/'project.json'),read_json(directory/'annotations.json'),body['frame_id'],directory))
                    elif path == '/api/game-run':
                        from .game_tools import save_run
                        self.respond(save_run(directory,body['task']))
                    elif path == '/api/estimate-probabilities':
                        from .mechanic_observations import estimate
                        result=estimate(body['csv'])
                        folder=directory/'mechanics';folder.mkdir(exist_ok=True)
                        (folder/'observations.csv').write_text(body['csv'],encoding='utf-8-sig')
                        write_json(folder/'estimated_models.json',result)
                        self.respond(result)
                    else:
                        self.respond({'error':'not found'},status=404)
            except (ValueError,KeyError,TypeError,OSError,ImportError) as error:
                self.respond({'error':str(error)},status=400)

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.session_url = f'http://127.0.0.1:{server.server_port}/?token={nonce}'
    return server


def review(directory, open_browser=True):
    server = make_server(directory)
    print('Annotation workspace:',server.session_url,flush=True)
    print('Keep this terminal open. Ctrl+C stops the local server.',flush=True)
    if open_browser:
        webbrowser.open(server.session_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
