"""DB-derived planning cards and versioned, user-approved specifications."""
from message_catalog import text as _msg
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import decisions
from localization import translate

LABELS = dict(zip(decisions.CATEGORIES, (
    _msg('ui.genre'), _msg('ui.camera'), _msg('ui.art.style'), _msg('ui.mood.and.world'), _msg('ui.core.loop'), _msg('ui.platform.and.controls'),
    _msg('ui.scope.and.content'), _msg('ui.technology'), 'UI', _msg('ui.color.palette'), _msg('ui.purpose.and.other'))))
START_QUOTE = _msg('ui.selected.start.with.this.on.the.summary.screen')
SPEC_SCHEMA = '''CREATE TABLE IF NOT EXISTS harness_specs (
    version INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
    confirmed_hash TEXT NOT NULL, snapshot TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0)'''


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def current_records(c, pid):
    return [decisions.decoded_record(row) for row in c.execute(
        'SELECT r.* FROM user_decisions r WHERE project_id=? '
        'AND NOT EXISTS (SELECT 1 FROM user_decisions n WHERE n.supersedes=r.id) '
        'ORDER BY r.rowid', (pid,))]


def summary(records):
    categories = []
    for category, label in LABELS.items():
        items = [{k: r[k] for k in ('id', 'created_at', 'topic', 'decision', 'status')}
                 for r in records if r['category'] == category]
        states = {r['status'] for r in items}
        categories.append({'category': category, 'label': label, 'items': items,
                           'status': 'proposed' if 'proposed' in states else
                                     'confirmed' if items else 'undecided'})
    return {'categories': categories,
            'confirmed_count': sum(r['status'] == 'confirmed' for r in records),
            'fingerprint': digest(records)}


def confirmed_hash(records):
    return digest([r for r in records if r['status'] == 'confirmed'])


def spec_text(snapshot):
    language = snapshot.get('language', 'ko')
    tr = lambda text, *values: translate(text, language, *values)
    lines = ['# SPEC', '', tr(_msg('ui.version'), snapshot['version']),
             tr(_msg('ui.time'), snapshot['created_at']), tr(_msg('ui.project'), snapshot['project_id']), '']
    for category in snapshot['categories']:
        lines.extend([f'## {tr(category["label"])}', ''])
        if not category['items']:
            lines.append('- ' + tr(_msg('ui.undecided')))
        for item in category['items']:
            label = tr(_msg('ui.confirmed') if item['status'] == 'confirmed' else _msg('ui.proposed'))
            text = item['decision'].replace('\n', '\n  ')
            lines.append(f'- [{label}] {item["topic"]}: {text} '
                         f'({item["id"]}, {item["created_at"]})')
        lines.append('')
    return '\n'.join(lines)


class Planning:
    def __init__(self, state):
        self.state = state

    def root(self, pid):
        return Path(self.state.project(pid)['path'])

    def connect(self, root):
        path = decisions.project_path(root, 'data/decisions.sqlite')
        c = sqlite3.connect(path, isolation_level=None, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute(SPEC_SCHEMA)
        return c

    def latest(self, c):
        row = c.execute('SELECT * FROM harness_specs ORDER BY version DESC LIMIT 1').fetchone()
        return dict(row) if row else None

    def save_version(self, c, pid, records, *, delivered):
        previous = self.latest(c)
        snapshot = {**summary(records), 'project_id': pid,
                    'language': self.state.setting('language', 'ko'),
                    'version': previous['version'] + 1 if previous else 1,
                    'created_at': datetime.now(timezone.utc).isoformat()}
        c.execute('INSERT INTO harness_specs VALUES(?,?,?,?,?)', (
            snapshot['version'], snapshot['created_at'], confirmed_hash(records),
            json.dumps(snapshot, ensure_ascii=False), int(delivered)))
        return self.latest(c)

    def materialize(self, root, c):
        # Reconstruct files from committed snapshots, including after an interrupted write.
        folder = decisions.project_path(root, '.harness/specs')
        folder.mkdir(parents=True, exist_ok=True)
        latest = None
        for row in c.execute('SELECT * FROM harness_specs ORDER BY version'):
            latest = spec_text(json.loads(row['snapshot']))
            path = decisions.project_path(root, f'.harness/specs/SPEC.v{row["version"]:03d}.md')
            if not path.exists() or path.read_text(encoding='utf-8') != latest:
                decisions.atomic_text(path, latest)
        if latest is not None:
            path = decisions.project_path(root, 'SPEC.md')
            if not path.exists() or path.read_text(encoding='utf-8') != latest:
                decisions.atomic_text(path, latest)

    def progress(self, pid):
        with self.state.lock:
            root = self.root(pid)
            with closing(self.connect(root)) as c, decisions.transaction(c):
                records = current_records(c, pid)
                latest = self.latest(c)
                if latest and latest['confirmed_hash'] != confirmed_hash(records):
                    latest = self.save_version(c, pid, records, delivered=bool(latest['delivered']))
            if latest:
                with closing(self.connect(root)) as c:
                    self.materialize(root, c)
            result = summary(records)
            info = self.state.project(pid)['info'].get('planning', {})
            checkpoint = result['confirmed_count'] // 10
            if not latest and checkpoint > info.get('checkpoint', 0):
                info = {**info, 'open': True}
                self.state.merge_info(pid, planning=info)
            result.update(show_summary=bool(info.get('open')) and not (latest and latest['delivered']),
                          spec_version=latest['version'] if latest else None,
                          pending_delivery=bool(latest and not latest['delivered']))
            try:
                milestones = decisions.read_milestones(root)
                result['production'] = {
                    'started': latest is not None, 'milestones': milestones,
                    'completed': sum(m['status'] == 'done' for m in milestones),
                    'total': len(milestones),
                    'current': next((m for m in milestones if m['status'] == 'active'), None),
                    'error': None}
            except (ValueError, OSError) as error:
                result['production'] = {'started': latest is not None, 'milestones': [],
                                        'completed': 0, 'total': 0, 'current': None, 'error': str(error)}
            return result

    def open_summary(self, pid):
        with self.state.lock:
            info = self.state.project(pid)['info'].get('planning', {})
            self.state.merge_info(pid, planning={**info, 'open': True})
            return self.progress(pid)

    def more(self, pid, fingerprint):
        with self.state.lock:
            result = self.progress(pid)
            if result['fingerprint'] != fingerprint:
                raise ValueError(_msg('ui.decisions.changed.review.the.updated.summary'))
            self.state.merge_info(pid, planning={'open': False, 'checkpoint': result['confirmed_count'] // 10})
            return self.progress(pid)

    def approve(self, pid, fingerprint):
        with self.state.lock:
            root = self.root(pid)
            # Keep vector search working: unchanged proposal content keeps its original vector.
            with decisions.database(root / 'data/decisions.sqlite', 'user', write=True,
                                    project_root=root) as c, decisions.transaction(c):
                c.execute(SPEC_SCHEMA)
                latest = self.latest(c)
                if latest:
                    if latest['delivered']:
                        raise ValueError(_msg('ui.development.has.already.been.approved.for.this.project'))
                else:
                    records = current_records(c, pid)
                    if digest(records) != fingerprint:
                        raise ValueError(_msg('ui.decisions.changed.review.the.updated.summary'))
                    if not records:
                        raise ValueError(_msg('ui.there.are.no.saved.decisions'))
                    for proposal in (r for r in records if r['status'] == 'proposed'):
                        # A single supersedes link cannot safely retire two conflicting records.
                        others = [r for r in records if r['id'] != proposal['id'] and
                                  (r['category'], r['topic']) == (proposal['category'], proposal['topic'])]
                        if others:
                            raise ValueError(_msg('py.dashboard_planning.message' ,proposal['category'],proposal['topic']))
                        record = {**proposal, 'id': decisions.next_id(c, 'user'),
                                  'created_at': datetime.now(timezone.utc).isoformat(),
                                  'status': 'confirmed', 'user_quote': translate(START_QUOTE, self.state.setting('language', 'ko')),
                                  'supersedes': proposal['id']}
                        c.execute(f'INSERT INTO user_decisions ({",".join(record)}) '
                                  f'VALUES ({",".join("?" for _ in record)})',
                                  [json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v
                                   for v in record.values()])
                        c.execute('INSERT INTO user_decision_vectors(id,embedding,metadata) '
                                  'SELECT ?,embedding,metadata FROM user_decision_vectors WHERE id=?',
                                  (record['id'], proposal['id']))
                    latest = self.save_version(c, pid, current_records(c, pid), delivered=False)
            with closing(self.connect(root)) as c:
                self.materialize(root, c)
            return latest['version']

    def delivered(self, pid):
        with self.state.lock, closing(self.connect(self.root(pid))) as c:
            c.execute('UPDATE harness_specs SET delivered=1')
            info = self.state.project(pid)['info'].get('planning', {})
            self.state.merge_info(pid, planning={**info, 'open': False})
