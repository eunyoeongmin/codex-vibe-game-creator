"""Local-only game creation dashboard. Run start.bat to prepare its runtime."""
from __future__ import annotations
from message_catalog import text as _msg, browser_catalog, bundle_runtime, error_payload
import argparse
import base64
from contextlib import closing
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import re
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
from project_workbench import Discards, context_search, target

WEB = Path(__file__).resolve().parent / 'web'
MAX_BODY = 24 * 1024 * 1024


class ConnectionRecoveryError(RpcError):
    def __init__(self, message, detail, *, restart_required=False):
        super().__init__(message)
        self.detail = str(detail)
        self.restart_required = restart_required


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
            if self.auth_rpc is None or self.auth_rpc.closed or self.auth_rpc.process.poll() is not None:
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
            raise ValueError(_msg('ui.choose.a.model.from.the.codex.model.list'))
        effort = effort or selected.get('defaultReasoningEffort')
        allowed = [e['reasoningEffort'] for e in selected.get('supportedReasoningEfforts', [])]
        if effort and effort not in allowed:
            raise ValueError(_msg('ui.choose.a.reasoning.effort.supported.by.this.model'))
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
            raise ValueError(_msg('ui.select.a.speed.supported.by.this.model'))
        return tier

    def connect(self, project_id, model=None, effort=None, service_tier=None, *, restart=False):
        with self.lock:
            project = self.state.project(project_id)
            session = self.sessions.get(project_id)
            if session:
                with session.lock:
                    if not session.closed and not session.rpc.closed and session.rpc.process.poll() is None:
                        try:
                            session.rpc.call('account/read', timeout=5)
                        except (RpcError, OSError) as error:
                            if not restart:
                                raise ConnectionRecoveryError(
                                    _msg('ui.could.not.confirm.a.response.from.the.codex'), error,
                                    restart_required=True) from error
                        else:
                            return self.state.project(project_id)['info']
                    session.close()
                    self.sessions.pop(project_id, None)
            # The login/control process can also be stale. It does not run game turns.
            try:
                account = self.auth().call('account/read', timeout=5).get('account')
            except (RpcError, OSError):
                if self.auth_rpc:
                    self.auth_rpc.close()
                self.auth_rpc = None
                try:
                    account = self.auth().call('account/read', timeout=5).get('account')
                except (RpcError, OSError) as error:
                    raise ConnectionRecoveryError(_msg('ui.failed.to.restore.the.codex.sign.in.connection'), error) from error
            if not account:
                raise ValueError(_msg('ui.sign.in.using.the.dashboard.s.codex.sign'))
            if self.prepare_sandbox() != 'ready':
                raise ValueError(_msg('ui.windows.permissions.are.being.prepared.complete.the.administrator'))
            model, effort = self.model_settings(model or project.get('model'),
                                                effort or project.get('info', {}).get('requested_effort'))
            service_tier = self.service_tier(model, service_tier or project.get('info', {}).get('requested_service_tier'))
            new_project.ensure_production_support(Path(project['path']))
            try:
                session = ProjectSession(self.state, project_id, self.codex_home)
            except (RpcError, OSError) as error:
                raise ConnectionRecoveryError(_msg('ui.could.not.start.the.codex.process'), error) from error
            session.planning = self.planning
            self.sessions[project_id] = session
            try:
                return session.connect(model, effort, service_tier)
            except Exception as error:
                session.close()
                self.sessions.pop(project_id, None)
                raise ConnectionRecoveryError(
                    _msg('ui.could.not.restore.the.existing.conversation') if project.get('thread_id') else
                    _msg('ui.could.not.connect.the.conversation'), error) from error

    def session(self, project_id):
        self.state.project(project_id)
        session = self.sessions.get(project_id)
        if not session or session.closed:
            raise ValueError(_msg('ui.connect.to.this.project.s.conversation.first'))
        return session

    def preview(self, project_id, relative, *, variant=None):
        project = self.state.project(project_id)
        preview_root = safe_file(project['path'], variant['folder']) if variant else Path(project['path'])
        key = project_id + (':' + variant['id'] if variant else '')
        target = safe_file(preview_root, relative)
        if not target.is_file() or target.suffix.lower() not in ('.html', '.htm'):
            raise ValueError(_msg('ui.choose.an.html.file.to.preview'))
        with self.lock:
            if key not in self.previews:
                server = PreviewServer(('127.0.0.1', 0), PreviewHandler)
                server.root = preview_root
                server.dashboard_origin = getattr(self, 'dashboard_origin', '')
                self.previews[key] = server
                threading.Thread(target=server.serve_forever, daemon=True).start()
            server = self.previews[key]
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
                raise ValueError(_msg('py.dashboard.message'))
            relative = unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
            parts = relative.replace('\\', '/').split('/')
            if any(p.startswith('.') for p in parts) or parts[0] in ('data', 'guide', 'catalogs', 'genres', 'agents', 'discarded'):
                raise ValueError(_msg('py.dashboard.message.2'))
            special = {'__live_runtime.js': 'live-runtime.js', '__creator_bridge.js': 'feedback-bridge.js', '__timeline_player.js': 'timeline-player.js', '__gameplay_runtime.js': 'gameplay-runtime.js', '__balance_runtime.js': 'balance-runtime.js'}
            target = WEB / special[relative] if relative in special else safe_file(self.server.root, relative)
            if target.is_dir():
                target = safe_file(self.server.root, relative.rstrip('/') + '/index.html')
            data = (bundle_runtime(target.read_text(encoding='utf-8')).encode('utf-8')
                    if relative in special else target.read_bytes())
            if target.suffix.lower() in ('.html', '.htm') and self.server.dashboard_origin:
                # Inject only into the served preview; never alter game files or exports.
                from creator_tools import manifest
                from live_tools import build_fingerprint
                fingerprint = build_fingerprint(manifest(self.server.root))
                bridge = f'<script src="/__live_runtime.js"></script><script src="/__balance_runtime.js"></script><script src="/__gameplay_runtime.js"></script><script src="/__timeline_player.js"></script><script src="/__creator_bridge.js" data-parent="{self.server.dashboard_origin}" data-fingerprint="{fingerprint}"></script>'.encode()
                head = re.search(br'</head\s*>', data, re.I)
                doctype = re.search(br'<!doctype[^>]*>', data, re.I)
                position = head.start() if head else doctype.end() if doctype else 0
                data = data[:position] + bridge + data[position:]
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
            if method == 'GET' and route == '/message-catalog.js':
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.respond({'error': _msg('py.dashboard.message')}, 403)
                return self.respond(browser_catalog().encode('utf-8'), content_type='text/javascript; charset=utf-8')
            if method == 'GET' and route in ('/live.js', '/messages.js', '/', '/app.js', '/assets.js', '/references.js', '/workbench.js', '/creator.js', '/production.js', '/gameplay.js', '/studio.js', '/sound-runtime.js', '/style.css', '/i18n.js'):
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.respond({'error': _msg('py.dashboard.message')}, 403)
                filename = 'index.html' if route == '/' else route[1:]
                return self.respond((WEB / filename).read_bytes(), content_type={
                    'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'assets.js': 'text/javascript; charset=utf-8',
                    'references.js': 'text/javascript; charset=utf-8',
                    'workbench.js': 'text/javascript; charset=utf-8',
                    'creator.js': 'text/javascript; charset=utf-8',
                    'studio.js': 'text/javascript; charset=utf-8',
                    'sound-runtime.js': 'text/javascript; charset=utf-8',
                    'gameplay.js': 'text/javascript; charset=utf-8',
                    'production.js': 'text/javascript; charset=utf-8',
                    'style.css': 'text/css; charset=utf-8', 'i18n.js': 'text/javascript; charset=utf-8',
                    'live.js': 'text/javascript; charset=utf-8', 'messages.js': 'text/javascript; charset=utf-8'}[filename])
            if not self.authorized():
                return self.respond({'error': _msg('py.dashboard.message.3')}, 403)
            body = {}
            if method == 'POST':
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError(_msg('ui.invalid.request.size.attachments.must.be.mb.or'))
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError(_msg('py.asset_store.message.5'))
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            result = self.route(method, route, query, body)
            self.respond(result, content_type='application/zip' if isinstance(result, bytes) else 'application/json; charset=utf-8')
        except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
            self.respond(error_payload(error), 400)
        except ConnectionRecoveryError as error:
            self.respond({**error_payload(error), 'detail': error.detail,
                          'restart_required': error.restart_required}, 503)
        except (RpcError, OSError, sqlite3.Error) as error:
            self.respond(error_payload(error), 503)
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
                return {'available': False, 'message': _msg('ui.sign.in.to.codex.to.view.usage')}
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
            raise ValueError(_msg('py.dashboard.message.4'))
        project_id, action = parts[2:]
        project = app.state.project(project_id)
        root = Path(project['path'])
        app.dashboard_origin = f'http://127.0.0.1:{self.server.server_port}'
        if action.startswith(('creator', 'content-', 'story-', 'feedback-', 'checkpoint-', 'variant-')) or action == 'game-export':
            from creator_api import route as creator_route
            return creator_route(self, method, project_id, action, query, body)
        if action == 'target' and method == 'GET':
            return target(root, query.get('kind'), query.get('id'))
        if action == 'context' and method == 'GET':
            return context_search(root, query.get('q', ''))
        if action == 'discards' and method == 'GET':
            return {'candidates': Discards(root).list()}
        if action == 'discard-propose' and method == 'POST':
            return Discards(root).propose(body.get('path'), body.get('reason'), body.get('record_ids'))
        if action == 'discard-action' and method == 'POST':
            if body.get('confirmation') != f'{body.get("action")}:{body.get("id")}:{body.get("digest")}':
                raise ValueError(_msg('py.dashboard.explicit.selection.of.this.file.and.action.is'))
            Discards(root).act(body.get('id'), body.get('action'), body.get('digest'))
            return {'candidates': Discards(root).list()}
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
                raise ValueError(_msg('ui.this.asset.has.changed.refresh.before.saving.again'))
            request = body.get('text')
            if not isinstance(request, str) or not request.strip() or len(request) > 10000:
                raise ValueError(_msg('ui.enter.a.change.request.of.characters'))
            session = app.session(project_id)
            evidence = context_search(root, request, target(root, 'asset', asset['id']))
            text = session.instructions.render('work_request', request=request, context=json.dumps(evidence, ensure_ascii=False))
            session.send_message(text, instruction_section='work_request', display_text=f'{asset["name"]}\n{request}')
            app.state.merge_info(project_id, last_context=evidence, last_request=request)
            app.state.event(project_id, 'request_context', context=evidence)
            return {'accepted': True, 'working': bool(session.turn_id), 'activity': session.activity_status()}
        if action == 'asset-media' and method == 'GET':
            store = AssetStore(root)
            asset = store.get(query.get('id'))
            if query.get('path') not in asset['files']:
                raise ValueError(_msg('ui.only.files.registered.to.this.asset.can.be'))
            path = store.file(query['path'])
            types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                     '.webp': 'image/webp', '.avif': 'image/avif', '.svg': 'image/svg+xml', '.bmp': 'image/bmp',
                     '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.flac': 'audio/flac'}
            if path.suffix.lower() not in types or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError(_msg('ui.preview.supports.image.and.sound.files.up.to'))
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
                    'work_status': session.work_status() if session else None,
                    'asset_counts': {status: sum(a['status'] == status for a in assets) for status in ('temporary', 'proposed')},
                    'progress': app.planning.progress(project_id)}
        if method == 'GET' and action == 'progress':
            return app.planning.progress(project_id)
        if method == 'POST' and action == 'summary':
            return app.planning.open_summary(project_id)
        if method == 'POST' and action == 'summary-more':
            session = app.sessions.get(project_id)
            if session and session.turn_id:
                raise ValueError(_msg('ui.wait.for.the.current.response.to.finish'))
            result = app.planning.more(project_id, body.get('fingerprint'))
            if session and not session.closed:
                session.send_instruction('planning_more')
            return result
        if method == 'POST' and action == 'summary-start':
            session = app.session(project_id)
            with session.lock:
                if session.turn_id:
                    raise ValueError(_msg('ui.wait.for.the.current.response.to.finish'))
                version = app.planning.approve(project_id, body.get('fingerprint'))
                new_project.ensure_production_support(root)
                session.send_instruction('production_start', version=version)
                for question in app.state.questions(project_id):
                    app.state.answer_question(project_id, question['id'])
                app.planning.delivered(project_id)
                return app.planning.progress(project_id)
        if method == 'POST' and action == 'connect':
            return {'info': app.connect(project_id, body.get('model'), body.get('effort'), body.get('service_tier'),
                                        restart=body.get('restart') is True)}
        if method == 'POST' and action == 'model':
            model, effort = app.model_settings(body.get('model'), body.get('effort'))
            tier = app.service_tier(model, body.get('service_tier'))
            app.session(project_id).change_model(model, effort, tier)
            return {'model': model, 'effort': effort, 'service_tier': tier}
        if method == 'POST' and action == 'message':
            attachments = [safe_file(root, p) for p in body.get('attachments', [])]
            if any(p.parent != root / 'uploads' or not p.is_file() for p in attachments):
                raise ValueError(_msg('ui.only.files.uploaded.to.this.project.can.be'))
            text = body.get('text', '')
            if not isinstance(text, str) or len(text) > 10000:
                raise ValueError(_msg('py.dashboard.message.5'))
            selected = None
            if body.get('target'):
                requested = body['target']
                if not isinstance(requested, dict):
                    raise ValueError(_msg('py.dashboard.a.request.target.object.is.required'))
                selected = target(root, requested.get('kind'), requested.get('id'))
                if selected['fingerprint'] != requested.get('fingerprint'):
                    raise ValueError(_msg('py.dashboard.the.request.target.changed.select.it.again.before'))
            if (not selected and not attachments and text.strip().rstrip('.!').lower() in (
                    _msg('py.dashboard.message.6'), _msg('py.dashboard.message.7'), _msg('py.dashboard.message.8'), '/development')
                    and not app.planning.progress(project_id)['spec_version']):
                app.state.event(project_id, 'user', text=text)
                return {'accepted': True, 'progress': app.planning.open_summary(project_id)}
            if attachments:
                text += _msg('py.dashboard.message.9') + '\n'.join(p.relative_to(root).as_posix() for p in attachments)
            session = app.session(project_id)
            if selected or (root / 'SPEC.md').is_file():
                evidence = context_search(root, text, selected)
                prompt = session.instructions.render('work_request', request=text, context=json.dumps(evidence, ensure_ascii=False))
                session.send_message(prompt, attachments=attachments, instruction_section='work_request',
                                     display_text=(f'[{selected["id"]}]\n' if selected else '') + text)
                app.state.merge_info(project_id, last_context=evidence, last_request=text)
                app.state.event(project_id, 'request_context', context=evidence)
            else:
                session.send_message(text, attachments=attachments)
                app.state.merge_info(project_id, last_request=text)
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
                    raise ValueError(_msg('ui.the.editor.supports.text.files.up.to.mb'))
                data = path.read_bytes()
                try:
                    text = data.decode('utf-8-sig')
                except UnicodeDecodeError:
                    raise ValueError(_msg('ui.this.is.not.a.utf.text.file')) from None
                return {'text': text, 'digest': hashlib.sha256(data).hexdigest()}
            if path.name == '.project' or '.harness' in path.relative_to(root).parts:
                raise ValueError(_msg('ui.project.runtime.settings.cannot.be.changed.in.the'))
            content = body.get('text')
            if not isinstance(content, str) or len(content.encode('utf-8')) > 2 * 1024 * 1024:
                raise ValueError(_msg('ui.only.utf.text.up.to.mb.can.be'))
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if current != body.get('digest'):
                raise ValueError(_msg('ui.the.file.changed.reopen.it.to.see.the'))
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
            if ((action == 'attachment' and path.parent not in (root / 'uploads', root / 'feedback')) or path.suffix.lower() not in types
                    or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024):
                raise ValueError(_msg('ui.only.project.images.up.to.mb.can.be'))
            return {'mime': types[path.suffix.lower()], 'data': base64.b64encode(path.read_bytes()).decode('ascii')}
        if method == 'POST' and action == 'upload':
            name = body.get('name', '')
            if not isinstance(name, str) or not name or '/' in name or '\\' in name or ':' in name:
                raise ValueError(_msg('ui.a.valid.filename.is.required'))
            data = base64.b64decode(body['data'], validate=True)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError(_msg('ui.attachments.must.be.mb.or.smaller'))
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
        raise ValueError(_msg('py.dashboard.message.10'))

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=_msg('cli.dashboard.local.only.game.creation.dashboard.run.start.bat'))
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    app = App()
    server = LocalServer(('127.0.0.1', args.port), Handler)
    server.app = app
    url = f'http://127.0.0.1:{server.server_port}/#token={app.token}'
    print(_msg('py.dashboard.codex.vibe.game.creator' ,url), flush=True)
    print(_msg('py.dashboard.message.11'), flush=True)
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
