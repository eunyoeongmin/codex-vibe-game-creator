"""Local-only game creation dashboard. Run start.bat to prepare its runtime."""
from __future__ import annotations
import argparse
import base64
from contextlib import closing
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import webbrowser

from codex_bridge import CodexRpc, RpcError
from dashboard_session import ProjectSession
from dashboard_state import State, safe_file
import new_project
from dashboard_planning import Planning
from runtime_setup import APP_HOME
from localization import valid_language
from asset_store import AssetStore

WEB = Path(__file__).resolve().parent / 'web'
MAX_BODY = 24 * 1024 * 1024


class App:
    def __init__(self, state_dir=None, projects_root=None, runtime=None):
        self.state_dir = Path(state_dir or APP_HOME / 'dashboard').resolve()
        self.state = State(self.state_dir, projects_root or new_project.PROJECTS_ROOT)
        self.planning = Planning(self.state)
        self.runtime = runtime or new_project.installed_runtime()
        self.codex_home = self.state_dir / 'codex'
        self.token = secrets.token_urlsafe(32)
        self.sessions = {}
        self.previews = {}
        self.lock = threading.RLock()
        self.auth_rpc = None
        self.login = None
        self.sandbox_setup = None

    def auth(self):
        with self.lock:
            if self.auth_rpc is None or self.auth_rpc.process.poll() is not None:
                self.auth_rpc = CodexRpc(self.codex_home, self.state_dir, self.auth_event)
            return self.auth_rpc

    def auth_event(self, method, params):
        if method == 'windowsSandbox/setupCompleted':
            self.sandbox_setup = params

    def prepare_sandbox(self, retry=False):
        with self.lock:
            if os.name != 'nt':
                return 'ready'
            rpc = self.auth()
            readiness = rpc.call('windowsSandbox/readiness')['status']
            if readiness != 'ready' and (self.sandbox_setup is None or
                                        (retry and self.sandbox_setup.get('success') is False)):
                self.sandbox_setup = {'success': None}
                try:
                    rpc.call('windowsSandbox/setupStart', {'mode': 'elevated'})
                except (OSError, RpcError) as error:
                    self.sandbox_setup = {'success': False, 'error': str(error)}
            return readiness

    def status(self):
        try:
            rpc = self.auth()
            account = rpc.call('account/read').get('account')
            models = rpc.call('model/list', {'limit': 100}).get('data', [])
            readiness = self.prepare_sandbox()
            return {'account': account, 'models': models, 'error': None,
                    'sandbox_readiness': readiness, 'sandbox_setup': self.sandbox_setup}
        except (OSError, RpcError) as error:
            return {'account': None, 'models': [], 'error': str(error)}

    def model_settings(self, model=None, effort=None):
        models = self.auth().call('model/list', {'limit': 100}).get('data', [])
        selected = next((m for m in models if m['model'] == model or
                         (not model and m.get('isDefault'))), None)
        if selected is None:
            raise ValueError('Codex 모델 목록에 있는 모델을 선택하세요.')
        effort = effort or selected.get('defaultReasoningEffort')
        allowed = [e['reasoningEffort'] for e in selected.get('supportedReasoningEfforts', [])]
        if effort and effort not in allowed:
            raise ValueError('선택한 모델이 지원하는 추론 수준을 선택하세요.')
        return selected['model'], effort

    def service_tier(self, model, tier=None):
        tier = tier or 'default'
        models = self.auth().call('model/list', {'limit': 100}).get('data', [])
        selected = next((m for m in models if m['model'] == model), {})
        tiers = selected.get('serviceTiers') or []
        allowed = {'default', *(t['id'] for t in tiers)}
        if not tiers:
            allowed.update('priority' if t == 'fast' else t for t in selected.get('additionalSpeedTiers') or [])
        if tier not in allowed:
            raise ValueError('선택한 모델이 지원하는 속도를 선택하세요.')
        return tier

    def connect(self, project_id, model=None, effort=None, service_tier=None):
        with self.lock:
            project = self.state.project(project_id)
            session = self.sessions.get(project_id)
            if session and not session.closed:
                return self.state.project(project_id)['info']
            if not self.auth().call('account/read').get('account'):
                raise ValueError('먼저 대시보드의 Codex 로그인 버튼으로 로그인하세요.')
            if self.prepare_sandbox() != 'ready':
                raise ValueError('Windows 작업 권한을 자동으로 준비하고 있습니다. 관리자 확인 창이 나타나면 완료해 주세요.')
            model, effort = self.model_settings(model or project.get('model'),
                                                effort or project.get('info', {}).get('requested_effort'))
            service_tier = self.service_tier(model, service_tier or project.get('info', {}).get('requested_service_tier'))
            new_project.ensure_production_support(Path(project['path']))
            session = ProjectSession(self.state, project_id, self.codex_home)
            session.planning = self.planning
            self.sessions[project_id] = session
            try:
                return session.connect(model, effort, service_tier)
            except Exception:
                session.close()
                self.sessions.pop(project_id, None)
                raise

    def session(self, project_id):
        self.state.project(project_id)
        session = self.sessions.get(project_id)
        if not session or session.closed:
            raise ValueError('대화 연결 버튼을 눌러 이 프로젝트에 연결하세요.')
        return session

    def preview(self, project_id, relative):
        project = self.state.project(project_id)
        target = safe_file(project['path'], relative)
        if not target.is_file() or target.suffix.lower() not in ('.html', '.htm'):
            raise ValueError('미리 볼 HTML 파일을 선택하세요.')
        with self.lock:
            if project_id not in self.previews:
                server = PreviewServer(('127.0.0.1', 0), PreviewHandler)
                server.root = Path(project['path'])
                self.previews[project_id] = server
                threading.Thread(target=server.serve_forever, daemon=True).start()
            server = self.previews[project_id]
        from urllib.parse import quote
        return f'http://127.0.0.1:{server.server_port}/{quote(relative.replace(chr(92), "/"))}'

    def close(self):
        for session in list(self.sessions.values()):
            session.close()
        if self.auth_rpc:
            self.auth_rpc.close()
        for server in self.previews.values():
            server.shutdown()
            server.server_close()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


class PreviewServer(LocalServer):
    pass


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                raise ValueError('허용되지 않은 호스트입니다.')
            relative = unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
            parts = relative.replace('\\', '/').split('/')
            if any(p.startswith('.') for p in parts) or parts[0] in ('data', 'guide', 'catalogs', 'genres'):
                raise ValueError('게임 공개 파일만 미리 볼 수 있습니다.')
            target = safe_file(self.server.root, relative)
            if target.is_dir():
                target = safe_file(self.server.root, relative.rstrip('/') + '/index.html')
            data = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, OSError):
            self.send_error(404)

    def log_message(self, *_):
        pass


class Handler(BaseHTTPRequestHandler):
    @property
    def app(self):
        return self.server.app

    def respond(self, value, status=200, content_type='application/json; charset=utf-8'):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob: data: https: http:; media-src 'self' blob: data:; frame-src http://127.0.0.1:*; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            return False
        if self.headers.get('Origin') not in (None, origin):
            return False
        return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.app.token)

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def dispatch(self, method):
        try:
            parsed = urlsplit(self.path)
            route = parsed.path
            if method == 'GET' and route in ('/', '/app.js', '/assets.js', '/references.js', '/style.css', '/i18n.js', '/locales.json'):
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.respond({'error': '허용되지 않은 호스트입니다.'}, 403)
                filename = 'index.html' if route == '/' else route[1:]
                return self.respond((WEB / filename).read_bytes(), content_type={
                    'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'assets.js': 'text/javascript; charset=utf-8',
                    'references.js': 'text/javascript; charset=utf-8',
                    'style.css': 'text/css; charset=utf-8', 'i18n.js': 'text/javascript; charset=utf-8',
                    'locales.json': 'application/json; charset=utf-8'}[filename])
            if not self.authorized():
                return self.respond({'error': 'start.bat으로 연 대시보드에서 접속하세요.'}, 403)
            body = {}
            if method == 'POST':
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('요청 크기가 올바르지 않습니다. 첨부는 16MB 이하로 선택하세요.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('JSON 객체가 필요합니다.')
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            result = self.route(method, route, query, body)
            self.respond(result)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
            self.respond({'error': str(error)}, 400)
        except (RpcError, OSError, sqlite3.Error) as error:
            self.respond({'error': str(error)}, 503)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self, method, route, query, body):
        app = self.app
        if route == '/api/preferences':
            if method == 'POST':
                language = valid_language(body.get('language'))
                app.state.set_setting('language', language)
                for session in app.sessions.values():
                    session.requested_language = language
            return {'language': app.state.setting('language'),
                    'version': (WEB.parent / 'VERSION').read_text(encoding='utf-8').strip()}
        if route == '/api/status' and method == 'GET':
            return {**app.status(), 'projects_root': str(app.state.projects_root)}
        if route == '/api/login' and method == 'POST':
            app.login = app.auth().call('account/login/start', {'type': 'chatgpt'})
            return {'url': app.login['authUrl']}
        if route == '/api/sandbox' and method == 'POST':
            return {'status': app.prepare_sandbox(retry=True)}
        if route == '/api/usage' and method == 'GET':
            rpc = app.auth()
            if not rpc.call('account/read').get('account'):
                return {'available': False, 'message': 'Codex 로그인 후 사용량을 확인할 수 있습니다.'}
            try:
                return {'available': True, **rpc.call('account/rateLimits/read', timeout=20)}
            except RpcError as error:
                return {'available': False, 'message': str(error)}
        if route == '/api/projects':
            if method == 'GET':
                return {'projects': app.state.projects()}
            path = new_project.create_project(app.state.projects_root, name=body.get('name'), runtime=app.runtime)
            return {'project': app.state.add(path)}
        parts = route.strip('/').split('/')
        if len(parts) != 4 or parts[:2] != ['api', 'projects']:
            raise ValueError('존재하지 않는 요청입니다.')
        project_id, action = parts[2:]
        project = app.state.project(project_id)
        root = Path(project['path'])
        if action == 'assets' and method == 'GET':
            store = AssetStore(root)
            return {'assets': store.list(kind=query.get('kind'), status=query.get('status'), query=query.get('q')),
                    'art_decisions': store.art_decisions()}
        if action == 'asset-save' and method == 'POST':
            return AssetStore(root).save(body.get('values'), asset_id=body.get('id'),
                expected_revision=body.get('revision'), actor='user', change_note=body.get('change_note'))
        if action == 'asset-history' and method == 'GET':
            return {'history': AssetStore(root).history(query.get('id'))}
        if action == 'asset-request' and method == 'POST':
            asset = AssetStore(root).get(body.get('id'))
            if asset['revision'] != body.get('revision'):
                raise ValueError('에셋이 변경되었습니다. 새로고침 후 다시 저장하세요.')
            request = body.get('text')
            if not isinstance(request, str) or not request.strip() or len(request) > 10000:
                raise ValueError('수정 요청을 1~10,000자로 입력하세요.')
            session = app.session(project_id)
            text = session.instructions.render('asset_request', asset=json.dumps(asset, ensure_ascii=False), request=request)
            session.send_message(text, instruction_section='asset_request', display_text=f'{asset["name"]}\n{request}')
            return {'accepted': True, 'working': bool(session.turn_id), 'activity': session.activity_status()}
        if action == 'asset-media' and method == 'GET':
            store = AssetStore(root)
            asset = store.get(query.get('id'))
            if query.get('path') not in asset['files']:
                raise ValueError('이 에셋에 등록된 파일만 열 수 있습니다.')
            path = store.file(query['path'])
            types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                     '.webp': 'image/webp', '.avif': 'image/avif', '.svg': 'image/svg+xml', '.bmp': 'image/bmp',
                     '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.flac': 'audio/flac'}
            if path.suffix.lower() not in types or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('미리보기는 16MB 이하 이미지·사운드 파일을 지원합니다.')
            return {'mime': types[path.suffix.lower()], 'data': base64.b64encode(path.read_bytes()).decode('ascii')}
        if method == 'GET' and action == 'history':
            before = int(query['before']) if 'before' in query else None
            return app.state.history(project_id, before=before)
        if method == 'GET' and action == 'events':
            session = app.sessions.get(project_id)
            assets = AssetStore(root).list()
            return {'events': app.state.events(project_id, int(query.get('after', 0))),
                    'questions': app.state.questions(project_id), 'project': project,
                    'connected': bool(session and not session.closed),
                    'working': bool(session and session.turn_id),
                    'activity': session.activity_status() if session else None,
                    'asset_counts': {status: sum(a['status'] == status for a in assets) for status in ('temporary', 'proposed')},
                    'progress': app.planning.progress(project_id)}
        if method == 'GET' and action == 'progress':
            return app.planning.progress(project_id)
        if method == 'POST' and action == 'summary':
            return app.planning.open_summary(project_id)
        if method == 'POST' and action == 'summary-more':
            session = app.sessions.get(project_id)
            if session and session.turn_id:
                raise ValueError('현재 답변이 끝난 뒤 선택해 주세요.')
            result = app.planning.more(project_id, body.get('fingerprint'))
            if session and not session.closed:
                session.send_instruction('planning_more')
            return result
        if method == 'POST' and action == 'summary-start':
            session = app.session(project_id)
            with session.lock:
                if session.turn_id:
                    raise ValueError('현재 답변이 끝난 뒤 선택해 주세요.')
                version = app.planning.approve(project_id, body.get('fingerprint'))
                new_project.ensure_production_support(root)
                session.send_instruction('production_start', version=version)
                for question in app.state.questions(project_id):
                    app.state.answer_question(project_id, question['id'])
                app.planning.delivered(project_id)
                return app.planning.progress(project_id)
        if method == 'POST' and action == 'connect':
            return {'info': app.connect(project_id, body.get('model'), body.get('effort'), body.get('service_tier'))}
        if method == 'POST' and action == 'model':
            model, effort = app.model_settings(body.get('model'), body.get('effort'))
            tier = app.service_tier(model, body.get('service_tier'))
            app.session(project_id).change_model(model, effort, tier)
            return {'model': model, 'effort': effort, 'service_tier': tier}
        if method == 'POST' and action == 'message':
            attachments = [safe_file(root, p) for p in body.get('attachments', [])]
            if any(p.parent != root / 'uploads' or not p.is_file() for p in attachments):
                raise ValueError('이 프로젝트에 업로드한 파일만 첨부할 수 있습니다.')
            text = body.get('text', '')
            if (not attachments and text.strip().rstrip('.!').lower() in (
                    '시작하자', '이제 시작하자', '개발 시작하자', '/development')
                    and not app.planning.progress(project_id)['spec_version']):
                app.state.event(project_id, 'user', text=text)
                return {'accepted': True, 'progress': app.planning.open_summary(project_id)}
            if attachments:
                text += '\n\n첨부 파일(프로젝트 상대 경로):\n' + '\n'.join(p.relative_to(root).as_posix() for p in attachments)
            session = app.session(project_id)
            session.send_message(text, attachments=attachments)
            return {'accepted': True, 'working': bool(session.turn_id), 'activity': session.activity_status()}
        if method == 'POST' and action == 'interrupt':
            app.session(project_id).interrupt()
            return {'accepted': True}
        if method == 'POST' and action == 'answer':
            app.session(project_id).answer(body['id'], body['answers'])
            return {'accepted': True}
        if method == 'GET' and action == 'files':
            files = []
            for directory, folders, names in os.walk(root, followlinks=False):
                folders[:] = sorted(f for f in folders if f not in (
                    'node_modules', '.git', '__pycache__', '.venv', 'tmp')
                    and Path(directory, f).resolve().is_relative_to(root))
                for name in sorted(names):
                    path = Path(directory, name)
                    if path.resolve().is_relative_to(root) and len(files) < 2500:
                        files.append(path.relative_to(root).as_posix())
            return {'files': files}
        if action == 'file':
            path = safe_file(root, query.get('path') if method == 'GET' else body.get('path'))
            if method == 'GET':
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('편집기는 2MB 이하의 텍스트 파일을 지원합니다.')
                data = path.read_bytes()
                try:
                    text = data.decode('utf-8-sig')
                except UnicodeDecodeError:
                    raise ValueError('이 파일은 UTF-8 텍스트 파일이 아닙니다.') from None
                return {'text': text, 'digest': hashlib.sha256(data).hexdigest()}
            if path.name == '.project' or '.harness' in path.relative_to(root).parts:
                raise ValueError('프로젝트 실행 설정은 편집기에서 변경할 수 없습니다.')
            content = body.get('text')
            if not isinstance(content, str) or len(content.encode('utf-8')) > 2 * 1024 * 1024:
                raise ValueError('UTF-8 텍스트 2MB 이하만 저장할 수 있습니다.')
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if current != body.get('digest'):
                raise ValueError('파일이 변경되었습니다. 다시 열어 최신 내용을 확인하세요.')
            path.parent.mkdir(parents=True, exist_ok=True)
            safe_file(root, path.relative_to(root).as_posix()).write_text(content, encoding='utf-8')
            return {'digest': hashlib.sha256(path.read_bytes()).hexdigest()}
        if method == 'GET' and action in ('attachment', 'image'):
            requested = query.get('path', '')
            if action == 'image' and Path(requested).is_absolute():
                requested = Path(requested).resolve().relative_to(root).as_posix()
            path = safe_file(root, requested)
            types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                     '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp', '.avif': 'image/avif'}
            if ((action == 'attachment' and path.parent != root / 'uploads') or path.suffix.lower() not in types
                    or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024):
                raise ValueError('프로젝트 안의 16MB 이하 이미지 파일만 표시할 수 있습니다.')
            return {'mime': types[path.suffix.lower()], 'data': base64.b64encode(path.read_bytes()).decode('ascii')}
        if method == 'POST' and action == 'upload':
            name = body.get('name', '')
            if not isinstance(name, str) or not name or '/' in name or '\\' in name or ':' in name:
                raise ValueError('올바른 파일 이름이 필요합니다.')
            data = base64.b64decode(body['data'], validate=True)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('첨부는 16MB 이하로 선택하세요.')
            path = safe_file(root, 'uploads/' + uuid.uuid4().hex[:10] + '-' + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as file:
                file.write(data)
            return {'path': path.relative_to(root).as_posix()}
        if method == 'GET' and action == 'records':
            db_path = safe_file(root, 'data/decisions.sqlite')
            with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                result = {}
                for table in ('user_decisions', 'work_decisions', 'user_references'):
                    result[table] = [dict(r) for r in db.execute(
                        f'SELECT * FROM {table} WHERE project_id=? ORDER BY rowid DESC LIMIT 100', (project_id,))]
                return result
        if method == 'GET' and action == 'reference':
            from reference_trace import get
            return get(root, query.get('id', ''))
        if method == 'POST' and action == 'preview':
            return {'url': app.preview(project_id, body.get('path', 'index.html'))}
        if method == 'POST' and action == 'folder':
            os.startfile(root)
            return {'opened': True}
        raise ValueError('존재하지 않는 작업입니다.')

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    app = App()
    server = LocalServer(('127.0.0.1', args.port), Handler)
    server.app = app
    url = f'http://127.0.0.1:{server.server_port}/#token={app.token}'
    print(f'Codex Vibe Game Creator: {url}', flush=True)
    print('프로젝트는 대시보드에서 생성합니다. 종료하려면 이 창에서 Ctrl+C를 누르세요.', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == '__main__':
    main()
