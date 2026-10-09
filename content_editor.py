"""Explicit, project-owned content definitions; no inference from arbitrary code."""
from message_catalog import text as _msg
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import uuid

from decisions import find_project, project_path, atomic_text


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(_msg('py.content_editor.characters.required' ,label,maximum))
    return value.strip()


@contextmanager
def database(root):
    root, pid = find_project(root)
    path = project_path(root, 'data/creator.sqlite')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute('CREATE TABLE IF NOT EXISTS entries(kind TEXT NOT NULL,id TEXT NOT NULL,value TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(kind,id))')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def put(db, kind, key, value):
    db.execute('INSERT INTO entries VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
               (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False), timestamp()))


def get(db, kind, key):
    row = db.execute('SELECT value FROM entries WHERE kind=? AND id=?', (kind, key)).fetchone()
    if not row:
        raise ValueError(_msg('py.content_editor.requested.item.no.longer.exists.refresh.the.list'))
    return json.loads(row[0])


def entries(db, kind):
    return [json.loads(r[0]) for r in db.execute('SELECT value FROM entries WHERE kind=? ORDER BY updated_at DESC', (kind,))]


def file_path(root, relative):
    relative = text(relative, 'path', 500).replace('\\', '/')
    parts = relative.split('/')
    if ':' in relative or any(not p or p in ('.', '..') or p.startswith('.') for p in parts):
        raise ValueError(_msg('py.content_editor.a.project.relative.content.file.is.required'))
    if parts[0].lower() in ('data', 'guide', 'agents', 'references', 'discarded', 'variants', 'feedback'):
        raise ValueError(_msg('py.content_editor.use.a.game.content.folder.such.as.content'))
    path = project_path(root, relative)
    if path.suffix.lower() not in ('.json', '.csv') or not path.is_file():
        raise ValueError(_msg('py.content_editor.register.an.existing.json.or.csv.content.file'))
    if path.stat().st_size > 2_000_000:
        raise ValueError(_msg('py.content_editor.content.editor.supports.files.up.to.mb'))
    return path


def normalize(definition):
    if not isinstance(definition, dict):
        raise ValueError(_msg('py.content_editor.a.content.definition.object.is.required'))
    result = {key: text(definition.get(key), key, 200 if key != 'path' else 500)
              for key in ('id', 'name', 'path', 'id_field')}
    fields = definition.get('fields')
    if not isinstance(fields, list) or not 1 <= len(fields) <= 40:
        raise ValueError(_msg('py.content_editor.define.content.fields'))
    result['fields'] = []
    names = set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError(_msg('py.content_editor.invalid.field.definition'))
        name = text(field.get('key'), _msg('py.content_editor.field.key'), 100)
        if name in names or field.get('type') not in ('string', 'integer', 'number', 'boolean', 'enum', 'reference'):
            raise ValueError(_msg('py.content_editor.field.keys.must.be.unique.and.have.a'))
        names.add(name)
        value = {'key': name, 'label': text(field.get('label', name), 'label', 200), 'type': field['type'],
                 'editable': field.get('editable', True) is True, 'required': field.get('required', True) is True}
        for bound in ('min', 'max'):
            if bound in field:
                if type(field[bound]) not in (int, float) or not math.isfinite(field[bound]):
                    raise ValueError(_msg('py.content_editor.numeric.bounds.must.be.finite.numbers'))
                value[bound] = field[bound]
        if value.get('min', -math.inf) > value.get('max', math.inf):
            raise ValueError(_msg('py.content_editor.minimum.exceeds.maximum'))
        if field['type'] == 'enum':
            options = field.get('options')
            if not isinstance(options, list) or not options or any(not isinstance(v, str) for v in options):
                raise ValueError(_msg('py.content_editor.enum.fields.require.text.options'))
            value['options'] = list(dict.fromkeys(options))
        if field['type'] == 'reference':
            value['dataset'] = text(field.get('dataset'), _msg('py.content_editor.reference.dataset'), 200)
        result['fields'].append(value)
    if result['id_field'] not in names:
        raise ValueError(_msg('py.content_editor.the.id.field.must.be.defined'))
    identity = next(f for f in result['fields'] if f['key'] == result['id_field'])
    if identity['type'] != 'string':
        raise ValueError(_msg('py.content_editor.the.id.field.must.be.a.string'))
    identity.update(editable=False, required=True)
    return result


def read(root, definition):
    path = file_path(root, definition['path'])
    raw = path.read_bytes()
    if path.suffix.lower() == '.json':
        rows = json.loads(raw.decode('utf-8-sig'))
    else:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(_msg('py.content_editor.csv.headers.must.be.unique'))
        rows = list(reader)
        for row in rows:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(_msg('py.content_editor.csv.rows.must.match.the.headers'))
            for field in definition['fields']:
                key = field['key']
                if row.get(key, '') == '' and not field['required']:
                    row[key] = None
                elif field['type'] in ('integer', 'number') and key in row:
                    row[key] = int(row[key]) if field['type'] == 'integer' else float(row[key])
                elif field['type'] == 'boolean' and key in row:
                    if row[key].lower() not in ('true', 'false'):
                        raise ValueError(_msg('py.content_editor.csv.booleans.must.be.true.false'))
                    row[key] = row[key].lower() == 'true'
    if not isinstance(rows, list) or len(rows) > 3000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError(_msg('py.content_editor.content.must.be.an.array.of.up.to'))
    return rows, digest(raw)


def validate(root, db, definition, rows):
    ids = set()
    for row in rows:
        identity = text(row.get(definition['id_field']), _msg('py.content_editor.row.id'), 200)
        if identity != row.get(definition['id_field']): raise ValueError(_msg('py.content_editor.row.ids.cannot.have.surrounding.whitespace'))
        if identity in ids:
            raise ValueError(_msg('py.content_editor.duplicate.row.id'))
        ids.add(identity)
    for row in rows:
        for field in definition['fields']:
            key, kind = field['key'], field['type']
            value = row.get(key)
            if value is None or value == '':
                if field['required']:
                    raise ValueError(_msg('py.content_editor.value.required' ,key))
                continue
            if kind in ('string', 'enum', 'reference') and (not isinstance(value, str) or len(value) > 10000):
                raise ValueError(_msg('py.content_editor.text.required' ,key))
            if kind == 'boolean' and type(value) is not bool:
                raise ValueError(_msg('py.content_editor.boolean.required' ,key))
            if kind in ('integer', 'number'):
                if type(value) not in (int, float) or not math.isfinite(value) or (kind == 'integer' and int(value) != value):
                    raise ValueError(_msg('py.content_editor.valid.required' ,key,kind))
                if value < field.get('min', -math.inf) or value > field.get('max', math.inf):
                    raise ValueError(_msg('py.content_editor.value.outside.allowed.range' ,key))
            if kind == 'enum' and value not in field['options']:
                raise ValueError(_msg('py.content_editor.choose.a.registered.option' ,key))
            if kind == 'reference':
                if field['dataset'] == definition['id']:
                    allowed = ids
                else:
                    referenced = get(db, 'content', field['dataset'])
                    referenced_rows, _ = read(root, referenced)
                    allowed = {r[referenced['id_field']] for r in referenced_rows}
                if value not in allowed:
                    raise ValueError(_msg('py.content_editor.referenced.row.does.not.exist' ,key))


def register(root, definition, expected=None):
    definition = normalize(definition)
    with database(root) as db:
        for current in entries(db, 'content'):
            if current['id'] == definition['id'] and current['revision'] != expected:
                raise ValueError(_msg('py.content_editor.definition.exists.or.changed.supply.its.current.revision'))
            if current['id'] != definition['id'] and file_path(root, current['path']) == file_path(root, definition['path']):
                raise ValueError(_msg('py.content_editor.this.file.is.already.registered.under.another.id'))
        rows, _ = read(root, definition)
        validate(root, db, definition, rows)
        definition['revision'] = uuid.uuid4().hex
        put(db, 'content', definition['id'], definition)
        return definition


def show(root, dataset):
    with database(root) as db:
        definition = get(db, 'content', dataset)
        rows, version = read(root, definition)
        return {'definition': definition, 'rows': rows, 'digest': version}


def save_row(root, dataset, row_id, values, expected, revision):
    if not isinstance(values, dict):
        raise ValueError(_msg('py.content_editor.a.field.value.object.is.required'))
    with database(root) as db:
        definition = get(db, 'content', dataset)
        rows, version = read(root, definition)
        if version != expected or definition['revision'] != revision:
            raise ValueError(_msg('py.content_editor.content.changed.reload.before.saving'))
        row = next((r for r in rows if r.get(definition['id_field']) == row_id), None)
        if row is None:
            raise ValueError(_msg('py.content_editor.row.no.longer.exists'))
        fields = {f['key']: f for f in definition['fields']}
        if any(key not in fields or not fields[key]['editable'] for key in values):
            raise ValueError(_msg('py.content_editor.only.registered.editable.fields.may.be.changed'))
        before = dict(row)
        row.update(values)
        validate(root, db, definition, rows)
        path = file_path(root, definition['path'])
        if path.suffix.lower() == '.json':
            output = json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        else:
            original = csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')))
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=original.fieldnames)
            writer.writeheader()
            writer.writerows({k: str(v).lower() if isinstance(v, bool) else '' if v is None else v for k, v in r.items()} for r in rows)
            output = stream.getvalue()
        change = {'id': 'CE-' + uuid.uuid4().hex[:12], 'dataset': dataset, 'row_id': row_id,
                  'path': definition['path'], 'before': before, 'after': dict(row), 'actor': 'user', 'created_at': timestamp()}
        backup = project_path(root, 'data/content-history/' + change['id'] + '.original')
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(path.read_bytes())
        if digest(path.read_bytes()) != expected:
            raise ValueError(_msg('py.content_editor.content.changed.during.save.reload.before.saving'))
        atomic_text(path, output)
        put(db, 'content_edit', change['id'], change)
    return show(root, dataset)


def command(args):
    if args.command == 'register':
        from decisions import input_text
        return register(args.project_root, json.loads(input_text(args)), args.revision)
    if args.command == 'show':
        return show(args.project_root, args.id)
    with database(args.project_root) as db:
        return {'definitions': entries(db, 'content')}
