"""Project routing, UI protocol, and real Codex filesystem isolation checks."""
from contextlib import closing
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from codex_bridge import CodexRpc, RpcError, sandbox_policy
from dashboard import App, Handler, LocalServer
from dashboard_session import ProjectSession, QUESTION_TOOL
from dashboard_state import State
from instruction_bundle import InstructionBundle

STARTUP_PROMPT = InstructionBundle().render("startup")
from dashboard_state import safe_file
import new_project


class FakeRpc:
    """Model-free protocol peer; never fabricates an AI answer."""
    instances = []

    def __init__(self, home, cwd, on_event=None, on_request=None):
        self.cwd, self.event, self.request = Path(cwd), on_event, on_request
        self.calls, self.responses = [], []
        self.__class__.instances.append(self)

    def call(self, method, params):
        self.calls.append((method, params))
        if method in ('thread/start', 'thread/resume'):
            return {'thread': {'id': params.get('threadId', 'thread-test'), 'turns': []},
                    'cwd': str(self.cwd), 'sandbox': sandbox_policy(self.cwd),
                    'approvalPolicy': 'never', 'model': 'test-model',
                    'instructionSources': [str(self.cwd / 'AGENTS.md')]}
        if method == 'turn/start':
            return {'turn': {'id': 'turn-' + str(len(self.calls))}}
        return {}

    def respond(self, request_id, result):
        self.responses.append((request_id, result))

    def deny_request(self, message):
        CodexRpc.deny_request(self, message)

    def close(self):
        pass


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harness-dashboard-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = new_project.installed_runtime()
        self.app = App(self.root / 'state', self.root / 'GameProjects', self.runtime)
        self.addCleanup(self.app.close)

    def create(self, name='한글 게임'):
        path = new_project.create_project(self.app.state.projects_root, name=name, runtime=self.runtime)
        return self.app.state.add(path)

    def server(self):
        server = LocalServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, route, body=None, *, authorized=True, origin=None):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = 'Bearer ' + self.app.token
        if origin:
            headers['Origin'] = origin
        request = Request(f'http://127.0.0.1:{server.server_port}/api/{route}',
                          data=None if body is None else json.dumps(body).encode(), headers=headers)
        with urlopen(request, timeout=10) as result:
            return json.load(result)

    def test_http_creation_and_project_file_boundary(self):
        server = self.server()
        self.assertEqual(server.server_address[0], '127.0.0.1')
        self.assertFalse(self.app.state.projects_root.exists())
        self.assertEqual(self.request(server, 'projects')['projects'], [])
        for headers in ({'authorized': False}, {'origin': 'https://unrelated.example'}):
            with self.assertRaises(HTTPError) as error:
                self.request(server, 'projects', **headers)
            self.assertEqual(error.exception.code, 403)
        first = self.request(server, 'projects', {'name': '../같은 이름'})['project']
        second = self.request(server, 'projects', {'name': '../같은 이름'})['project']
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(Path(first['path']).parent, self.app.state.projects_root)
        route = f'projects/{first["id"]}/file'
        for path in ('../escape.txt', str(self.root / 'escape.txt'), 'file.txt:stream'):
            with self.assertRaises(HTTPError):
                self.request(server, route, {'path': path, 'text': 'no', 'digest': None})
        self.request(server, route, {'path': 'game.txt', 'text': '한글 저장', 'digest': None})
        self.assertEqual((Path(first['path']) / 'game.txt').read_text(encoding='utf-8'), '한글 저장')
        self.assertFalse((Path(second['path']) / 'game.txt').exists())
        self.assertFalse((self.root / 'escape.txt').exists())
        with self.assertRaises(HTTPError):
            self.request(server, route, {'path': 'game.txt', 'text': 'stale', 'digest': None})

    def test_image_attachment_preview_and_conversation_history(self):
        server = self.server()
        project = self.create()
        other = self.create('다른 프로젝트')
        route = f'projects/{project["id"]}/'
        data = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1sAAAAASUVORK5CYII='
        uploaded = self.request(server, route + 'upload', {'name': '참고.png', 'data': data})['path']
        preview = self.request(server, route + 'attachment?path=' + quote(uploaded))
        self.assertEqual(preview, {'mime': 'image/png', 'data': data})
        for request_route, authorized in (
                (route + 'attachment?path=' + quote(uploaded), False),
                (f'projects/{other["id"]}/attachment?path=' + quote(uploaded), True),
                (route + 'attachment?path=../outside.png', True),
                (route + 'attachment?path=AGENTS.md', True)):
            with self.assertRaises(HTTPError):
                self.request(server, request_route, authorized=authorized)
        with patch('dashboard_session.CodexRpc', FakeRpc):
            session = ProjectSession(self.app.state, project['id'], self.root / 'codex')
            self.app.sessions[project['id']] = session
            session.connect()
            self.request(server, route + 'message', {'text': '이 이미지 참고', 'attachments': [uploaded]})
            inputs = session.rpc.calls[-1][1]['input']
            self.assertIn({'type': 'localImage', 'path': str(Path(project['path']) / uploaded)}, inputs)
            events = self.app.state.events(project['id'], 0)
            event = next(e for e in reversed(events) if e['kind'] == 'user')
            self.assertEqual(event['attachments'], [uploaded])
            self.assertEqual((Path(project['path']) / uploaded).read_bytes(), base64.b64decode(data))

    def test_activity_tracks_real_items_and_clears_on_turn_end(self):
        project = self.create()
        with patch('dashboard_session.CodexRpc', FakeRpc):
            session = ProjectSession(self.app.state, project['id'], self.root / 'codex')
            self.app.sessions[project['id']] = session
            session.connect()
            session.on_event('turn/started', {'turn': {'id': 'activity-turn'}})
            self.assertEqual(session.activity_status(), 'working')
            for item_type, expected in (('reasoning', 'thinking'), ('agentMessage', 'responding'),
                                        ('fileChange', 'editing'), ('webSearch', 'web_search'),
                                        ('mcpToolCall', 'tool'), ('plan', 'planning')):
                item = {'id': item_type, 'type': item_type}
                session.on_event('item/started', {'item': item})
                self.assertEqual(session.activity_status(), expected)
                session.on_event('item/completed', {'item': item})
                self.assertEqual(session.activity_status(), 'working')
            read = {'id': 'read', 'type': 'commandExecution', 'commandActions': [{'type': 'read'}]}
            session.on_event('item/started', {'item': read})
            session.on_event('item/started', {'item': {'id': 'edit', 'type': 'fileChange'}})
            self.assertEqual(session.activity_status(), 'editing')
            session.on_event('item/completed', {'item': {'id': 'edit', 'type': 'fileChange'}})
            self.assertEqual(session.activity_status(), 'reading')
            session.live_questions['question'] = 'rpc-request'
            self.assertEqual(session.activity_status(), 'waiting')
            session.live_questions.clear()
            server = self.server()
            route = f'projects/{project["id"]}/'
            self.assertEqual(self.request(server, route + 'events')['activity'], 'reading')
            self.assertEqual(self.request(server, route + 'message', {'text': '일반 채팅'})['activity'], 'reading')
            session.on_event('turn/completed', {'turn': {'id': 'activity-turn', 'status': 'completed'}})
            self.assertIsNone(session.activity_status())
            self.assertFalse(session.active_items)
            session.on_event('turn/started', {'turn': {'id': 'next-turn'}})
            self.assertEqual(session.activity_status(), 'working')
            session.on_event('connection/closed', {})
            self.assertIsNone(session.activity_status())

    def test_chat_history_migration_paging_and_live_cursor(self):
        project = self.create()
        other = self.create('다른 대화')
        pid = project['id']
        # Simulate an old DB with long streaming replies and no display index.
        original = []
        for number in range(35):
            original.append({'kind': 'user', 'text': f'질문 {number}'})
            original.extend({'kind': 'agent_delta', 'item_id': f'a{number}', 'text': '조각 '}
                            for _ in range(20))
            original.append({'kind': 'item', 'phase': 'completed', 'item': {
                'type': 'agentMessage', 'id': f'a{number}', 'text': f'완성된 답변 {number}'}})
        original.extend([{'kind': 'user', 'text': '진행 중인 질문'},
                         {'kind': 'agent_delta', 'item_id': 'active', 'text': '아직 '},
                         {'kind': 'agent_delta', 'item_id': 'active', 'text': '진행 중'}])
        with closing(self.app.state.connect()) as db:
            db.executemany('INSERT INTO events(project_id,data) VALUES(?,?)',
                           [(pid, json.dumps(e, ensure_ascii=False)) for e in original])
            db.execute("DELETE FROM settings WHERE key='chat_history_version'")
            db.commit()
        self.app.state = State(self.app.state.folder, self.app.state.projects_root)
        self.app.state.event(other['id'], 'user', text='섞이면 안 되는 메시지')
        server = self.server()
        route = f'projects/{pid}/'
        latest = self.request(server, route + 'history')
        self.assertEqual(len(latest['events']), 30)
        self.assertTrue(latest['has_more'])
        self.assertEqual(latest['events'][-1]['item']['text'], '아직 진행 중')
        self.assertFalse(any(e['kind'] == 'agent_delta' for e in latest['events']))
        self.app.state.event(pid, 'agent_delta', item_id='active', text=' 이어짐')
        live = self.request(server, route + f'events?after={latest["cursor"]}')['events']
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]['text'], ' 이어짐')
        self.assertEqual(self.app.state.history(pid)['events'][-1]['item']['text'], '아직 진행 중 이어짐')
        seen = list(latest['events'])
        page = latest
        while page['has_more']:
            page = self.request(server, route + f'history?before={page["before"]}')
            seen = page['events'] + seen
        self.assertEqual(len(seen), 72)
        self.assertEqual(len({event['seq'] for event in seen}), 72)
        self.assertEqual([e['text'] for e in seen if e['kind'] == 'user'],
                         [f'질문 {n}' for n in range(35)] + ['진행 중인 질문'])
        with closing(self.app.state.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events WHERE project_id=?', (pid,)).fetchone()[0],
                             len(original) + 1)
        with self.assertRaises(HTTPError):
            self.request(server, route + 'history', authorized=False)

    def test_junction_and_marker_cannot_redirect_project(self):
        project = self.create()
        root = Path(project['path'])
        outside = self.root / 'outside'
        outside.mkdir()
        link = root / 'linked'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
            self.addCleanup(lambda: link.rmdir() if link.exists() else None)
        else:
            link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_file(root, 'linked/escape.txt')
        (root / '.project').write_text('{"project_id":"different"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.app.state.project(project['id'])

    def test_persistent_chat_choices_and_denied_escalation(self):
        project = self.create()
        with patch('dashboard_session.CodexRpc', FakeRpc):
            session = ProjectSession(self.app.state, project['id'], self.root / 'codex')
            session.connect()
            rpc = session.rpc
            starts = [p for m,p in rpc.calls if m == 'turn/start']
            self.assertEqual(starts[0]['input'][0]['text'], STARTUP_PROMPT)
            self.assertEqual(rpc.calls[0][1]['dynamicTools'], [{**QUESTION_TOOL, 'description': InstructionBundle().render('question_tool')}])
            first_turn = session.turn_id
            session.on_event('turn/completed', {'turn': {'id': first_turn, 'status': 'completed'}})
            session.send_message('안녕하세요')
            session.on_request({'id': 99, 'method': 'item/tool/call', 'params': {
                'threadId': session.thread_id, 'turnId': session.turn_id, 'callId': 'choice-1',
                'tool': 'request_user_input_async', 'arguments': {'questions': [
                    {'title': '조작 방식은?', 'options': ['키보드', '터치']}]}}})
            self.assertTrue(rpc.responses[-1][1]['success'])
            self.assertEqual(self.app.state.questions(project['id'])[0]['questions'][0]['options'], ['키보드', '터치'])
            session.answer('choice-1', ['키보드'])
            self.assertEqual(rpc.calls[-1][0], 'turn/steer')
            self.assertIn('"user_quote": "키보드"', rpc.calls[-1][1]['input'][0]['text'])
            self.assertEqual(self.app.state.questions(project['id']), [])
            session.change_model('selected-model')
            active = session.turn_id
            session.on_event('turn/completed', {'turn': {'id': active, 'status': 'completed'}})
            session.send_message('새 모델로 이어서')
            self.assertEqual(rpc.calls[-1][1]['model'], 'selected-model')
            self.assertEqual(rpc.calls[-1][1]['threadId'], session.thread_id)
            usage = {'last': {'inputTokens': 1200, 'outputTokens': 100, 'totalTokens': 1300},
                     'total': {'totalTokens': 5000}, 'modelContextWindow': 10000}
            session.on_event('thread/tokenUsage/updated', {'threadId': session.thread_id, 'tokenUsage': usage})
            self.assertEqual(self.app.state.project(project['id'])['info']['token_usage'], usage)
            session.on_request({'id': 100, 'method': 'item/permissions/requestApproval', 'params': {
                'threadId': session.thread_id, 'permissions': {'fileSystem': {'write': [str(self.root)]}}}})
            self.assertEqual(rpc.responses[-1], (100, {'permissions': {}, 'scope': 'turn'}))
            session.close()
            resumed = ProjectSession(self.app.state, project['id'], self.root / 'codex')
            resumed.connect()
            self.assertEqual(resumed.rpc.calls[0][0], 'thread/resume')
            self.assertFalse(any(m == 'turn/start' for m,_ in resumed.rpc.calls))

    def test_work_and_user_record_contracts(self):
        project = Path(self.create()['path'])
        script = str(project / '.harness/decisions.py')
        def call(kind, *args, payload=None, cwd=project):
            return subprocess.run([self.runtime['python'], '-B', script, kind, *args], cwd=cwd,
                                  input=json.dumps(payload, ensure_ascii=False) if payload else None,
                                  encoding='utf-8', capture_output=True)
        user = {'category': 'genre', 'topic': '장르', 'decision': '퍼즐', 'status': 'confirmed',
                'user_quote': '퍼즐로 하자', 'assistant_reply': '퍼즐로 기록합니다.', 'ai_role': 'explanation'}
        work = ['add','--area','gameplay','--decision','격자 판정','--reason','충돌 판정을 단순화한다',
                '--alternatives','없음','--evidence-type','none','--source','ai_judgment']
        for kind, args, payload in [('user',['add'],user), ('work',work,None)]:
            with self.subTest(kind=kind):
                self.assertNotEqual(call(kind,*args,payload=payload,cwd=self.root).returncode,0)
                invalid = {**user,'category':'invalid'} if kind=='user' else None
                bad_args = ['add'] if kind=='user' else [*work[:2],'invalid',*work[3:]]
                self.assertNotEqual(call(kind,*bad_args,payload=invalid).returncode,0)
                saved = call(kind,*args,payload=payload)
                self.assertEqual(saved.returncode,0,saved.stderr)
                conflict = {**user,'decision':'액션'} if kind=='user' else None
                self.assertNotEqual(call(kind,*args,payload=conflict).returncode,0)
                listed = call(kind, 'list', *(['--area', 'gameplay'] if kind == 'work' else []))
                self.assertEqual(listed.returncode,0,listed.stderr)
                self.assertIn('퍼즐' if kind=='user' else '격자 판정',listed.stdout)

    def test_native_questions_recovery_effort_and_resume_without_prompt(self):
        project = self.create()
        pid = project['id']
        item = {'type': 'agentMessage', 'id': 'call-native', 'delivery': 'async',
                'text': '조작 방식은?', 'questions': [{'title': '조작 방식은?', 'options': ['키보드', '터치']}]}
        # Reproduce the real CLI's notification, which never calls item/tool/call.
        with patch('dashboard_session.CodexRpc', FakeRpc):
            session = ProjectSession(self.app.state, pid, self.root / 'codex')
            session.connect(effort='high')
            self.assertEqual(session.rpc.calls[0][1]['config']['model_reasoning_effort'], 'high')
            self.assertEqual(session.rpc.calls[1][1]['effort'], 'high')
            self.assertNotIn('최근 10건', STARTUP_PROMPT)
            session.on_event('item/completed', {'threadId': session.thread_id, 'item': item})
            self.assertEqual(self.app.state.questions(pid)[0]['mode'], 'native_async')
            session.answer(item['id'], ['터치'])
            reply = session.rpc.calls[-1][1]['input'][0]['text']
            payload = json.loads(reply.split('\n')[1])[0]
            self.assertEqual(payload['answer'], '터치')
            self.assertEqual(json.loads(payload['questionItemId']), ['request_user_input_async', 'call-native', 0])
            self.app.state.recover_questions()
            self.assertEqual(self.app.state.questions(pid), [])
            # An existing thread must not get a prompt even if its old startup failed.
            self.app.state.update(pid, startup_sent=0)
            resumed = ProjectSession(self.app.state, pid, self.root / 'codex')
            resumed.connect()
            self.assertFalse(any(m == 'turn/start' for m, _ in resumed.rpc.calls))
            self.assertEqual(resumed.requested_effort, 'high')
            resumed.change_model('test-model', 'low')
            resumed.send_message('이어 하기')
            self.assertEqual(resumed.rpc.calls[-1][1]['effort'], 'low')
        self.app.state.event(pid, 'item', phase='completed', item={**item, 'id': 'missing-card'})
        self.app.state.recover_questions()
        self.app.state.recover_questions()
        self.assertEqual([q['id'] for q in self.app.state.questions(pid)], ['missing-card'])

    def test_automatic_sandbox_and_supported_efforts(self):
        rpc = Mock()
        rpc.call.side_effect = lambda method, *args, **kwargs: (
            {'status': 'notConfigured'} if method == 'windowsSandbox/readiness' else
            {'data': [{'model': 'test', 'isDefault': True, 'defaultReasoningEffort': 'medium',
                       'supportedReasoningEfforts': [{'reasoningEffort': 'medium'}, {'reasoningEffort': 'high'}]}]}
            if method == 'model/list' else {})
        with patch.object(self.app, 'auth', return_value=rpc), patch('dashboard.os.name', 'nt'):
            self.app.prepare_sandbox()
            self.app.prepare_sandbox()
            self.assertEqual(sum(c.args[0] == 'windowsSandbox/setupStart' for c in rpc.call.call_args_list), 1)
            self.app.auth_event('windowsSandbox/setupCompleted', {'success': False, 'error': 'cancelled'})
            self.app.prepare_sandbox()
            self.assertEqual(sum(c.args[0] == 'windowsSandbox/setupStart' for c in rpc.call.call_args_list), 1)
            self.app.prepare_sandbox(retry=True)
            self.assertEqual(sum(c.args[0] == 'windowsSandbox/setupStart' for c in rpc.call.call_args_list), 2)
            self.assertEqual(self.app.model_settings(), ('test', 'medium'))
            self.assertEqual(self.app.model_settings('test', 'high'), ('test', 'high'))
            with self.assertRaises(ValueError):
                self.app.model_settings('test', 'ultra')

    def test_instruction_source_snapshot_and_delivery_trace(self):
        import hashlib
        from instruction_bundle import SOURCE
        source = self.root / 'dashboard.toml'
        original = SOURCE.read_bytes()
        source.write_bytes(original)
        bundle = InstructionBundle(source)
        original_version = bundle.source['version']
        project = self.create()
        with patch('dashboard_session.CodexRpc', FakeRpc), patch('dashboard_session.InstructionBundle', return_value=bundle):
            session = ProjectSession(self.app.state, project['id'], self.root / 'codex')
            session.connect()
            self.assertEqual(session.rpc.calls[0][1]['developerInstructions'], bundle.render('host'))
            source.write_bytes(original.replace(f'version = {original_version}'.encode(),
                                                f'version = {original_version + 1}'.encode()))
            session.send_instruction('production_start', version=7)
            traces = [e for e in self.app.state.events(project['id']) if e['kind'] == 'instruction_sent']
            self.assertEqual([e['section'] for e in traces], ['host', 'question_tool', 'startup', 'production_start'])
            for trace in traces:
                self.assertEqual(trace['path'], str(source))
                self.assertEqual(trace['sha256'], hashlib.sha256(original).hexdigest())
                self.assertEqual(trace['version'], original_version)
                self.assertEqual(trace['text_sha256'], hashlib.sha256(trace['text'].encode()).hexdigest())
                self.assertEqual(trace['thread_id'], session.thread_id)
            self.assertIn('SPEC.md 버전 7', traces[-1]['text'])
            self.assertEqual(traces[-1]['text'], session.rpc.calls[-1][1]['input'][0]['text'])
            self.assertEqual(traces[-1]['turn_id'], session.turn_id)
            with patch.object(session.rpc, 'call', side_effect=RpcError('delivery failed')):
                with self.assertRaises(RpcError):
                    session.send_instruction('planning_more')
            self.assertEqual(len([e for e in self.app.state.events(project['id']) if e['kind'] == 'instruction_sent']), 4)
        reloaded = InstructionBundle(source)
        self.assertEqual(reloaded.source['version'], original_version + 1)
        self.assertNotEqual(reloaded.source['sha256'], bundle.source['sha256'])


@unittest.skipUnless(os.name == 'nt', 'Native Windows sandbox integration')
class NativeSandboxTests(unittest.TestCase):
    def test_inside_write_outside_deny_and_shared_runtime(self):
        runtime = new_project.installed_runtime()
        with tempfile.TemporaryDirectory(prefix='harness-native-test-') as folder:
            root = Path(folder).resolve()
            project = new_project.create_project(root/'GameProjects', name='임시 검사', runtime=runtime)
            sibling = new_project.create_project(root/'GameProjects', name='다른 게임', runtime=runtime)
            # Use the existing, already-provisioned Windows sandbox for this local
            # no-inference test. Production uses its own Codex home and setup UI.
            rpc = CodexRpc(Path.home()/'.codex', project)
            try:
                if rpc.call('windowsSandbox/readiness')['status'] != 'ready':
                    self.skipTest('Windows sandbox setup is required')
                command = [runtime['python'], '-B', '-c',
                    'from pathlib import Path; Path("inside.txt").write_text("ok"); '
                    'Path("../outside.txt").write_text("not allowed")']
                with self.assertRaises(RpcError):
                    rpc.call('command/exec', {'command':command, 'cwd':str(project),
                                             'sandboxPolicy':sandbox_policy(project), 'timeoutMs':20000})
                self.assertTrue((project/'inside.txt').is_file())
                self.assertFalse((project.parent/'outside.txt').exists())
                denied = rpc.call('command/exec', {
                        'command':[runtime['python'],'-B','-c',
                            'from pathlib import Path; import sys; Path(sys.argv[1]).mkdir()', str(sibling/'outside-folder')],
                        'cwd':str(project),'sandboxPolicy':sandbox_policy(project),'timeoutMs':20000})
                self.assertNotEqual(denied['exitCode'], 0)
                self.assertFalse((sibling/'outside-folder').exists())
                result = rpc.call('command/exec', {
                    'command':[runtime['python'],'-B',str(project/'.harness/decisions.py'),'user','list'],
                    'cwd':str(project),'sandboxPolicy':sandbox_policy(project),'timeoutMs':20000})
                self.assertEqual(result['exitCode'],0,result)
                self.assertEqual(json.loads(result['stdout'])['records'],[])
                payload = {'category':'genre','topic':'장르','decision':'퍼즐', 'status':'confirmed',
                           'user_quote':'퍼즐로 하자', 'assistant_reply':'퍼즐로 기록합니다.', 'ai_role':'explanation'}
                (project/'input.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                saved = rpc.call('command/exec', {
                    'command':[runtime['python'],'-B',str(project/'.harness/decisions.py'),
                               'user','add','--input','input.json'],
                    'cwd':str(project),'sandboxPolicy':sandbox_policy(project),'timeoutMs':30000})
                self.assertEqual(saved['exitCode'],0,saved)
                self.assertEqual(json.loads(saved['stdout'])['saved']['decision'],'퍼즐')
            finally:
                rpc.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
