"""Project-scoped asset inventory and revision history shared by CLI and dashboard."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

KINDS = ('image', 'sound')
STATUSES = ('temporary', 'proposed', 'confirmed', 'retired')
METHODS = ('code', 'image_skill', 'external', 'other_skill')
USAGE_STATES = ('planned', 'in_use', 'unused')
FIELDS = {'name', 'kind', 'group', 'usage', 'usage_state', 'status', 'methods', 'files',
          'art_notes', 'reason', 'source_note', 'replacement_plan', 'decision_ids',
          'reference_ids', 'approval_quote'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_revisions (
 asset_id TEXT NOT NULL, revision INTEGER NOT NULL, project_id TEXT NOT NULL,
 created_at TEXT NOT NULL, actor TEXT NOT NULL, change_note TEXT NOT NULL,
 snapshot TEXT NOT NULL, PRIMARY KEY(asset_id, revision)
);
'''


class AssetStore:
    def __init__(self, project):
        import decisions
        self.root, self.pid = decisions.find_project(project)
        if self.root != Path(project).resolve():
            raise ValueError('에셋 저장소는 프로젝트 루트에서 열어야 합니다.')
        self.path = decisions.project_path(self.root, 'data/decisions.sqlite')

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.executescript(SCHEMA)
            yield c
        finally:
            c.close()

    @staticmethod
    def decode(row):
        return {k: row[k] for k in ('id', 'project_id', 'revision', 'created_at', 'updated_at')} | json.loads(row['payload'])

    def get(self, asset_id, c=None):
        if c is None:
            with self.connect() as connection:
                return self.get(asset_id, connection)
        row = c.execute('SELECT * FROM assets WHERE id=? AND project_id=?', (asset_id, self.pid)).fetchone()
        if row is None:
            raise ValueError('에셋을 찾을 수 없습니다.')
        return self.decode(row)

    def list(self, *, kind=None, status=None, query=None):
        import decisions
        if kind:
            decisions.choice(kind, KINDS, 'kind')
        if status:
            decisions.choice(status, STATUSES, 'status')
        with self.connect() as c:
            records = [self.decode(r) for r in c.execute('SELECT * FROM assets WHERE project_id=? ORDER BY rowid', (self.pid,))]
        return [r for r in records if (not kind or r['kind'] == kind) and (not status or r['status'] == status)
                and (not query or query.casefold() in json.dumps(r, ensure_ascii=False).casefold())]

    def history(self, asset_id):
        with self.connect() as c:
            self.get(asset_id, c)
            return [{**dict(row), 'snapshot': json.loads(row['snapshot'])} for row in c.execute(
                'SELECT * FROM asset_revisions WHERE asset_id=? AND project_id=? ORDER BY revision DESC',
                (asset_id, self.pid))]

    def art_decisions(self):
        with self.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_decisions'").fetchone():
                return []
            return [dict(row) for row in c.execute(
                "SELECT id,topic,decision FROM user_decisions d WHERE project_id=? AND status='confirmed' "
                "AND category IN ('art_style','color_palette','viewpoint','ui_style','mood') "
                "AND NOT EXISTS(SELECT 1 FROM user_decisions n WHERE n.supersedes=d.id) ORDER BY rowid", (self.pid,))]

    def file(self, path):
        import decisions
        # Accept only portable project-relative paths, including for code-generated art.
        if not isinstance(path, str) or not path or path.startswith(('/', '\\')) or ':' in path or '..' in path.replace('\\', '/').split('/'):
            raise ValueError('에셋 파일은 프로젝트 내부 상대 경로로 지정하세요.')
        result = decisions.project_path(self.root, path)
        return result

    def validate(self, values, c, previous, actor):
        import decisions
        if not isinstance(values, dict) or values.keys() - FIELDS:
            raise ValueError('에셋 필드가 올바르지 않습니다.')
        defaults = {'group': '', 'usage_state': 'planned', 'status': 'temporary', 'methods': [], 'files': [],
                    'art_notes': '', 'source_note': '', 'replacement_plan': '', 'decision_ids': [],
                    'reference_ids': [], 'approval_quote': ''}
        value = defaults | ({k: previous[k] for k in FIELDS} if previous else {}) | values
        for field in ('name', 'usage', 'reason'):
            decisions.nonempty(value.get(field), field)
        decisions.choice(value.get('kind'), KINDS, 'kind')
        decisions.choice(value['status'], STATUSES, 'status')
        decisions.choice(value['usage_state'], USAGE_STATES, 'usage_state')
        if value['status'] == 'retired' and value['usage_state'] != 'unused':
            raise ValueError('사용 종료 에셋은 적용 상태를 미사용으로 지정하세요.')
        for field in ('group', 'art_notes', 'source_note', 'replacement_plan', 'approval_quote'):
            if not isinstance(value[field], str):
                raise ValueError(f'{field}: 문자열이 필요합니다.')
        for field in ('methods', 'files', 'decision_ids', 'reference_ids'):
            decisions.string_list(value[field], field)
            if len(set(value[field])) != len(value[field]):
                raise ValueError(f'{field}: 중복 항목은 사용할 수 없습니다.')
        if not value['methods']:
            raise ValueError('제작 방식을 하나 이상 선택하세요.')
        for method in value['methods']:
            decisions.choice(method, METHODS, 'methods')
        for path in value['files']:
            if not self.file(path).is_file():
                raise ValueError('등록할 에셋 파일이 프로젝트 안에 없습니다.')
        if value['usage_state'] == 'in_use' and not value['files']:
            raise ValueError('사용 중인 에셋에는 파일 또는 구현 코드 경로가 필요합니다.')
        if value['status'] == 'temporary':
            decisions.nonempty(value['replacement_plan'], 'replacement_plan')
        for field, table in (('decision_ids', 'user_decisions'), ('reference_ids', 'user_references')):
            for record_id in value[field]:
                if not c.execute(f'SELECT 1 FROM {table} WHERE id=? AND project_id=?', (record_id, self.pid)).fetchone():
                    raise ValueError('같은 프로젝트의 결정·레퍼런스만 연결할 수 있습니다.')
        changed_art = previous is None or any(value[k] != previous[k] for k in
            ('files', 'methods', 'art_notes', 'decision_ids', 'reference_ids'))
        needs_approval = value['status'] == 'confirmed' and (not previous or previous['status'] != 'confirmed' or changed_art)
        if needs_approval:
            quote = values.get('approval_quote', '')
            decisions.nonempty(quote, 'approval_quote')
        # A material change cannot inherit the old approval as evidence for new art.
        if value['status'] != 'confirmed':
            value['approval_quote'] = ''
        return value

    def save(self, values, *, asset_id=None, expected_revision=None, actor='ai', change_note):
        import decisions
        decisions.choice(actor, ('ai', 'user'), 'actor')
        decisions.nonempty(change_note, 'change_note')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                previous = self.get(asset_id, c) if asset_id else None
                if previous and (type(expected_revision) is not int or expected_revision != previous['revision']):
                    raise ValueError('에셋이 변경되었습니다. 새로고침 후 다시 저장하세요.')
                payload = self.validate(values, c, previous, actor)
                now = datetime.now(timezone.utc).isoformat()
                if not asset_id:
                    number = c.execute('SELECT coalesce(max(cast(substr(id,3) AS INTEGER)),0)+1 FROM assets').fetchone()[0]
                    asset_id = f'A-{number:03d}'
                record = {'id': asset_id, 'project_id': self.pid, 'revision': previous['revision'] + 1 if previous else 1,
                          'created_at': previous['created_at'] if previous else now, 'updated_at': now, **payload}
                c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                          'revision=excluded.revision,updated_at=excluded.updated_at,payload=excluded.payload',
                          (asset_id, self.pid, record['revision'], record['created_at'], now, json.dumps(payload, ensure_ascii=False)))
                c.execute('INSERT INTO asset_revisions VALUES(?,?,?,?,?,?,?)',
                          (asset_id, record['revision'], self.pid, now, actor, change_note, json.dumps(record, ensure_ascii=False)))
                c.commit()
                return record
            except Exception:
                c.rollback()
                raise


def command(args):
    import decisions
    store = AssetStore(args.project_root)
    if args.command == 'list':
        return {'assets': store.list(kind=args.kind, status=args.status, query=args.query)}
    if args.command == 'show':
        return store.get(args.id)
    if args.command == 'history':
        return {'history': store.history(args.id)}
    value = json.loads(decisions.input_text(args))
    if not isinstance(value, dict):
        raise ValueError('JSON 객체가 필요합니다.')
    note = value.pop('change_note', None)
    return store.save(value, asset_id=getattr(args, 'id', None), expected_revision=getattr(args, 'revision', None), change_note=note)
