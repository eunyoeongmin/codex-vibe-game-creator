"""Append-only research, interpretation and application links for project references."""
from message_catalog import text as _msg
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import decisions

STAGES = ('research', 'interpretation', 'application')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS reference_traces (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
 reference_id TEXT NOT NULL REFERENCES user_references(id),
 created_at TEXT NOT NULL, stage TEXT NOT NULL
 CHECK(stage IN ('research','interpretation','application')),
 topic TEXT NOT NULL CHECK(length(trim(topic))>0),
 user_quote TEXT NOT NULL, assistant_reply TEXT NOT NULL,
 reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 supersedes TEXT UNIQUE REFERENCES reference_traces(id),
 payload TEXT NOT NULL CHECK(json_valid(payload))
);
CREATE INDEX IF NOT EXISTS reference_trace_lookup ON reference_traces(project_id, reference_id);
'''
COMMON = {'stage', 'topic', 'user_quote', 'assistant_reply', 'reason'}
FIELDS = {
    'research': {'source', 'locator', 'observation', 'limitations'},
    'interpretation': {'research_ids', 'meaning'},
    'application': {'interpretation_ids', 'plan', 'differences', 'state', 'decision_ids', 'asset_ids', 'files'},
}


def exists(c, table):
    return c is not None and c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def decode(row):
    value = dict(row)
    return value | {'payload': json.loads(value['payload'])}


def traces(c, pid, ref_id):
    if not exists(c, 'reference_traces'):
        return []
    rows = [decode(r) for r in c.execute(
        'SELECT * FROM reference_traces WHERE project_id=? AND reference_id=? ORDER BY rowid', (pid, ref_id))]
    by_id = {r['id']: r for r in rows}
    replaced = {r['supersedes']: r['id'] for r in rows if r['supersedes']}
    # Links only target older entries, so parent review state is available here.
    for row in rows:
        row['superseded_by'] = replaced.get(row['id'])
        links = row['payload'].get('research_ids', []) + row['payload'].get('interpretation_ids', [])
        row['outdated_basis'] = any(link not in by_id or link in replaced or
                                   by_id[link].get('outdated_basis', False) for link in links)
    return rows


def relative_file(root, value, *, must_exist=False):
    decisions.nonempty(value, _msg('py.reference_trace.file.path'))
    if value.startswith(('/', '\\')) or ':' in value or '..' in value.replace('\\', '/').split('/'):
        raise ValueError(_msg('py.reference_trace.message'))
    path = decisions.project_path(root, value)
    if must_exist and not path.is_file():
        raise ValueError(_msg('py.reference_trace.message.2'))
    return path.relative_to(root).as_posix()


def linked_records(c, pid, ids, tables, field):
    decisions.string_list(ids, field)
    if len(ids) != len(set(ids)):
        raise ValueError(_msg('py.reference_trace.message.3' ,field))
    for record_id in ids:
        if not any(exists(c, table) and c.execute(
                f'SELECT 1 FROM {table} WHERE id=? AND project_id=?', (record_id, pid)).fetchone()
                for table in tables):
            raise ValueError(_msg('py.reference_trace.message.4' ,field,record_id))


def validate(c, root, pid, ref_id, value):
    if not isinstance(value, dict) or not COMMON <= value.keys():
        raise ValueError(_msg('py.reference_trace.message.5'))
    stage = value['stage']
    decisions.choice(stage, STAGES, 'stage')
    required = COMMON | FIELDS[stage]
    if not required <= value.keys() or value.keys() - required - {'supersedes'}:
        raise ValueError(_msg('py.reference_trace.message.6' ,stage,', '.join(sorted(required))))
    for field in COMMON - {'stage'}:
        decisions.nonempty(value[field], field)
    payload = {k: value[k] for k in FIELDS[stage]}
    if stage == 'research':
        for field in FIELDS[stage]:
            if not isinstance(payload[field], str):
                raise ValueError(_msg('py.asset_store.message.3' ,field))
        decisions.nonempty(payload['source'], 'source')
        decisions.nonempty(payload['observation'], 'observation')
        parsed = urlsplit(payload['source'])
        if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password:
            pass
        else:
            payload['source'] = relative_file(root, payload['source'], must_exist=True)
    else:
        field, parent_stage = ('research_ids', 'research') if stage == 'interpretation' else ('interpretation_ids', 'interpretation')
        linked_records(c, pid, payload[field], ('reference_traces',), field)
        if not payload[field]:
            raise ValueError(_msg('py.reference_trace.message.7' ,field))
        current = {r['id']: r for r in traces(c, pid, ref_id)}
        for key in payload[field]:
            if key not in current or current[key]['stage'] != parent_stage:
                raise ValueError(_msg('py.reference_trace.message.8'))
            if current[key]['superseded_by'] or current[key]['outdated_basis']:
                raise ValueError(_msg('py.reference_trace.message.9'))
        if stage == 'interpretation':
            decisions.nonempty(payload['meaning'], 'meaning')
        else:
            decisions.nonempty(payload['plan'], 'plan')
            if not isinstance(payload['differences'], str):
                raise ValueError(_msg('py.reference_trace.message.10'))
            decisions.choice(payload['state'], ('planned', 'applied', 'dropped'), 'state')
            linked_records(c, pid, payload['decision_ids'], ('user_decisions', 'work_decisions'), 'decision_ids')
            linked_records(c, pid, payload['asset_ids'], ('assets',), 'asset_ids')
            payload['asset_versions'] = {key: c.execute(
                'SELECT revision FROM assets WHERE id=? AND project_id=?', (key, pid)).fetchone()['revision']
                for key in payload['asset_ids']}
            if not isinstance(payload['files'], list):
                raise ValueError(_msg('py.reference_trace.message.11'))
            files = []
            for entry in payload['files']:
                if not isinstance(entry, dict) or set(entry) != {'path', 'location'}:
                    raise ValueError(_msg('py.reference_trace.message.12'))
                decisions.nonempty(entry['location'], 'location')
                files.append({'path': relative_file(root, entry['path'], must_exist=payload['state'] == 'applied'),
                              'location': entry['location']})
            if payload['state'] == 'applied' and not files:
                raise ValueError(_msg('py.reference_trace.message.13'))
            payload['files'] = files
    return payload


def add(project, ref_id, value):
    root, pid = decisions.find_project(project)
    path = decisions.project_path(root, 'data/decisions.sqlite')
    with decisions.database(path, 'user', write=True, project_root=root) as c:
        c.executescript(SCHEMA)
        with decisions.transaction(c):
            if not c.execute('SELECT 1 FROM user_references WHERE id=? AND project_id=?', (ref_id, pid)).fetchone():
                raise ValueError(_msg('py.decisions.message.30'))
            payload = validate(c, root, pid, ref_id, value)
            previous = c.execute(
                'SELECT t.id FROM reference_traces t WHERE t.project_id=? AND t.reference_id=? AND t.stage=? AND t.topic=? '
                'AND NOT EXISTS(SELECT 1 FROM reference_traces n WHERE n.supersedes=t.id)',
                (pid, ref_id, value['stage'], value['topic'])).fetchone()
            supersedes = value.get('supersedes')
            if (previous and supersedes != previous['id']) or (not previous and supersedes is not None):
                raise ValueError(_msg('py.reference_trace.message.14'))
            number = c.execute('SELECT coalesce(max(cast(substr(id,4) AS INTEGER)),0)+1 FROM reference_traces').fetchone()[0]
            record = {'id': f'RT-{number:03d}', 'project_id': pid, 'reference_id': ref_id,
                      'created_at': datetime.now(timezone.utc).isoformat(),
                      **{k: value[k] for k in COMMON}, 'supersedes': supersedes,
                      'payload': json.dumps(payload, ensure_ascii=False)}
            c.execute(f'INSERT INTO reference_traces ({",".join(record)}) VALUES ({",".join("?" for _ in record)})', list(record.values()))
            return {'saved': record | {'payload': payload}}


def detail(c, pid, record):
    result = dict(record)
    if isinstance(result.get('aspects'), str):
        result['aspects'] = json.loads(result['aspects'])
    result['trace'] = traces(c, pid, result['id'])
    result['linked_decisions'] = []
    result['linked_assets'] = []
    explicit_decisions = {key for row in result['trace'] for key in row['payload'].get('decision_ids', [])}
    explicit_assets = {key for row in result['trace'] for key in row['payload'].get('asset_ids', [])}
    for table in ('user_decisions', 'work_decisions'):
        if not exists(c, table):
            continue
        for row in c.execute(f'SELECT * FROM {table} WHERE project_id=?', (pid,)):
            item = decisions.decoded_record(row)
            if item['id'] in explicit_decisions or result['id'] in item.get('reference_ids', []):
                if table == 'user_decisions':
                    newer = c.execute('SELECT id FROM user_decisions WHERE supersedes=? AND project_id=?', (item['id'], pid)).fetchone()
                    item['superseded_by'] = newer['id'] if newer else None
                result['linked_decisions'].append(item)
    if exists(c, 'assets'):
        for row in c.execute('SELECT * FROM assets WHERE project_id=?', (pid,)):
            item = dict(row)
            item = {k: v for k, v in item.items() if k != 'payload'} | json.loads(item['payload'])
            if item['id'] in explicit_assets or result['id'] in item.get('reference_ids', []):
                result['linked_assets'].append(item)
    return result


def get(project, ref_id):
    root, pid = decisions.find_project(project)
    with decisions.database(decisions.project_path(root, 'data/decisions.sqlite'), 'user', project_root=root) as c:
        row = c.execute('SELECT * FROM user_references WHERE id=? AND project_id=?', (ref_id, pid)).fetchone() if exists(c, 'user_references') else None
        if row is None:
            raise ValueError(_msg('py.decisions.message.30'))
        return detail(c, pid, row)
