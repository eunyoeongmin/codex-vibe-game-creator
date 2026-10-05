"""Codex app-server JSON-RPC transport. No terminal scraping or shell interpolation."""
from __future__ import annotations
from collections import deque
from functools import lru_cache
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading


@lru_cache(maxsize=1)
def find_codex():
    managed = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'GameHarness/tools/codex/bin/codex.exe'
    if managed.is_file():
        return str(managed)
    executable = shutil.which('codex.exe') or shutil.which('codex')
    if executable and Path(executable).suffix.lower() not in ('.cmd', '.bat', '.ps1'):
        return executable
    if os.name == 'nt':
        # The Windows desktop app ships the app-server CLI in resources/.
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            'Get-AppxPackage -Name OpenAI.Codex | Select-Object -ExpandProperty InstallLocation'],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for location in result.stdout.splitlines():
            candidate = Path(location.strip()) / 'app/resources/codex.exe'
            if candidate.is_file():
                return str(candidate)
    # Codex installed by the VS Code extension is also a native CLI binary.
    candidates = sorted((Path.home() / '.vscode/extensions').glob(
        'openai.chatgpt-*/bin/windows-x86_64/codex.exe'), reverse=True)
    if candidates:
        return str(candidates[0])
    if executable:
        npm_root = Path(executable).parent / 'node_modules/@openai'
        candidates = list(npm_root.glob('**/codex.exe'))
        if candidates:
            return str(candidates[0])
    raise FileNotFoundError('Codex를 찾을 수 없습니다. Codex 앱, CLI 또는 VS Code 확장을 설치한 뒤 다시 실행하세요.')


def sandbox_policy(project):
    return {'type': 'workspaceWrite', 'writableRoots': [str(Path(project).resolve())],
            'networkAccess': True, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}


class RpcError(RuntimeError):
    pass


class CodexRpc:
    def __init__(self, home, cwd, on_event=None, on_request=None, *, windows_sandbox='elevated'):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.cwd = Path(cwd).resolve()
        self.on_event = on_event or (lambda method, params: None)
        self.on_request = on_request or self.deny_request
        self.lock = threading.Lock()
        self.waiters = {}
        self.counter = 0
        self.errors = deque(maxlen=20)
        self.closed = False
        environment = os.environ.copy()
        for name in ('CODEX_PERMISSION_PROFILE', 'CODEX_SESSION_ID', 'CODEX_THREAD_ID',
                     'CODEX_INTERNAL_ORIGINATOR_OVERRIDE', 'CODEX_CI'):
            environment.pop(name, None)
        # An application-owned config prevents global MCP/desktop tools from bypassing
        # the game's filesystem sandbox. Login is managed by app-server in this home.
        environment['CODEX_HOME'] = str(self.home)
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        temporary = self.cwd / '.harness/tmp'
        if temporary.is_dir():
            environment['TMP'] = environment['TEMP'] = str(temporary)
        args = [find_codex(), 'app-server', '--listen', 'stdio://',
                '-c', 'approval_policy="never"', '-c', 'sandbox_mode="workspace-write"',
                '-c', 'sandbox_workspace_write.exclude_tmpdir_env_var=true',
                '-c', 'sandbox_workspace_write.exclude_slash_tmp=true',
                '-c', 'sandbox_workspace_write.network_access=true',
                '-c', 'windows.sandbox=' + json.dumps(windows_sandbox)]
        if (self.cwd / '.project').is_file():
            args += ['-c', 'sandbox_workspace_write.writable_roots=' + json.dumps([self.cwd.as_posix()]),
                     '-c', 'projects.' + json.dumps(self.cwd.as_posix()) + '.trust_level="trusted"']
        self.process = subprocess.Popen(args, cwd=self.cwd, env=environment,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, encoding='utf-8', errors='replace',
                                        bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()
        try:
            self.info = self.call('initialize', {'clientInfo': {
                'name': 'game_harness_dashboard', 'title': 'Game Harness', 'version': '0.1.0'},
                'capabilities': {'experimentalApi': True}}, timeout=30)
            self.send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def send(self, message):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RpcError('Codex 연결이 종료되었습니다. 프로젝트를 다시 열어 연결하세요.')
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.process.stdin.flush()

    def call(self, method, params=None, timeout=60):
        with self.lock:
            self.counter += 1
            request_id = self.counter
            result_queue = queue.Queue(maxsize=1)
            self.waiters[request_id] = result_queue
        try:
            self.send({'id': request_id, 'method': method, 'params': params or {}})
            try:
                message = result_queue.get(timeout=timeout)
            except queue.Empty:
                raise RpcError(f'Codex 응답 시간 초과: {method}') from None
            if 'error' in message:
                raise RpcError(message['error'].get('message', str(message['error'])))
            return message.get('result', {})
        finally:
            with self.lock:
                self.waiters.pop(request_id, None)

    def respond(self, request_id, result):
        self.send({'id': request_id, 'result': result})

    def deny_request(self, message):
        method = message['method']
        if method == 'item/permissions/requestApproval':
            self.respond(message['id'], {'permissions': {}, 'scope': 'turn'})
        elif method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            self.respond(message['id'], {'decision': 'decline'})
        elif method in ('execCommandApproval', 'applyPatchApproval'):
            self.respond(message['id'], {'decision': 'denied'})
        else:
            self.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Unsupported client request'}})

    def _reader(self):
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line)
                    if 'method' in message:
                        if 'id' in message:
                            self.on_request(message)
                        else:
                            self.on_event(message['method'], message.get('params', {}))
                    else:
                        with self.lock:
                            waiter = self.waiters.get(message.get('id'))
                        if waiter:
                            waiter.put_nowait(message)
                except Exception as error:
                    self.errors.append(str(error))
        finally:
            with self.lock:
                waiters = list(self.waiters.values())
            for waiter in waiters:
                try:
                    waiter.put_nowait({'error': {'message': 'Codex 프로세스가 종료되었습니다.'}})
                except queue.Full:
                    pass
            self.on_event('connection/closed', {})

    def _stderr(self):
        for line in self.process.stderr:
            self.errors.append(line.rstrip())

    def close(self):
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream:
                stream.close()
