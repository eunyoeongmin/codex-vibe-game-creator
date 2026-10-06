"""Long-lived project conversations, asynchronous choices, and fixed sandbox scope."""
from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid

from codex_bridge import CodexRpc, RpcError, sandbox_policy
from instruction_bundle import InstructionBundle
from localization import LANGUAGES

QUESTION_TOOL = {
    'type': 'function', 'name': 'request_user_input_async',
    'inputSchema': {'type': 'object', 'properties': {'questions': {
        'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': {
            'type': 'object', 'properties': {'title': {'type': 'string'},
                'options': {'type': 'array', 'minItems': 2, 'maxItems': 4, 'items': {'type': 'string'}}},
            'required': ['title'], 'additionalProperties': False}}},
        'required': ['questions'], 'additionalProperties': False}}



class ProjectSession:
    def __init__(self, state, project_id, codex_home):
        self.state, self.id = state, project_id
        self.project = state.project(project_id)
        self.root = Path(self.project['path'])
        self.lock = threading.RLock()
        self.turn_id = None
        self.activity_lock = threading.Lock()
        self.active_items = {}
        self.thread_id = self.project['thread_id']
        self.live_questions = {}
        self.finished_turns = deque(maxlen=128)
        self.starting_bootstrap = False
        self.bootstrap_turn = None
        self.bootstrap_failed = False
        self.requested_model = self.project.get('model')
        self.requested_effort = self.project.get('info', {}).get('requested_effort')
        self.requested_service_tier = self.project.get('info', {}).get('requested_service_tier', 'default')
        self.closed = False
        self.planning = None
        self.instructions = InstructionBundle()
        self.requested_language = self.state.setting('language', 'ko')
        self.applied_language = None
        self.rpc = CodexRpc(codex_home, self.root, self.on_event, self.on_request)

    def connect(self, model=None, effort=None, service_tier=None):
        self.project = self.state.project(self.id)
        fresh = not self.thread_id
        self.requested_effort = effort or self.requested_effort
        self.requested_service_tier = service_tier or self.requested_service_tier
        config = {'sandbox_workspace_write.writable_roots': [self.root.as_posix()],
                  'sandbox_workspace_write.network_access': True,
                  'sandbox_workspace_write.exclude_tmpdir_env_var': True,
                  'sandbox_workspace_write.exclude_slash_tmp': True}
        params = {'cwd': str(self.root), 'runtimeWorkspaceRoots': [str(self.root)],
                  'serviceTier': self.requested_service_tier,
                  'approvalPolicy': 'never', 'sandbox': 'workspace-write',
                  'developerInstructions': self.instructions.render('host', language=LANGUAGES[self.requested_language]), 'config': config}
        if self.requested_effort:
            config['model_reasoning_effort'] = self.requested_effort
        if model or self.requested_model:
            params['model'] = model or self.requested_model
        if self.thread_id:
            params['threadId'] = self.thread_id
            result = self.rpc.call('thread/resume', params)
        else:
            params['dynamicTools'] = [{**QUESTION_TOOL, 'description': self.instructions.render('question_tool')}]
            result = self.rpc.call('thread/start', params)
        self.thread_id = result['thread']['id']
        self.applied_language = self.requested_language
        policy = result.get('sandbox', {})
        if policy.get('type') != 'workspaceWrite' or Path(result['cwd']).resolve() != self.root:
            self.close()
            raise RpcError('Codex가 요청한 프로젝트 쓰기 범위를 적용하지 않아 대화를 시작하지 않았습니다.')
        roots = {Path(p).resolve() for p in policy.get('writableRoots', [])}
        if any(p != self.root for p in roots) or result.get('approvalPolicy') != 'never':
            self.close()
            raise RpcError('프로젝트 밖 쓰기 권한이 감지되어 대화를 시작하지 않았습니다.')
        self.requested_model = result.get('model')
        self.requested_effort = result.get('reasoningEffort') or self.requested_effort
        info = {**self.project.get('info', {}), 'cwd': result['cwd'], 'instruction_sources': result.get('instructionSources', []),
                'sandbox': policy, 'writable_roots': [str(self.root)],
                'model': result.get('model'), 'requested_effort': self.requested_effort, 'thread_id': self.thread_id,
                'requested_service_tier': self.requested_service_tier,
                'instruction_bundle': self.instructions.source, 'language': self.applied_language}
        self.state.update(self.id, thread_id=self.thread_id, model=result.get('model'), info=info)
        self.state.event(self.id, 'connected', **info)
        self.record_instruction('host', params['developerInstructions'], method='thread/start' if fresh else 'thread/resume')
        if fresh:
            self.record_instruction('question_tool', params['dynamicTools'][0]['description'], method='thread/start')
        # Recover an active turn reported by app-server instead of starting a duplicate.
        for turn in result['thread'].get('turns', []):
            if turn.get('status') == 'inProgress':
                self.turn_id = turn['id']
        if fresh and not self.state.project(self.id)['startup_sent']:
            self.send_instruction('startup', startup=True)
        return info

    def record_instruction(self, section, text, *, method, turn_id=None):
        self.state.event(self.id, 'instruction_sent', **self.instructions.trace(section, text),
                         thread_id=self.thread_id, turn_id=turn_id, method=method,
                         sent_at=datetime.now(timezone.utc).isoformat())

    def send_instruction(self, section, *, startup=False, **values):
        return self.send_message(self.instructions.render(section, **values),
                                 startup=startup, instruction_section=section)

    def send_message(self, text, *, startup=False, attachments=None, instruction_section=None, display_text=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise ValueError('메시지는 1~100,000자로 입력하세요.')
        with self.lock:
            if not self.turn_id and self.thread_id and self.applied_language != self.requested_language:
                self.connect(self.requested_model, self.requested_effort)
            if startup:
                self.starting_bootstrap = True
                self.bootstrap_failed = False
            content = [{'type': 'text', 'text': text}]
            for path in attachments or []:
                if path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
                    content.append({'type': 'localImage', 'path': str(path)})
            active = self.turn_id
            if active:
                result = self.rpc.call('turn/steer', {
                    'threadId': self.thread_id, 'expectedTurnId': active, 'input': content})
            else:
                params = {
                    'threadId': self.thread_id, 'input': content, 'cwd': str(self.root),
                    'serviceTier': self.requested_service_tier,
                    'runtimeWorkspaceRoots': [str(self.root)],
                    'approvalPolicy': 'never', 'sandboxPolicy': sandbox_policy(self.root),
                    'clientUserMessageId': str(uuid.uuid4())}
                if self.requested_model:
                    params['model'] = self.requested_model
                if self.requested_effort:
                    params['effort'] = self.requested_effort
                result = self.rpc.call('turn/start', params)
                turn_id = result['turn']['id']
                self.turn_id = None if turn_id in self.finished_turns else turn_id
                if self.requested_model:
                    self.state.merge_info(self.id, model=self.requested_model)
            self.state.event(self.id, 'startup' if startup else 'user', text=text if display_text is None else display_text,
                             **({'attachments': [path.relative_to(self.root).as_posix()
                                                 for path in attachments]} if attachments else {}))
            if instruction_section:
                self.record_instruction(instruction_section, text, method='turn/steer' if active else 'turn/start',
                                        turn_id=active or result['turn']['id'])
            if startup:
                self.bootstrap_turn = result.get('turn', {}).get('id')
                self.starting_bootstrap = False
                self.state.update(self.id, startup_sent=0 if self.bootstrap_failed else 1)
            return result

    def change_model(self, model, effort=None, service_tier='default'):
        with self.lock:
            self.requested_model = model
            self.requested_effort = effort
            self.requested_service_tier = service_tier
            self.state.update(self.id, model=model)
            self.state.merge_info(self.id, requested_effort=effort, requested_service_tier=service_tier)
            self.state.event(self.id, 'model_selected', text=f'다음 작업부터 {model} / 추론 수준 {effort or "기본값"}을 사용합니다.')

    def interrupt(self):
        with self.lock:
            if self.turn_id:
                self.rpc.call('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id})

    def on_event(self, method, params):
        if params.get('threadId') and self.thread_id and params['threadId'] != self.thread_id:
            return
        if method == 'turn/started':
            with self.activity_lock:
                self.active_items.clear()
            self.turn_id = params['turn']['id']
            self.state.event(self.id, 'turn_started', turn_id=self.turn_id)
        elif method == 'turn/completed':
            turn = params['turn']
            self.finished_turns.append(turn['id'])
            if turn['status'] == 'failed' and (self.starting_bootstrap or turn['id'] == self.bootstrap_turn):
                self.bootstrap_failed = True
                self.state.update(self.id, startup_sent=0)
            if turn['id'] == self.turn_id:
                self.turn_id = None
                with self.activity_lock:
                    self.active_items.clear()
            self.state.event(self.id, 'turn_completed', status=turn['status'], error=turn.get('error'))
        elif method == 'item/agentMessage/delta':
            self.track_activity({'id': params['itemId'], 'type': 'agentMessage'})
            self.state.event(self.id, 'agent_delta', item_id=params['itemId'], text=params['delta'])
        elif method == 'item/commandExecution/outputDelta':
            self.state.event(self.id, 'command_delta', item_id=params['itemId'], text=params['delta'])
        elif method in ('item/started', 'item/completed'):
            item = params.get('item', {})
            self.track_activity(item, completed=method == 'item/completed')
            if (method == 'item/completed' and item.get('type') == 'agentMessage' and
                    '[[HARNESS:SHOW_SUMMARY]]' in item.get('text', '') and self.planning):
                self.planning.open_summary(self.id)
            if item.get('type') == 'agentMessage' and item.get('questions'):
                self.state.add_question(self.id, item['id'], {'questions': item['questions'], 'mode': 'native_async'})
            if item.get('type') in ('agentMessage', 'commandExecution', 'fileChange', 'plan', 'imageGeneration'):
                self.state.event(self.id, 'item', phase=method.split('/')[-1], item=item)
        elif method == 'turn/diff/updated':
            self.state.event(self.id, 'diff', text=params.get('diff', ''))
        elif method == 'thread/tokenUsage/updated':
            self.state.merge_info(self.id, token_usage=params['tokenUsage'])
        elif method == 'model/rerouted':
            self.state.merge_info(self.id, model=params.get('toModel'))
            self.state.event(self.id, 'model_selected', text=f'Codex 서비스가 모델을 {params.get("toModel")}로 변경했습니다: {params.get("reason", "")}')
        elif method == 'error':
            self.state.event(self.id, 'error', text=params.get('error', {}).get('message', str(params)))
        elif method == 'connection/closed':
            self.closed = True
            self.turn_id = None
            with self.activity_lock:
                self.active_items.clear()
            self.state.event(self.id, 'disconnected', text='Codex 연결이 종료되었습니다. 대화 연결 버튼으로 이어갈 수 있습니다.')

    def track_activity(self, item, *, completed=False):
        item_id = item.get('id')
        if not item_id:
            return
        kind = {'reasoning': 'thinking', 'agentMessage': 'responding', 'plan': 'planning',
                'commandExecution': 'command', 'fileChange': 'editing', 'webSearch': 'web_search',
                'mcpToolCall': 'tool', 'dynamicToolCall': 'tool', 'imageView': 'image_view',
                'imageGeneration': 'image_generation', 'contextCompaction': 'compacting'}.get(item.get('type'))
        if kind == 'command':
            actions = {action.get('type') for action in item.get('commandActions', [])}
            kind = {frozenset({'read'}): 'reading', frozenset({'search'}): 'file_search',
                    frozenset({'listFiles'}): 'listing'}.get(frozenset(actions), kind)
        with self.activity_lock:
            if completed:
                self.active_items.pop(item_id, None)
            elif kind:
                self.active_items.pop(item_id, None)
                self.active_items[item_id] = kind

    def activity_status(self):
        if self.closed or not self.turn_id:
            return None
        if self.live_questions:
            return 'waiting'
        with self.activity_lock:
            return next(reversed(self.active_items.values()), 'working')

    def on_request(self, message):
        params, method = message.get('params', {}), message['method']
        if params.get('threadId') and self.thread_id and params['threadId'] != self.thread_id:
            self.rpc.deny_request(message)
            return
        if method == 'item/tool/call' and params.get('tool') == 'request_user_input_async':
            try:
                args = params['arguments']
                if isinstance(args, str):
                    args = json.loads(args)
                questions = args['questions']
                if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
                    raise ValueError('질문은 1~3개여야 합니다.')
                for question in questions:
                    if not isinstance(question.get('title'), str) or not question['title'].strip():
                        raise ValueError('질문 제목이 필요합니다.')
                    options = question.get('options', [])
                    if options and (not 2 <= len(options) <= 4 or not all(isinstance(v, str) for v in options)):
                        raise ValueError('선택지는 문자열 2~4개여야 합니다.')
                self.state.add_question(self.id, params['callId'], {'questions': questions, 'mode': 'async'})
                output = {'accepted': True}
                success = True
            except (ValueError, KeyError, TypeError) as error:
                output, success = {'error': str(error)}, False
            self.rpc.respond(message['id'], {'contentItems': [
                {'type': 'inputText', 'text': json.dumps(output, ensure_ascii=False)}], 'success': success})
        elif method == 'item/tool/requestUserInput':
            question_id = str(params['itemId'])
            self.live_questions[question_id] = message['id']
            questions = [{'title': q['question'], 'key': q['id'],
                          'options': [o['label'] for o in q.get('options', [])]} for q in params['questions']]
            self.state.add_question(self.id, question_id, {'questions': questions, 'mode': 'blocking'})
        else:
            self.rpc.deny_request(message)
            self.state.event(self.id, 'blocked', text='추가 권한 요청을 거부했습니다. 현재 프로젝트 안에서 작업해야 합니다.', method=method)

    def answer(self, question_id, answers):
        with self.lock:
            question = next((q for q in self.state.questions(self.id) if q['id'] == question_id), None)
            if question is None:
                raise ValueError('이미 답했거나 존재하지 않는 질문입니다.')
            if not isinstance(answers, list) or len(answers) != len(question['questions']):
                raise ValueError('각 질문에 대한 응답이 필요합니다.')
            if any(not isinstance(a, str) or len(a) > 10000 for a in answers):
                raise ValueError('답변은 문자열이어야 합니다.')
            if question['mode'] == 'blocking' and question_id in self.live_questions:
                self.rpc.respond(self.live_questions.pop(question_id), {'answers': {
                    q['key']: {'answers': [a] if a else []} for q, a in zip(question['questions'], answers)}})
                for q, a in zip(question['questions'], answers):
                    self.state.event(self.id, 'user', text=f'{q["title"]}\n{a or "건너뛰기"}')
            elif question['mode'] == 'native_async':
                replies = [{'questionItemId': json.dumps(['request_user_input_async', question_id, i], separators=(',', ':')),
                            'question': q['title'], 'answer': a or '건너뛰기'}
                           for i, (q, a) in enumerate(zip(question['questions'], answers))]
                self.send_message('<send_user_message_question_reply>\n' +
                                  json.dumps(replies, ensure_ascii=False) + '\n</send_user_message_question_reply>')
            else:
                text = json.dumps({'type': 'question_answers', 'answers': [
                    {'question': q['title'], 'user_quote': a, 'skipped': not bool(a)}
                    for q, a in zip(question['questions'], answers)]}, ensure_ascii=False)
                self.send_message(text)
            self.state.answer_question(self.id, question_id)

    def close(self):
        self.closed = True
        self.rpc.close()
