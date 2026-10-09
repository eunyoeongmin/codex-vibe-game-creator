"""Project-scoped request context and user-operated discard candidates."""
from message_catalog import text as _msg
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from decisions import find_project, project_path, read_milestones


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def connect(root):
    root, pid = find_project(root)
    path = project_path(root, 'data/decisions.sqlite')
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    return db, root, pid


def target(root, kind, record_id):
    if kind == 'milestone':
        record = next((m for m in read_milestones(root) if m['id'] == record_id), None)
    elif kind == 'asset':
        from asset_store import AssetStore
        record = AssetStore(root).get(record_id)
    else:
        tables = {'user': 'user_decisions', 'work': 'work_decisions', 'reference': 'user_references'}
        if kind not in tables:
            raise ValueError(_msg('py.project_workbench.unknown.request.target.type'))
        db, root, pid = connect(root)
        with closing(db):
            row = db.execute(f'SELECT * FROM {tables[kind]} WHERE project_id=? AND id=?', (pid, record_id)).fetchone()
            record = dict(row) if row else None
    if record is None:
        raise ValueError(_msg('py.project_workbench.request.target.no.longer.exists.refresh.the.list'))
    return {'kind': kind, 'id': record_id, 'record': record, 'fingerprint': fingerprint(record)}


def context_search(root, query, selected=None):
    """Bounded keyword evidence, not an assertion that systems are related."""
    if not isinstance(query, str) or len(query) > 10000:
        raise ValueError(_msg('py.project_workbench.search.text.must.be.at.most.characters'))
    db, root, pid = connect(root)
    terms = list(dict.fromkeys(re.findall(r'[\w-]{2,}', query.lower())))[:16]
    # Strip common Korean grammatical suffixes, retaining the original terms.
    for word in terms[:]:
        base = re.sub(_msg('py.project_workbench.message'), '', word)
        if len(base) >= 2 and base != word:
            terms.append(base)
    if selected:
        terms += re.findall(r'\b[UWAR]-\d+\b', json.dumps(selected['record'], ensure_ascii=False).lower(), re.I)
        for field in ('title', 'topic', 'name', 'title_or_url'):
            terms += re.findall(r'[\w-]{2,}', str(selected['record'].get(field, '')).lower())[:8]
    terms = list(dict.fromkeys(t.lower() for t in terms))[:24]
    matches = []
    scanned_records = 0
    with closing(db):
        existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('user_decisions', 'work_decisions', 'user_references', 'reference_traces', 'assets'):
            if table not in existing:
                continue
            current_only = (f' AND NOT EXISTS(SELECT 1 FROM {table} newer WHERE newer.project_id={table}.project_id AND newer.supersedes={table}.id)'
                            if table in ('user_decisions', 'reference_traces') else '')
            rows = db.execute(f'SELECT * FROM {table} WHERE project_id=?{current_only} ORDER BY rowid DESC LIMIT 300', (pid,))
            for row in rows:
                scanned_records += 1
                value = dict(row)
                if table == 'assets':
                    value.update(json.loads(value.pop('payload')))
                if value.get('status') == 'superseded':
                    continue
                text = json.dumps(value, ensure_ascii=False)
                score = sum(term in text.lower() for term in terms)
                if score:
                    excerpt = {k: v[:2000] if isinstance(v, str) else v for k, v in value.items()}
                    matches.append((score, {'table': table, 'id': value['id'], 'record': excerpt}))
    matches.sort(key=lambda item: item[0], reverse=True)
    evidence = [v for _, v in matches[:8]]
    for entry in evidence:
        ref = entry['record'].get('evidence_ref', '') or ''
        terms += re.findall(r'[A-Za-z_][A-Za-z_0-9]{2,}', ref.lower())[:8]
    terms = list(dict.fromkeys(terms))[:48]
    code = []
    scanned_files = 0
    truncated = False
    extensions = {'.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.py', '.cs', '.gd', '.lua', '.json'}
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in
                         ('node_modules', 'data', 'guide', 'agents', 'catalogs', 'genres', '__pycache__', 'venv')
                         and (Path(folder) / d).resolve().is_relative_to(root))
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix.lower() not in extensions or not path.resolve().is_relative_to(root):
                continue
            if scanned_files >= 150:
                truncated = True
                break
            scanned_files += 1
            try:
                if path.stat().st_size > 256_000:
                    truncated = True
                    continue
                lines = path.read_text(encoding='utf-8-sig').splitlines()
            except (OSError, UnicodeError):
                continue
            for number, line in enumerate(lines, 1):
                if terms and any(term in line.lower() for term in terms):
                    code.append({'path': path.relative_to(root).as_posix(), 'line': number, 'text': line[:350]})
                    if len(code) >= 12:
                        break
            if len(code) >= 12:
                truncated = True
                break
        if truncated and (scanned_files >= 150 or len(code) >= 12):
            break
    return {'query': query, 'terms': terms, 'target': selected, 'records': evidence, 'code': code,
            'coverage': {'method': 'keyword', 'records_scanned': scanned_records, 'files_scanned': scanned_files,
                         'max_records_per_table': 300, 'limited': truncated}, 'created_at': now()}


class Discards:
    def __init__(self, root):
        self.root, self.pid = find_project(root)

    def db(self):
        db, _, _ = connect(self.root)
        db.execute('''CREATE TABLE IF NOT EXISTS discard_candidates (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, path TEXT NOT NULL,
            reason TEXT NOT NULL, record_ids TEXT NOT NULL, digest TEXT NOT NULL,
            size INTEGER NOT NULL, state TEXT NOT NULL, destination TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        db.commit()
        return db

    def file(self, relative, *, discarded=False):
        if not isinstance(relative, str) or not relative or '\x00' in relative:
            raise ValueError(_msg('py.project_workbench.a.project.file.path.is.required'))
        parts = relative.replace('\\', '/').split('/')
        if ':' in relative or relative.startswith(('/', '\\')) or any(p in ('', '.', '..') or p.startswith('.') for p in parts):
            raise ValueError(_msg('py.project_workbench.only.regular.project.files.may.be.discarded'))
        if parts[0].lower() in ('data', 'guide', 'agents', 'catalogs', 'genres') or parts[-1].lower() in (
                'agents.md', 'agents.override.md', 'spec.md', 'state.md', 'milestones.json'):
            raise ValueError(_msg('py.project_workbench.project.instructions.and.records.cannot.be.discarded.here'))
        if discarded != (parts[0].lower() == 'discarded'):
            raise ValueError(_msg('py.project_workbench.invalid.discard.location'))
        path = project_path(self.root, relative)
        # Reject links/junctions rather than operating on their targets.
        original = self.root.joinpath(*parts)
        if original.resolve() != original.absolute() or any(p.is_symlink() for p in (original, *original.parents)):
            raise ValueError(_msg('py.project_workbench.linked.files.cannot.be.discarded'))
        if not path.is_file():
            raise ValueError(_msg('py.project_workbench.the.candidate.file.no.longer.exists'))
        return path

    @staticmethod
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    def propose(self, path, reason, record_ids=None):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise ValueError(_msg('py.project_workbench.a.discard.reason.is.required.characters'))
        ids = record_ids or []
        if not isinstance(ids, list) or any(not isinstance(i, str) or not re.fullmatch(r'[A-Z]+-\d+', i) for i in ids):
            raise ValueError(_msg('py.project_workbench.invalid.record.ids'))
        source = self.file(path)
        path = source.relative_to(self.root).as_posix()
        digest = self.digest(source)
        with closing(self.db()) as db, db:
            old = db.execute("SELECT * FROM discard_candidates WHERE project_id=? AND path=? AND digest=? AND state='pending'",
                             (self.pid, path, digest)).fetchone()
            if old:
                return dict(old)
            record = {'id': 'X-' + uuid.uuid4().hex[:12], 'project_id': self.pid, 'path': path,
                      'reason': reason, 'record_ids': json.dumps(ids), 'digest': digest, 'size': source.stat().st_size,
                      'state': 'pending', 'destination': None, 'created_at': now(), 'updated_at': now()}
            db.execute(f'INSERT INTO discard_candidates ({",".join(record)}) VALUES ({",".join("?" for _ in record)})', tuple(record.values()))
            return record

    def list(self):
        with closing(self.db()) as db:
            return [dict(r) for r in db.execute('SELECT * FROM discard_candidates WHERE project_id=? ORDER BY created_at DESC', (self.pid,))]

    def act(self, record_id, action, digest):
        if action not in ('move', 'delete', 'keep'):
            raise ValueError(_msg('py.project_workbench.unknown.discard.action'))
        with closing(self.db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM discard_candidates WHERE id=? AND project_id=?', (record_id, self.pid)).fetchone()
            if not row or row['digest'] != digest:
                raise ValueError(_msg('py.project_workbench.the.discard.candidate.changed.refresh.the.list'))
            expected = 'moved' if action == 'delete' else 'pending'
            if row['state'] != expected:
                raise ValueError(_msg('py.project_workbench.this.discard.action.is.no.longer.available.refresh'))
            if action == 'keep':
                db.execute("UPDATE discard_candidates SET state='kept',updated_at=? WHERE id=?", (now(), record_id))
                db.commit()
                return
            source = self.file(row['destination'] if action == 'delete' else row['path'], discarded=action == 'delete')
            if self.digest(source) != digest:
                raise ValueError(_msg('py.project_workbench.the.file.changed.after.registration.register.it.again'))
            destination = f'discarded/{record_id}/{source.name}' if action == 'move' else row['destination']
            dest = project_path(self.root, destination)
            if dest != self.root.joinpath('discarded', record_id, source.name):
                raise ValueError(_msg('py.project_workbench.invalid.discard.destination'))
            if action == 'move' and dest.exists():
                raise ValueError(_msg('py.project_workbench.the.destination.already.exists.no.file.was.overwritten'))
            # Persist intent first. A crash leaves an inspectable entry, never a repeated deletion.
            db.execute('UPDATE discard_candidates SET state=?,destination=?,updated_at=? WHERE id=?',
                       ('moving' if action == 'move' else 'deleting', destination, now(), record_id))
            db.commit()
            try:
                if action == 'move':
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.parent.resolve() != self.root.joinpath('discarded', record_id):
                        raise ValueError(_msg('py.project_workbench.invalid.discard.destination'))
                    source.rename(dest)
                else:
                    source.unlink()
            except Exception:
                db.execute("UPDATE discard_candidates SET state='needs_attention',updated_at=? WHERE id=?", (now(), record_id))
                db.commit()
                raise
            db.execute('UPDATE discard_candidates SET state=?,updated_at=? WHERE id=?',
                       ('moved' if action == 'move' else 'deleted', now(), record_id))
            db.commit()


def command(args):
    if args.store == 'context':
        return context_search(args.project_root, args.query)
    store = Discards(args.project_root)
    if args.command == 'list':
        return {'candidates': store.list()}
    return store.propose(args.path, args.reason, args.record_ids)
