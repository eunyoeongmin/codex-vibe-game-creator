"""Dashboard-owned project registry and conversation UI history."""
from __future__ import annotations
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import threading

from decisions import find_project, project_path


class State:
    def __init__(self, folder, projects_root):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.projects_root = Path(projects_root).resolve()
        self.db = self.folder / 'dashboard.sqlite'
        self.lock = threading.RLock()
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                    thread_id TEXT, model TEXT, info TEXT NOT NULL DEFAULT '{}',
                    startup_sent INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_project ON events(project_id, seq);
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    data TEXT NOT NULL, answered INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', ('projects_root', str(self.projects_root)))
            self.projects_root = Path(db.execute('SELECT value FROM settings WHERE key=?',
                                                ('projects_root',)).fetchone()[0]).resolve()
            db.commit()
        self.recover_questions()

    def recover_questions(self):
        # Older dashboards saved native question events without creating cards.
        # Recover only questions after the last user message, retaining answered IDs.
        with self.lock, closing(self.connect()) as db:
            pending = {}
            for row in db.execute('SELECT project_id,data FROM events ORDER BY seq'):
                event = json.loads(row['data'])
                pid = row['project_id']
                if event.get('kind') == 'user':
                    pending[pid] = {}
                item = event.get('item', {})
                if item.get('type') == 'agentMessage' and item.get('questions'):
                    pending.setdefault(pid, {})[item['id']] = {'questions': item['questions'], 'mode': 'native_async'}
            for pid, questions in pending.items():
                for qid, data in questions.items():
                    db.execute('INSERT OR IGNORE INTO questions VALUES(?,?,?,0)',
                               (qid, pid, json.dumps(data, ensure_ascii=False)))
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.db, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def setting(self, key, default=None):
        with closing(self.connect()) as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        with self.lock, closing(self.connect()) as db:
            db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, value))
            db.commit()

    def add(self, path):
        root, project_id = find_project(path)
        if root.parent != self.projects_root or root.name != project_id:
            raise ValueError('허용된 프로젝트 보관 위치가 아닙니다.')
        marker = json.loads((root / '.project').read_text(encoding='utf-8'))
        with self.lock, closing(self.connect()) as db:
            db.execute('INSERT INTO projects(id,name,path) VALUES(?,?,?)',
                       (project_id, marker['name'], str(root)))
            db.commit()
        return self.project(project_id)

    def projects(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute('SELECT id,name,path,model FROM projects ORDER BY rowid DESC')]

    def project(self, project_id):
        if not re.fullmatch(r'game-[a-f0-9]{32}', project_id or ''):
            raise ValueError('유효한 프로젝트 ID가 필요합니다.')
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise ValueError('등록된 프로젝트가 아닙니다.')
        result = dict(row)
        root = Path(result['path'])
        if root.resolve() != root or root.parent != self.projects_root:
            raise ValueError('프로젝트 경로가 변경되었습니다.')
        marker_root, marker_id = find_project(root)
        if marker_root != root or marker_id != project_id:
            raise ValueError('프로젝트 마커가 등록 정보와 일치하지 않습니다.')
        result['info'] = json.loads(result['info'])
        return result

    def update(self, project_id, **fields):
        if not fields.keys() <= {'thread_id', 'model', 'info', 'startup_sent'}:
            raise ValueError('변경할 수 없는 프로젝트 정보입니다.')
        values = [json.dumps(v, ensure_ascii=False) if k == 'info' else v for k, v in fields.items()]
        with self.lock, closing(self.connect()) as db:
            db.execute('UPDATE projects SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?',
                       [*values, project_id])
            db.commit()

    def event(self, project_id, kind, **data):
        with self.lock, closing(self.connect()) as db:
            db.execute('INSERT INTO events(project_id,data) VALUES(?,?)',
                       (project_id, json.dumps({'kind': kind, **data}, ensure_ascii=False)))
            db.commit()

    def merge_info(self, project_id, **fields):
        with self.lock, closing(self.connect()) as db:
            info = json.loads(db.execute('SELECT info FROM projects WHERE id=?', (project_id,)).fetchone()[0])
            info.update(fields)
            db.execute('UPDATE projects SET info=? WHERE id=?', (json.dumps(info, ensure_ascii=False), project_id))
            db.commit()

    def events(self, project_id, after=0):
        with closing(self.connect()) as db:
            return [{'seq': r['seq'], **json.loads(r['data'])} for r in db.execute(
                'SELECT seq,data FROM events WHERE project_id=? AND seq>? ORDER BY seq LIMIT 500',
                (project_id, after))]

    def add_question(self, project_id, question_id, data):
        with self.lock, closing(self.connect()) as db:
            db.execute('INSERT OR IGNORE INTO questions VALUES(?,?,?,0)',
                       (question_id, project_id, json.dumps(data, ensure_ascii=False)))
            db.commit()

    def questions(self, project_id):
        with closing(self.connect()) as db:
            return [{'id': r['id'], **json.loads(r['data'])} for r in db.execute(
                'SELECT id,data FROM questions WHERE project_id=? AND answered=0 ORDER BY rowid', (project_id,))]

    def answer_question(self, project_id, question_id):
        with self.lock, closing(self.connect()) as db:
            db.execute('UPDATE questions SET answered=1 WHERE id=? AND project_id=?', (question_id, project_id))
            db.commit()


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise ValueError('프로젝트 안의 파일 경로가 필요합니다.')
    # Reject drive names, NTFS streams and absolute paths before canonical containment.
    normalized = relative.replace('\\', '/')
    if normalized.startswith('/') or ':' in normalized or '..' in normalized.split('/'):
        raise ValueError('프로젝트 밖 경로는 사용할 수 없습니다.')
    path = project_path(root, normalized)
    if path == Path(root).resolve():
        raise ValueError('파일 경로가 필요합니다.')
    return path
