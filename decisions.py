"""Separate SQLite game-work/user records with Semantica semantic search."""
from __future__ import annotations
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
AREAS = ('gameplay', 'art', 'ui', 'code_structure', 'content', 'other')
CATEGORIES = ('genre', 'viewpoint', 'art_style', 'mood', 'core_loop', 'platform', 'scope', 'tech_stack', 'ui_style', 'color_palette', 'other')
REFERENCE_KINDS = ('game', 'image', 'link', 'video', 'other')
REFERENCE_ASPECTS = ('art_style', 'camera', 'ui', 'color', 'combat', 'mood', 'other')
EVIDENCE_TYPES = ('user', 'file', 'commit', 'test', 'none')
SOURCES = ('user_instruction', 'ai_judgment')
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
DIMENSION = 384
WORK_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_decisions (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
 project_id TEXT NOT NULL CHECK(length(trim(project_id)) > 0),
 area TEXT NOT NULL CHECK(area IN ('gameplay','art','ui','code_structure','content','other')),
 decision TEXT NOT NULL CHECK(length(trim(decision)) > 0),
 reason TEXT NOT NULL CHECK(length(trim(reason)) > 0 AND length(reason) <= 300),
 alternatives TEXT NOT NULL CHECK(length(trim(alternatives)) > 0),
 evidence_type TEXT NOT NULL CHECK(evidence_type IN ('user','file','commit','test','none')),
 evidence_ref TEXT,
 source TEXT NOT NULL CHECK(source IN ('user_instruction','ai_judgment')),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','superseded')),
 supersedes TEXT REFERENCES work_decisions(id),
 superseded_by TEXT REFERENCES work_decisions(id),
 CHECK(evidence_type = 'none' OR length(trim(coalesce(evidence_ref,''))) > 0),
 CHECK(evidence_type != 'none' OR source = 'ai_judgment')
);
"""
USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_decisions (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
 project_id TEXT NOT NULL CHECK(length(trim(project_id)) > 0),
 category TEXT NOT NULL CHECK(category IN ('genre','viewpoint','art_style','mood','core_loop','platform','scope','tech_stack','ui_style','color_palette','other')),
 topic TEXT NOT NULL CHECK(length(trim(topic)) > 0),
 decision TEXT NOT NULL CHECK(length(trim(decision)) > 0),
 status TEXT NOT NULL CHECK(status IN ('confirmed','proposed')),
 user_quote TEXT NOT NULL CHECK(length(trim(user_quote)) > 0),
 assistant_reply TEXT NOT NULL CHECK(length(trim(assistant_reply)) > 0),
 ai_role TEXT NOT NULL CHECK(ai_role IN ('proposal','explanation')),
 supersedes TEXT UNIQUE REFERENCES user_decisions(id),
 reference_ids TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(reference_ids) AND json_type(reference_ids)='array')
);
"""
REFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_references (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL CHECK(length(trim(project_id)) > 0),
 kind TEXT NOT NULL CHECK(kind IN ('game','image','link','video','other')),
 title_or_url TEXT NOT NULL CHECK(length(trim(title_or_url)) > 0),
 file_path TEXT,
 user_note TEXT NOT NULL CHECK(length(trim(user_note)) > 0),
 aspects TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(aspects) AND json_type(aspects)='array')
);
"""
TOPIC_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS topic_additions (
 id TEXT PRIMARY KEY,
 created_at TEXT NOT NULL,
 project_id TEXT NOT NULL CHECK(length(trim(project_id)) > 0),
 category TEXT NOT NULL CHECK(category IN ({','.join(repr(v) for v in CATEGORIES)})),
 topic TEXT NOT NULL CHECK(length(trim(topic)) > 0),
 description TEXT NOT NULL CHECK(length(trim(description)) > 0),
 user_quote TEXT NOT NULL CHECK(length(trim(user_quote)) > 0),
 ai_interpretation TEXT NOT NULL CHECK(length(trim(ai_interpretation)) > 0),
 assistant_reply TEXT NOT NULL CHECK(length(trim(assistant_reply)) > 0),
 reason TEXT NOT NULL CHECK(length(trim(reason)) > 0 AND length(reason) <= 300),
 evidence_type TEXT NOT NULL CHECK(evidence_type IN ('user','file','commit','test','none')),
 evidence_ref TEXT,
 source TEXT NOT NULL CHECK(source IN ('user_instruction','ai_judgment')),
 catalog_path TEXT NOT NULL,
 added_content TEXT NOT NULL,
 CHECK(evidence_type = 'none' OR length(trim(coalesce(evidence_ref,''))) > 0),
 CHECK(evidence_type != 'none' OR source = 'ai_judgment')
);
"""

def emit(value, *, error=False):
    print(json.dumps(value, ensure_ascii=False, indent=2), file=sys.stderr if error else sys.stdout)

def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name}은 비어 있지 않은 문자열이어야 합니다.')
    return value

def choice(value, options, name):
    if value not in options:
        raise ValueError(f'{name} 허용값: {", ".join(options)}')

def find_project(start=None):
    """Use only the nearest marker above the execution directory."""
    location = Path(start if start is not None else Path.cwd()).resolve()
    for folder in (location, *location.parents):
        marker = folder / '.project'
        if marker.exists() or marker.is_symlink():
            if not marker.is_file() or marker.resolve().parent != folder:
                raise ValueError('유효한 프로젝트 내부 .project 마커가 필요합니다.')
            value = json.loads(marker.read_text(encoding='utf-8-sig'))
            project_id = value.get('project_id') if isinstance(value, dict) else None
            if not isinstance(project_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', project_id):
                raise ValueError('.project의 project_id가 올바르지 않습니다.')
            return folder, project_id
    raise ValueError('.project 마커가 없어 실행을 거부합니다.')

def project_path(root, path):
    root = Path(root).resolve()
    path = Path(path).expanduser()
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('프로젝트 폴더 밖 경로는 사용할 수 없습니다.')
    return resolved

def input_text(args):
    if args.input:
        return project_path(args.project_root, args.input).read_text(encoding='utf-8-sig')
    return sys.stdin.read().lstrip('\ufeff')

@lru_cache(maxsize=1)
def embedder():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    from fastembed import TextEmbedding
    runtime_file = ROOT / 'runtime.json'
    cache = (json.loads(runtime_file.read_text(encoding='utf-8'))['model_cache']
             if runtime_file.is_file() else str(ROOT / '.venv-runtime/model-cache'))
    return TextEmbedding(model_name=MODEL, cache_dir=cache,
                         local_files_only=True, threads=2)

def embed(text):
    return next(iter(embedder().embed([text])))

@contextmanager
def database(path, kind, *, write=False, project_root=None):
    """Both record types belong to the marker's fixed project database."""
    choice(kind, ('work', 'user'), 'store')
    root, project_id = find_project(project_root)
    expected = project_path(root, 'data/decisions.sqlite')
    path = project_path(root, path)
    if path != expected:
        raise ValueError('DB 경로는 프로젝트의 data/decisions.sqlite로 고정됩니다.')
    if not path.exists() and not write:
        yield None
        return
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path.as_uri() + ('?mode=rwc' if write else '?mode=ro'),
                        uri=True, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        import sqlite_vec
        c.enable_load_extension(True)
        sqlite_vec.load(c)
        c.enable_load_extension(False)
        c.execute('PRAGMA foreign_keys=ON')
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'dev_decisions' in tables:
            raise ValueError('구형 하네스 개발 기록 DB는 게임 작업 기록 DB로 사용할 수 없습니다.')
        for table in ('work_decisions', 'user_decisions', 'user_references', 'topic_additions', 'reference_traces'):
            if table in tables and c.execute(f'SELECT 1 FROM {table} WHERE project_id<>? LIMIT 1', (project_id,)).fetchone():
                raise ValueError('다른 프로젝트 ID의 기록이 있는 DB는 사용할 수 없습니다.')
        if 'decisions' in tables:
            if c.execute('SELECT count(*) FROM decisions').fetchone()[0]:
                raise ValueError('구형 기록이 있습니다. 작업/사용자 구분을 확인한 뒤 이전하거나 제거해야 합니다.')
            if write:
                c.execute('DROP TABLE decisions')
        if write:
            c.executescript(WORK_SCHEMA + USER_SCHEMA)
            expand_user_categories(c)
            c.executescript(REFERENCE_SCHEMA + TOPIC_SCHEMA)
            for table in ('topic_addition_vectors', 'work_decision_vectors', 'user_decision_vectors'):
                c.execute(f'CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0('
                          f'id TEXT PRIMARY KEY, embedding float[{DIMENSION}] distance_metric=cosine, +metadata TEXT)')
        elif f'{kind}_decisions' not in tables:
            yield None
            return
        yield c
    finally:
        c.close()

@contextmanager
def transaction(c):
    c.execute('BEGIN IMMEDIATE')
    try:
        yield
        c.commit()
    except BaseException:
        c.rollback()
        raise

def expand_user_categories(c):
    """Expand the legacy CHECK constraint without changing records or vectors."""
    def current_schema():
        return c.execute("SELECT sql FROM sqlite_master WHERE name='user_decisions'").fetchone()[0]

    def up_to_date():
        schema = current_schema()
        return all(f"'{category}'" in schema for category in CATEGORIES) and 'reference_ids' in schema

    if up_to_date():
        return
    c.execute('PRAGMA foreign_keys=OFF')
    try:
        with transaction(c):
            if up_to_date():
                return
            objects = [r[0] for r in c.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name='user_decisions' "
                "AND type IN ('index','trigger') AND sql IS NOT NULL")]
            c.execute(USER_SCHEMA.replace('CREATE TABLE IF NOT EXISTS user_decisions',
                                          'CREATE TABLE user_decisions_expanded'))
            columns = 'id,created_at,project_id,category,topic,decision,status,user_quote,assistant_reply,ai_role,supersedes'
            if 'reference_ids' in {r[1] for r in c.execute('PRAGMA table_info(user_decisions)')}:
                columns += ',reference_ids'
            c.execute(f'INSERT INTO user_decisions_expanded ({columns}) SELECT {columns} FROM user_decisions')
            c.execute('DROP TABLE user_decisions')
            c.execute('ALTER TABLE user_decisions_expanded RENAME TO user_decisions')
            for sql in objects:
                c.execute(sql)
            if c.execute('PRAGMA foreign_key_check(user_decisions)').fetchone():
                raise ValueError('분류 확장 중 기존 기록의 연결을 확인할 수 없습니다.')
    finally:
        c.execute('PRAGMA foreign_keys=ON')

def next_id(c, kind):
    number = c.execute(f'SELECT coalesce(max(cast(substr(id,3) AS INTEGER)),0)+1 FROM {kind}_decisions').fetchone()[0]
    return f'{"W" if kind == "work" else "U"}-{number:03d}'

def insert_record(c, kind, fields):
    # The record, vector and supersession share one SQLite transaction.
    record = {'id': next_id(c, kind), 'created_at': datetime.now(timezone.utc).isoformat(), **fields}
    c.execute(f'INSERT INTO {kind}_decisions ({",".join(record)}) VALUES ({",".join("?" for _ in record)})',
              [json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for v in record.values()])
    text = '\n'.join(str(record.get(k, '')) for k in ('area', 'category', 'topic', 'decision', 'reason'))
    vector = embed(text)
    c.execute(f'INSERT INTO {kind}_decision_vectors (id,embedding,metadata) VALUES (?,?,?)',
              (record['id'], vector.astype('float32').tobytes(), json.dumps({'model': MODEL})))
    return record

def add_work(args):
    nonempty(args.project_id, 'project_id')
    choice(args.area, AREAS, 'area')
    for name in ('decision', 'reason', 'alternatives'):
        nonempty(getattr(args, name), name)
    if len(args.reason) > 300:
        raise ValueError('reason은 300자 이내여야 합니다.')
    choice(args.evidence_type, EVIDENCE_TYPES, 'evidence_type')
    choice(args.source, SOURCES, 'source')
    if args.evidence_type != 'none':
        nonempty(args.evidence_ref, 'evidence_ref')
    elif args.source != 'ai_judgment':
        raise ValueError('evidence_type=none이면 source=ai_judgment만 허용합니다.')
    with database(args.work_db, 'work', write=True) as c, transaction(c):
        active = [dict(r) for r in c.execute("SELECT * FROM work_decisions WHERE project_id=? AND area=? AND status='active' ORDER BY created_at DESC,id DESC", (args.project_id, args.area))]
        emit({'same_area_active': active, 'project_id': args.project_id, 'area': args.area}, error=True)
        if active and not (args.supersedes or args.independent):
            raise ValueError('같은 프로젝트·area의 active 결정이 있습니다. 위 목록을 읽고 --supersedes ID 또는 --independent를 지정하세요.')
        if args.supersedes:
            previous = next((r for r in active if r['id'] == args.supersedes), None)
            if previous is None:
                raise ValueError('supersedes는 같은 프로젝트·area의 active 결정 ID여야 합니다.')
            if previous['source'] == 'user_instruction' and not (
                args.source == 'user_instruction' and args.evidence_type == 'user' and args.evidence_ref.strip()
            ):
                raise ValueError('사용자 지시 번복에는 source=user_instruction, evidence_type=user와 사용자의 변경 확인 발언이 필요합니다.')
        fields = {k: getattr(args, k) for k in ('project_id', 'area', 'decision', 'reason', 'alternatives', 'evidence_type', 'evidence_ref', 'source', 'supersedes')}
        record = insert_record(c, 'work', {**fields, 'status': 'active', 'superseded_by': None})
        if args.supersedes:
            c.execute("UPDATE work_decisions SET status='superseded',superseded_by=? WHERE id=?", (record['id'], args.supersedes))
        return {'saved': record, 'reference': f"refs {record['id']}"}

def user_input(args):
    nonempty(args.project_id, 'project_id')
    raw = input_text(args)
    value = json.loads(raw)
    required = {'category', 'topic', 'decision', 'status', 'user_quote', 'assistant_reply', 'ai_role'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'supersedes', 'reference_ids'}:
        raise ValueError('필수: category, topic, decision, status, user_quote, assistant_reply, ai_role. 선택: supersedes, reference_ids.')
    for name in required:
        nonempty(value[name], name)
    choice(value['category'], CATEGORIES, 'category')
    choice(value['status'], ('confirmed', 'proposed'), 'status')
    choice(value['ai_role'], ('proposal', 'explanation'), 'ai_role')
    if value.get('supersedes') is not None:
        nonempty(value['supersedes'], 'supersedes')
    if 'reference_ids' in value:
        string_list(value['reference_ids'], 'reference_ids')
    return {'project_id': args.project_id, **value, 'supersedes': value.get('supersedes')}

def add_user(args):
    value = user_input(args)
    with database(args.user_db, 'user', write=True) as c, transaction(c):
        previous = None
        current = [dict(r) for r in c.execute(
            'SELECT r.* FROM user_decisions r WHERE project_id=? AND category=? AND topic=? '
            'AND NOT EXISTS (SELECT 1 FROM user_decisions n WHERE n.supersedes=r.id) '
            'ORDER BY created_at DESC,id DESC',
            (args.project_id, value['category'], value['topic']))]
        # A proposal may coexist with a confirmed choice without replacing it.
        conflicts = [r for r in current if not (
            value['status'] == 'proposed' and r['status'] == 'confirmed')]
        if conflicts:
            emit({'same_topic_current': conflicts, 'project_id': args.project_id}, error=True)
            if value['supersedes'] not in {r['id'] for r in conflicts}:
                raise ValueError('같은 프로젝트·category·topic의 결정이 있습니다. supersedes로 이전 기록을 지정하세요.')
        if value['supersedes']:
            previous = c.execute('SELECT * FROM user_decisions WHERE id=? AND project_id=?', (value['supersedes'], args.project_id)).fetchone()
            if previous is None or previous['category'] != value['category']:
                raise ValueError('supersedes는 같은 프로젝트·category의 기록이어야 합니다.')
            if c.execute('SELECT 1 FROM user_decisions WHERE supersedes=?', (value['supersedes'],)).fetchone():
                raise ValueError('이미 대체된 기록입니다. 현재 기록을 조회하세요.')
            if previous['status'] == 'confirmed' and value['status'] == 'proposed':
                raise ValueError('제안으로 confirmed 기록을 대체할 수 없습니다. 독립된 proposed 기록으로 저장하세요.')
        if 'reference_ids' not in value:
            value['reference_ids'] = json.loads(previous['reference_ids']) if previous else []
        for reference_id in value['reference_ids']:
            if not c.execute('SELECT 1 FROM user_references WHERE id=? AND project_id=?',
                             (reference_id, args.project_id)).fetchone():
                raise ValueError('reference_ids에는 같은 프로젝트에 저장된 레퍼런스 ID만 사용할 수 있습니다.')
        return {'saved': insert_record(c, 'user', value)}

def string_list(value, name, choices=None):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f'{name}은 문자열 배열이어야 합니다.')
    if len(set(value)) != len(value):
        raise ValueError(f'{name}에는 중복 값을 넣을 수 없습니다.')
    if choices and any(v not in choices for v in value):
        raise ValueError(f'{name} 허용값: {", ".join(choices)}')
    return value

def decoded_record(row):
    record = dict(row)
    for field in ('reference_ids', 'aspects'):
        if field in record:
            record[field] = json.loads(record[field])
    return record

def reference_folder(project_root, project_id):
    # A project ID is one directory name, never a path supplied to traverse.
    if (project_id in ('.', '..') or any(ch in project_id for ch in '<>:"/\\|?*')
            or any(ord(ch) < 32 for ch in project_id) or project_id.endswith((' ', '.'))
            or project_id.split('.')[0].upper() in {
                'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('이미지 보관용 project_id는 유효한 폴더 이름이어야 합니다.')
    root = Path(project_root).resolve()
    folder = project_path(root, Path('references') / project_id)
    return root, folder

def add_reference(args):
    raw = input_text(args)
    value = json.loads(raw)
    required = {'kind', 'title_or_url', 'user_note', 'aspects'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'file_path'}:
        raise ValueError('필수: kind, title_or_url, user_note, aspects. 선택: file_path.')
    for name in ('kind', 'title_or_url', 'user_note'):
        nonempty(value[name], name)
    choice(value['kind'], REFERENCE_KINDS, 'kind')
    string_list(value['aspects'], 'aspects', REFERENCE_ASPECTS)
    source = None
    if value.get('file_path') not in (None, ''):
        nonempty(value['file_path'], 'file_path')
        if value['kind'] != 'image':
            raise ValueError('file_path는 이미지 파일을 보관할 때만 사용합니다.')
        source = project_path(args.project_root, value['file_path'])
        if not source.is_file():
            raise ValueError('file_path는 이미지 파일 경로여야 합니다.')
        root, folder = reference_folder(args.project_root, args.project_id)
    copied = None
    try:
        with database(args.user_db, 'user', write=True) as c, transaction(c):
            number = c.execute('SELECT coalesce(max(cast(substr(id,3) AS INTEGER)),0)+1 FROM user_references').fetchone()[0]
            record = {'id': f'R-{number:03d}', 'project_id': args.project_id,
                      **value, 'file_path': None}
            if source:
                folder.mkdir(parents=True, exist_ok=True)
                destination = folder / (record['id'] + source.suffix)
                if not destination.resolve().is_relative_to(root):
                    raise ValueError('레퍼런스 보관 경로는 프로젝트 폴더 안이어야 합니다.')
                with source.open('rb') as original, destination.open('xb') as saved:
                    copied = destination
                    shutil.copyfileobj(original, saved)
                record['file_path'] = destination.relative_to(root).as_posix()
            c.execute(f'INSERT INTO user_references ({",".join(record)}) VALUES ({",".join("?" for _ in record)})',
                      [json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for v in record.values()])
        return {'saved': record}
    except BaseException:
        if copied is not None:
            copied.unlink(missing_ok=True)
        raise

def reference_command(args):
    nonempty(args.project_id, 'project_id')
    if args.command == 'add':
        return add_reference(args)
    if args.command == 'trace-add':
        from reference_trace import add
        return add(args.project_root, args.id, json.loads(input_text(args)))
    with database(args.user_db, 'user', write=args.command == 'set-aspects') as c:
        exists = c is not None and c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='user_references' AND type='table'").fetchone()
        if not exists:
            if args.command in ('show', 'set-aspects'):
                raise ValueError('해당 레퍼런스가 없습니다.')
            return {'records': []}
        if args.command == 'set-aspects':
            string_list(args.aspects, 'aspects', REFERENCE_ASPECTS)
            with transaction(c):
                row = c.execute('SELECT * FROM user_references WHERE id=? AND project_id=?',
                                (args.id, args.project_id)).fetchone()
                if row is None:
                    raise ValueError('해당 레퍼런스가 없습니다.')
                c.execute('UPDATE user_references SET aspects=? WHERE id=? AND project_id=?',
                          (json.dumps(args.aspects), args.id, args.project_id))
                return {'saved': {**decoded_record(row), 'aspects': args.aspects}}
        where, values = ['project_id=?'], [args.project_id]
        if args.command == 'show':
            where.append('id=?'); values.append(args.id)
        if args.command == 'search':
            nonempty(args.query, 'query')
            search = '(instr(lower(title_or_url),lower(?)) > 0 OR instr(lower(user_note),lower(?)) > 0'
            values.extend([args.query, args.query])
            from reference_trace import exists
            if exists(c, 'reference_traces'):
                search += (' OR EXISTS(SELECT 1 FROM reference_traces t WHERE t.reference_id=user_references.id '
                           'AND t.project_id=user_references.project_id AND instr(lower('
                           "t.topic || ' ' || t.user_quote || ' ' || t.assistant_reply || ' ' || t.reason || ' ' || t.payload),lower(?))>0)")
                values.append(args.query)
            where.append(search + ')')
        rows = [decoded_record(r) for r in c.execute(
            'SELECT * FROM user_references WHERE ' + ' AND '.join(where) +
            ' ORDER BY cast(substr(id,3) AS INTEGER) DESC LIMIT ? OFFSET ?',
            [*values, getattr(args, 'limit', 10), getattr(args, 'offset', 0)])]
        if args.command == 'show':
            if not rows:
                raise ValueError('해당 레퍼런스가 없습니다.')
            from reference_trace import detail
            return {'record': detail(c, args.project_id, rows[0])}
        return {'records': rows}

def atomic_text(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=path.parent, prefix='.topic-', delete=False) as f:
            temporary = Path(f.name)
            f.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

MILESTONE_STATUSES = ('pending', 'active', 'done', 'blocked')

def read_milestones(project_root):
    root, _ = find_project(project_root)
    path = project_path(root, 'milestones.json')
    records = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    if not isinstance(records, list):
        raise ValueError('milestones.json은 마일스톤 배열이어야 합니다.')
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('마일스톤 항목은 객체여야 합니다.')
        for key in ('id', 'title', 'done_condition'):
            nonempty(record.get(key), key)
        choice(record.get('status'), MILESTONE_STATUSES, 'status')
        progress = record.get('progress')
        if progress is not None:
            if (not isinstance(progress, dict) or type(progress.get('completed')) is not int or
                    type(progress.get('total')) is not int or progress['total'] <= 0 or
                    not 0 <= progress['completed'] <= progress['total']):
                raise ValueError('마일스톤 진행 수는 0 <= completed <= total, total >= 1이어야 합니다.')
            nonempty(progress.get('note'), 'note')
    return records

def milestone_command(args):
    root, _ = find_project(args.project_root)
    path = project_path(root, 'milestones.json')
    # Serialize read/modify/write across CLI processes using the existing project DB.
    db_path = project_path(root, 'data/decisions.sqlite')
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, isolation_level=None, timeout=30)) as c, transaction(c):
        records = read_milestones(root)
        if args.command == 'list':
            return {'milestones': records}
        if args.command == 'add':
            title = nonempty(args.title, 'title')
            done = nonempty(args.done_condition, 'done-condition')
            number = max((int(r['id'][2:]) for r in records), default=0) + 1
            record = {'id': f'M-{number:03d}', 'title': title, 'done_condition': done,
                      'not_doing': args.not_doing, 'status': 'pending'}
            records.append(record)
        else:
            record = next((r for r in records if r['id'] == args.id), None)
            if record is None:
                raise ValueError('존재하지 않는 마일스톤입니다.')
            if args.command == 'set-progress':
                if record['status'] != 'active':
                    raise ValueError('active 마일스톤의 진행도만 갱신할 수 있습니다.')
                if args.total <= 0 or not 0 <= args.completed <= args.total:
                    raise ValueError('total은 1 이상, completed는 0~total 범위여야 합니다.')
                record['progress'] = {'completed': args.completed, 'total': args.total,
                                      'note': nonempty(args.note, 'note'),
                                      'updated_at': datetime.now(timezone.utc).isoformat()}
            else:
                choice(args.status, MILESTONE_STATUSES, 'status')
                if args.status == 'active' and any(r['status'] == 'active' and r['id'] != args.id for r in records):
                    raise ValueError('다른 마일스톤이 active입니다. active는 하나만 허용합니다.')
                record['status'] = args.status
        atomic_text(path, json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        return {'saved': record}

def add_topic(args):
    raw = input_text(args)
    value = json.loads(raw)
    required = {'category', 'topic', 'description', 'user_quote', 'ai_interpretation',
                'assistant_reply', 'reason', 'evidence_type', 'source'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'evidence_ref'}:
        raise ValueError('필수: ' + ', '.join(sorted(required)) + '. 선택: evidence_ref.')
    for name in required:
        nonempty(value[name], name)
    choice(value['category'], CATEGORIES, 'category')
    choice(value['source'], SOURCES, 'source')
    choice(value['evidence_type'], EVIDENCE_TYPES, 'evidence_type')
    if len(value['reason']) > 300:
        raise ValueError('reason은 300자 이내여야 합니다.')
    if value['evidence_type'] != 'none':
        nonempty(value.get('evidence_ref'), 'evidence_ref')
    elif value['source'] != 'ai_judgment':
        raise ValueError('evidence_type=none이면 source=ai_judgment만 허용합니다.')
    for name in ('topic', 'description'):
        if any(ch in value[name] for ch in '\r\n|') or value[name] != value[name].strip():
            raise ValueError(f'{name}은 앞뒤 공백·줄바꿈·표 구분자 없는 한 줄로 입력하세요.')
    catalog = project_path(args.project_root, 'catalogs/product-design-topics.md')
    added_content = f"| {value['topic']} | {value['description']} |"
    before = None
    changed = False
    try:
        with database(args.user_db, 'user', write=True) as c, transaction(c):
            before = catalog.read_text(encoding='utf-8')
            lines = before.splitlines(keepends=True)
            heading = f"## {value['category']}"
            starts = [i for i, line in enumerate(lines) if line.strip() == heading]
            if len(starts) != 1:
                raise ValueError('topic 표에서 해당 category 섹션을 하나로 찾을 수 없습니다.')
            start = starts[0] + 1
            end = next((i for i in range(start, len(lines)) if lines[i].startswith('## ')), len(lines))
            rows = [i for i in range(start, end) if lines[i].startswith('|')]
            if len(rows) < 2:
                raise ValueError('category 섹션에 topic 표가 없습니다.')
            if any(lines[i].split('|')[1].strip() == value['topic'] for i in rows):
                raise ValueError('같은 category·topic이 이미 표에 있습니다. 기존 항목을 사용하세요.')
            number = c.execute('SELECT coalesce(max(cast(substr(id,3) AS INTEGER)),0)+1 FROM topic_additions').fetchone()[0]
            record = {'id': f'T-{number:03d}', 'created_at': datetime.now(timezone.utc).isoformat(),
                      'project_id': args.project_id, **value, 'evidence_ref': value.get('evidence_ref'),
                      'catalog_path': catalog.relative_to(Path(args.project_root).resolve()).as_posix(), 'added_content': added_content}
            vector = embed('\n'.join(record[k] for k in (
                'category', 'topic', 'description', 'user_quote', 'ai_interpretation', 'assistant_reply', 'reason')))
            c.execute(f'INSERT INTO topic_additions ({",".join(record)}) VALUES ({",".join("?" for _ in record)})', list(record.values()))
            c.execute('INSERT INTO topic_addition_vectors (id,embedding,metadata) VALUES (?,?,?)',
                      (record['id'], vector.astype('float32').tobytes(), json.dumps({'model': MODEL})))
            insertion = rows[-1] + 1
            if not lines[insertion - 1].endswith('\n'):
                lines[insertion - 1] += '\n'
            lines.insert(insertion, added_content + '\n')
            atomic_text(catalog, ''.join(lines))
            changed = True
        return {'saved': record}
    except BaseException:
        if changed:
            atomic_text(catalog, before)
        raise

def topic_command(args):
    nonempty(args.project_id, 'project_id')
    if args.command == 'add':
        return add_topic(args)
    with database(args.user_db, 'user') as c:
        if c is None or not c.execute("SELECT 1 FROM sqlite_master WHERE name='topic_additions' AND type='table'").fetchone():
            if args.command == 'show':
                raise ValueError('해당 topic 추가 기록이 없습니다.')
            return {'records': []}
        conditions, values = ['r.project_id=?'], [args.project_id]
        if getattr(args, 'category', None):
            conditions.append('r.category=?'); values.append(args.category)
        if args.command == 'show':
            conditions.append('r.id=?'); values.append(args.id)
        if args.command == 'search':
            nonempty(args.query, 'query')
            if args.semantic:
                return semantic_search(c, 'topic', conditions, values, args)
            columns = ('topic', 'description', 'user_quote', 'ai_interpretation', 'assistant_reply', 'reason', 'evidence_ref', 'added_content')
            conditions.append('(' + ' OR '.join(f"instr(lower(coalesce(r.{col},'')),lower(?)) > 0" for col in columns) + ')')
            values.extend([args.query] * len(columns))
        rows = [dict(r) for r in c.execute('SELECT r.* FROM topic_additions r WHERE ' +
            ' AND '.join(conditions) + ' ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?',
            [*values, getattr(args, 'limit', 10), getattr(args, 'offset', 0)])]
        if args.command == 'show':
            if not rows:
                raise ValueError('해당 topic 추가 기록이 없습니다.')
            return {'record': rows[0]}
        return {'records': rows}

def filters(args, kind):
    nonempty(args.project_id, 'project_id')
    conditions, values = ['r.project_id=?'], [args.project_id]
    if kind == 'user':
        if args.command != 'show':
            conditions.append('NOT EXISTS (SELECT 1 FROM user_decisions n WHERE n.supersedes=r.id)')
        if getattr(args, 'category', None):
            conditions.append('r.category=?'); values.append(args.category)
    elif getattr(args, 'area', None):
        conditions.append('r.area=?'); values.append(args.area)
    if getattr(args, 'status', None):
        conditions.append('r.status=?'); values.append(args.status)
    return conditions, values

def read_records(args, kind):
    path = args.work_db if kind == 'work' else args.user_db
    conditions, values = filters(args, kind)
    with database(path, kind) as c:
        if c is None:
            if args.command in ('why', 'show'):
                raise ValueError('해당 기록이 없습니다.')
            return {'records': []}
        if args.command in ('why', 'show'):
            conditions.append('r.id=?'); values.append(args.id)
        if args.command == 'search':
            nonempty(args.query, 'query')
            if args.semantic:
                return semantic_search(c, kind, conditions, values, args)
            columns = ('decision', 'reason', 'alternatives', 'evidence_ref') if kind == 'work' else ('topic', 'decision', 'user_quote', 'assistant_reply')
            conditions.append('(' + ' OR '.join(f"instr(lower(coalesce(r.{col},'')),lower(?)) > 0" for col in columns) + ')')
            values.extend([args.query] * len(columns))
        where = ' AND '.join(conditions) or '1'
        rows = [decoded_record(r) for r in c.execute(
            f'SELECT r.* FROM {kind}_decisions r WHERE {where} ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?',
            [*values, getattr(args, 'limit', 10), getattr(args, 'offset', 0)])]
        if args.command in ('why', 'show'):
            if not rows:
                raise ValueError('해당 기록이 없습니다.')
            if kind == 'user':
                next_row = c.execute('SELECT id FROM user_decisions WHERE supersedes=?', (rows[0]['id'],)).fetchone()
                rows[0]['superseded_by'] = next_row[0] if next_row else None
            return {'record': rows[0]}
        return {'records': rows}

def semantic_search(c, kind, conditions, values, args):
    """Rank only the scoped stored vectors, never another project's records."""
    import numpy as np
    from semantica.vector_store import SQLiteVecStore
    where = ' AND '.join(conditions) or '1'
    table, vectors_table = ('topic_additions', 'topic_addition_vectors') if kind == 'topic' else (f'{kind}_decisions', f'{kind}_decision_vectors')
    candidates = c.execute(f'SELECT r.*,v.embedding FROM {table} r JOIN {vectors_table} v ON v.id=r.id WHERE {where}', values).fetchall()
    if not candidates:
        return {'records': [], 'search_mode': 'semantic'}
    # The authoritative records/vectors stay on disk. Scope before similarity ranking.
    with closing(SQLiteVecStore(db_path=':memory:', table_name='candidates', dimension=DIMENSION, distance_metric='cosine')) as index:
        records, vectors = [], []
        for row in candidates:
            record = decoded_record(row)
            vectors.append(np.frombuffer(record.pop('embedding'), dtype=np.float32).copy())
            records.append(record)
        index.add(vectors=vectors, ids=[r['id'] for r in records], metadata=records)
        count = min(args.limit + args.offset, len(records))
        found = index.search(embed(args.query), top_k=count)[args.offset:]
        return {'records': [{**r['metadata'], 'similarity_score': r['score']} for r in found], 'search_mode': 'semantic'}

def bounded(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError('limit은 1~100 범위입니다.')
    return number

def offset_number(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('offset은 0 이상이어야 합니다.')
    return number

def pagination(p):
    p.add_argument('--limit', type=bounded, default=10)
    p.add_argument('--offset', type=offset_number, default=0)

def parser():
    root = argparse.ArgumentParser(description='프로젝트별 작업 결정 / 사용자 결정')
    stores = root.add_subparsers(dest='store', required=True)
    work = stores.add_parser('work', help='A: 게임 제작 AI의 작업 결정')
    commands = work.add_subparsers(dest='command', required=True)
    add = commands.add_parser('add', help='A: 작업 결정 추가')
    add.add_argument('--area', required=True, choices=AREAS)
    for name in ('decision', 'reason', 'alternatives'):
        add.add_argument('--' + name, required=True)
    add.add_argument('--evidence-type', required=True, choices=EVIDENCE_TYPES)
    add.add_argument('--evidence-ref')
    add.add_argument('--source', required=True, choices=SOURCES)
    conflict = add.add_mutually_exclusive_group()
    conflict.add_argument('--supersedes')
    conflict.add_argument('--independent', action='store_true')
    pagination(commands.add_parser('recent', help='A: 최근 기록, 기본 10건'))
    listing = commands.add_parser('list', help='A: 영역별 조회, 기본 10건')
    listing.add_argument('--area', required=True, choices=AREAS)
    listing.add_argument('--status', choices=('active', 'superseded'), default='active')
    pagination(listing)
    why = commands.add_parser('why', help='A: 결정 근거 조회'); why.add_argument('id')
    search = commands.add_parser('search', help='A: 키워드 검색'); search.add_argument('query')
    search.add_argument('--area', choices=AREAS)
    search.add_argument('--status', choices=('active', 'superseded'), default='active')
    search.add_argument('--semantic', action='store_true', help='키워드 대신 Semantica 의미 검색')
    pagination(search)
    users = stores.add_parser('user', help='B: 최종 사용자의 게임 결정')
    sub = users.add_subparsers(dest='command', required=True)
    for command in ('add', 'list', 'show', 'search'):
        p = sub.add_parser(command)
        if command == 'add':
            p.add_argument('--input', help='UTF-8 JSON 파일; 생략하면 stdin')
        elif command == 'show':
            p.add_argument('id')
        else:
            p.add_argument('--category', choices=CATEGORIES)
            p.add_argument('--status', choices=('confirmed', 'proposed'))
            pagination(p)
            if command == 'search':
                p.add_argument('query'); p.add_argument('--semantic', action='store_true')
    references = stores.add_parser('reference', help='결정의 근거가 되는 레퍼런스')
    sub = references.add_subparsers(dest='command', required=True)
    for command in ('add', 'list', 'show', 'search', 'set-aspects', 'trace-add'):
        p = sub.add_parser(command)
        if command == 'add':
            p.add_argument('--input', help='UTF-8 JSON 파일; 생략하면 stdin')
        elif command in ('show', 'set-aspects', 'trace-add'):
            p.add_argument('id')
            if command == 'set-aspects':
                p.add_argument('--aspects', nargs='*', required=True, choices=REFERENCE_ASPECTS)
            if command == 'trace-add':
                p.add_argument('--input', help='UTF-8 JSON 파일; 생략하면 stdin')
        else:
            pagination(p)
            if command == 'search':
                p.add_argument('query')
    topics = stores.add_parser('topic', help='topic 표 추가와 근거 기록')
    sub = topics.add_subparsers(dest='command', required=True)
    for command in ('add', 'list', 'show', 'search'):
        p = sub.add_parser(command)
        if command == 'add':
            p.add_argument('--input', help='UTF-8 JSON 파일; 생략하면 stdin')
        elif command == 'show':
            p.add_argument('id')
        else:
            p.add_argument('--category', choices=CATEGORIES)
            pagination(p)
            if command == 'search':
                p.add_argument('query'); p.add_argument('--semantic', action='store_true')
    milestones = stores.add_parser('milestone', help='제작 마일스톤')
    sub = milestones.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('--title', required=True)
    add.add_argument('--done-condition', required=True)
    add.add_argument('--not-doing', required=True)
    status = sub.add_parser('set-status')
    status.add_argument('id')
    status.add_argument('status', choices=MILESTONE_STATUSES)
    progress = sub.add_parser('set-progress')
    progress.add_argument('id')
    progress.add_argument('--completed', type=int, required=True)
    progress.add_argument('--total', type=int, required=True)
    progress.add_argument('--note', required=True)
    sub.add_parser('list')
    assets = stores.add_parser('asset', help='프로젝트 에셋 관리')
    sub = assets.add_subparsers(dest='command', required=True)
    for name in ('add', 'update', 'list', 'show', 'history'):
        p = sub.add_parser(name)
        if name in ('update', 'show', 'history'):
            p.add_argument('id')
        if name in ('add', 'update'):
            p.add_argument('--input', help='UTF-8 JSON 파일; 생략하면 stdin')
        if name == 'update':
            p.add_argument('--revision', type=int, required=True)
        if name == 'list':
            p.add_argument('--kind', choices=('image', 'sound'))
            p.add_argument('--status', choices=('temporary', 'proposed', 'confirmed', 'retired'))
            p.add_argument('--query')
    return root

def run(args):
    args.project_root, args.project_id = find_project()
    args.user_db = args.work_db = project_path(args.project_root, 'data/decisions.sqlite')
    if args.store == 'asset':
        from asset_store import command
        return command(args)
    if args.store == 'milestone':
        return milestone_command(args)
    if args.store == 'topic':
        return topic_command(args)
    if args.store == 'reference':
        return reference_command(args)
    if args.store == 'user':
        nonempty(args.project_id, 'project_id')
        return add_user(args) if args.command == 'add' else read_records(args, 'user')
    return add_work(args) if args.command == 'add' else read_records(args, 'work')

def main():
    args = parser().parse_args()
    try:
        emit(run(args)); return 0
    except Exception as error:
        emit({'error': str(error)}, error=True); return 1

if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
