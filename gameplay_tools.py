"""Project-local play saves, localization and playable design records."""
from message_catalog import text as _msg, bundle_runtime
import argparse
import json
import re
import uuid
from pathlib import Path

import content_editor as content
import creator_tools as creator
import production_tools as production
from decisions import find_project, project_path, atomic_text

KINDS = ('play_save', 'localization', 'experiment', 'integration', 'content_plan')


def object_value(value):
    if not isinstance(value, dict): raise ValueError(_msg('py.gameplay_tools.expected.an.object'))
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 2000000:
        raise ValueError(_msg('py.gameplay_tools.record.exceeds.mb'))
    return value


def save_record(root, kind, value, revision=None):
    with content.database(root) as db:
        old = content.get(db, kind, value['id']) if value.get('id') else None
        if old and old['revision'] != revision: raise ValueError(_msg('py.gameplay_tools.record.changed.reload.before.saving'))
        record = {**value, 'id': old['id'] if old else kind.upper() + '-' + uuid.uuid4().hex[:12],
                  'revision': uuid.uuid4().hex, 'updated_at': content.timestamp()}
        content.put(db, kind, record['id'], record)
        content.put(db, kind + '_history', record['revision'], record)
    return record


def snapshot(value):
    object_value(value)
    if set(value) != {'adapter', 'version', 'state'}: raise ValueError(_msg('py.gameplay_tools.save.requires.adapter.version.and.state'))
    content.text(value['adapter'], 'adapter', 120)
    if type(value['version']) is not int or value['version'] < 1: raise ValueError(_msg('py.gameplay_tools.save.version.must.be.a.positive.integer'))
    if not isinstance(value['state'], (dict, list)): raise ValueError(_msg('py.gameplay_tools.save.state.must.be.a.json.object.or'))
    return value


def play_save(root, value):
    object_value(value)
    kind = value.get('kind', 'slot')
    if kind not in ('slot', 'point', 'backup', 'migration'): raise ValueError(_msg('py.gameplay_tools.unknown.play.save.kind'))
    entry = content.text(value.get('entry'), 'entry', 500)
    if entry not in creator.game_files(root) or not entry.lower().endswith(('.html', '.htm')):
        raise ValueError(_msg('py.gameplay_tools.choose.an.existing.html.entry'))
    state = snapshot(value.get('snapshot'))
    parent = value.get('parent_id')
    if parent:
        with content.database(root) as db: old = content.get(db, 'play_save', parent)
        if old['snapshot']['adapter'] != state['adapter'] or old['entry'] != entry: raise ValueError(_msg('py.gameplay_tools.save.adapter.or.entry.mismatch'))
    return save_record(root, 'play_save', {'name': content.text(value.get('name'), 'name', 200), 'kind': kind,
        'entry': entry, 'snapshot': state, 'parent_id': parent, 'game_fingerprint': creator.manifest(root)})


def localization_read(root, key):
    with content.database(root) as db: record = content.get(db, 'localization', key)
    path = content.file_path(root, record['path'])
    raw = path.read_bytes()
    if len(raw) > 2000000: raise ValueError(_msg('py.gameplay_tools.localization.file.exceeds.mb'))
    data = json.loads(raw.decode('utf-8-sig'))
    validate_messages(data, record['base_locale'])
    issues = []
    base = data[record['base_locale']]
    for locale, messages in data.items():
        for name, original in base.items():
            if not messages.get(name): issues.append({'locale': locale, 'key': name, 'type': 'missing'})
            elif tokens(original) != tokens(messages[name]): issues.append({'locale': locale, 'key': name, 'type': 'variables'})
    return {'record': record, 'messages': data, 'digest': content.digest(raw), 'issues': issues}


def tokens(value):
    return sorted(set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', value)))


def validate_messages(value, base):
    object_value(value)
    if base not in value or not isinstance(value[base], dict) or not value[base]: raise ValueError(_msg('py.gameplay_tools.base.language.needs.game.strings'))
    for locale, messages in value.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,34}', locale) or not isinstance(messages, dict): raise ValueError(_msg('py.gameplay_tools.invalid.language.catalog'))
        for key, message in messages.items():
            content.text(key, 'key', 200)
            if not isinstance(message, str) or len(message) > 20000: raise ValueError(_msg('py.gameplay_tools.messages.must.be.strings.at.most.characters'))


def localization_register(root, value, revision=None):
    object_value(value)
    path = content.file_path(root, value.get('path'))
    if path.suffix.lower() != '.json' or not path.is_file(): raise ValueError(_msg('py.gameplay_tools.register.an.existing.json.catalog'))
    if path.stat().st_size > 2000000: raise ValueError(_msg('py.gameplay_tools.localization.file.exceeds.mb'))
    base = content.text(value.get('base_locale'), _msg('py.gameplay_tools.base.locale'), 35)
    validate_messages(json.loads(path.read_text(encoding='utf-8-sig')), base)
    with content.database(root) as db:
        if any(r['path'] == path.relative_to(root).as_posix() and r['id'] != value.get('id') for r in content.entries(db, 'localization')):
            raise ValueError(_msg('py.gameplay_tools.this.catalog.is.already.registered'))
    return save_record(root, 'localization', {'id': value.get('id'), 'name': content.text(value.get('name'), 'name', 200),
        'path': path.relative_to(root).as_posix(), 'base_locale': base}, revision)


def localization_edit(root, value):
    info = localization_read(root, value.get('id'))
    if info['digest'] != value.get('digest') or info['record']['revision'] != value.get('revision'): raise ValueError(_msg('py.gameplay_tools.catalog.changed.reload.before.saving'))
    messages = value.get('messages'); validate_messages(messages, info['record']['base_locale'])
    # Keys belong to game code. This editor changes translations, not identifiers.
    if set(messages[info['record']['base_locale']]) != set(info['messages'][info['record']['base_locale']]): raise ValueError(_msg('py.gameplay_tools.keep.the.existing.game.string.keys'))
    for locale, values in messages.items():
        for key, message in values.items():
            if key not in messages[info['record']['base_locale']]: raise ValueError(_msg('py.gameplay_tools.unknown.game.string.key'))
            if message and tokens(message) != tokens(messages[info['record']['base_locale']][key]): raise ValueError(_msg('py.gameplay_tools.translation.variables.do.not.match.the.base.language'))
    path = content.file_path(root, info['record']['path'])
    backup = project_path(root, 'data/localization-history/' + uuid.uuid4().hex + '.json')
    backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(path.read_bytes())
    atomic_text(path, json.dumps(messages, ensure_ascii=False, indent=2) + '\n')
    with content.database(root) as db:
        content.put(db, 'localization_edit', uuid.uuid4().hex, {'id': info['record']['id'], 'backup': backup.relative_to(root).as_posix(), 'updated_at': content.timestamp()})
    return localization_read(root, info['record']['id'])


def rows(value, fields, limit=200):
    if not isinstance(value, list) or not 1 <= len(value) <= limit: raise ValueError(f'Expected 1–{limit} rows.')
    if any(not isinstance(row, dict) for row in value): raise ValueError(_msg('py.gameplay_tools.each.row.must.be.an.object'))
    return [{field: content.text(row.get(field), field, 4000) for field in fields} for row in value if isinstance(row, dict)]


def design_save(root, kind, value, revision=None):
    object_value(value)
    if kind not in ('experiment', 'integration', 'content_plan'): raise ValueError(_msg('py.gameplay_tools.unknown.design.type'))
    record = {'id': value.get('id'), 'name': content.text(value.get('name'), 'name', 200),
              'user_quote': content.text(value.get('user_quote'), 'user_quote', 10000),
              'hypothesis': content.text(value.get('hypothesis'), 'hypothesis', 10000), 'status': 'proposed'}
    if kind == 'experiment':
        entry = content.text(value.get('entry'), 'entry', 500)
        if entry not in creator.game_files(root): raise ValueError(_msg('py.gameplay_tools.choose.an.existing.game.entry'))
        record.update(entry=entry, variable=content.text(value.get('variable'), 'variable'),
                      invariants=content.text(value.get('invariants'), 'invariants'),
                      observation=content.text(value.get('observation'), 'observation'),
                      candidates=rows(value.get('candidates'), ('name', 'change'), 4))
        if len(record['candidates']) < 2: raise ValueError(_msg('py.gameplay_tools.use.at.least.two.candidates'))
    elif kind == 'integration':
        graph = production.graph(root)
        if value.get('fingerprint') != graph['fingerprint']: raise ValueError(_msg('py.gameplay_tools.relationships.changed.reload.evidence'))
        ids = value.get('node_ids', [])
        if not isinstance(ids, list) or any(i not in {n['id'] for n in graph['nodes']} for i in ids): raise ValueError(_msg('py.gameplay_tools.choose.current.relationship.records'))
        record.update(fingerprint=graph['fingerprint'], node_ids=ids,
                      flow=rows(value.get('flow'), ('action', 'state_change', 'existing_connection', 'unresolved')))
    else:
        count = value.get('target_count')
        if type(count) is not int or not 1 <= count <= 200: raise ValueError(_msg('py.gameplay_tools.choose.a.target.count.from.to'))
        record.update(target_count=count, units=rows(value.get('units'), ('name', 'situation', 'player_action', 'reuse', 'outcome')))
        signatures = [tuple(r[f].strip().casefold() for f in ('situation', 'player_action', 'reuse', 'outcome')) for r in record['units']]
        record['repeated_rows'] = [i + 1 for i, s in enumerate(signatures) if s in signatures[:i]]
        record['remaining'] = count - len(record['units'])
    if value.get('id'):
        with content.database(root) as db: previous = content.get(db, kind, value['id'])
        if previous.get('status') != 'proposed': raise ValueError(_msg('py.gameplay_tools.create.a.new.proposal.to.change.an.approved'))
        if previous.get('variants'): raise ValueError(_msg('py.gameplay_tools.create.a.new.experiment.after.generating.candidates'))
    return save_record(root, kind, record, revision)


def get_record(root, kind, key, revision):
    with content.database(root) as db: value = content.get(db, kind, key)
    if value['revision'] != revision: raise ValueError(_msg('py.gameplay_tools.record.changed.reload.first'))
    return value


def experiment_build(root, key, revision):
    record = get_record(root, 'experiment', key, revision)
    if record.get('variants'): raise ValueError(_msg('py.gameplay_tools.candidates.already.exist'))
    variants = []
    for candidate in record['candidates']:
        hypothesis = json.dumps({'hypothesis': record['hypothesis'], 'variable': record['variable'],
            'invariants': record['invariants'], 'observation': record['observation'], 'candidate': candidate}, ensure_ascii=False)
        variants.append(creator.variant_create(root, candidate['name'], hypothesis, record['entry'])['id'])
    return save_record(root, 'experiment', {**record, 'variants': variants}, revision)


def approve(root, kind, key, revision, quote, chosen=None):
    record = get_record(root, kind, key, revision)
    if record['status'] == 'approved' and not record.get('decision_id'): return record_selection(root, kind, record)
    if record['status'] != 'proposed': raise ValueError(_msg('py.gameplay_tools.already.selected'))
    quote = content.text(quote, 'user_quote', 10000)
    if kind == 'experiment':
        if chosen not in record.get('variants', []): raise ValueError(_msg('py.gameplay_tools.choose.a.generated.candidate'))
        # Adoption checks the unchanged main baseline and preserves its prior files.
        creator.variant_adopt(root, chosen)
        record['selected_variant'] = chosen
    elif kind == 'integration':
        if record['fingerprint'] != production.graph(root)['fingerprint']: raise ValueError(_msg('py.gameplay_tools.relationships.changed.review.the.proposal.again'))
    elif kind == 'content_plan':
        if record['remaining'] != 0: raise ValueError(_msg('py.gameplay_tools.fill.the.selected.number.of.content.units.before'))
    else: raise ValueError(_msg('py.gameplay_tools.unknown.design.type'))
    record = save_record(root, kind, {**record, 'status': 'approved', 'selection_quote': quote}, revision)
    return record_selection(root, kind, record)


def record_selection(root, kind, record):
    """Use the normal decision/vector writer, with a distinct design-selection topic."""
    import decisions
    root, pid = find_project(root)
    topic = kind + ':' + record['id']
    with decisions.database(project_path(root, 'data/decisions.sqlite'), 'user', write=True, project_root=root) as db, decisions.transaction(db):
        existing = db.execute('SELECT id FROM user_decisions WHERE project_id=? AND topic=?', (pid, topic)).fetchone()
        if existing: identity = existing['id']
        else:
            result = decisions.insert_record(db, 'user', {'project_id': pid, 'category': 'scope' if kind == 'content_plan' else 'core_loop',
                'topic': topic, 'decision': json.dumps({k: v for k, v in record.items() if k not in ('game_fingerprint',)}, ensure_ascii=False),
                'status': 'confirmed', 'user_quote': record['selection_quote'], 'assistant_reply': record['hypothesis'],
                'ai_role': 'proposal', 'supersedes': None, 'reference_ids': []})
            identity = result['id']
    with content.database(root) as db:
        record['decision_id'] = identity
        content.put(db, kind, record['id'], record)
        content.put(db, kind + '_history', record['revision'], record)
    return record


def implementation(root, kind, value, revision):
    if kind not in ('experiment', 'integration', 'content_plan'): raise ValueError(_msg('py.gameplay_tools.unknown.design.type'))
    record = get_record(root, kind, value.get('id'), revision)
    if record['status'] != 'approved': raise ValueError(_msg('py.gameplay_tools.use.an.approved.design'))
    evidence = rows(value.get('evidence'), ('path', 'quote'))
    files = creator.game_files(root)
    for item in evidence:
        path = files.get(item['path'])
        if path is None or path.stat().st_size > 2000000 or item['quote'] not in path.read_text(encoding='utf-8-sig'):
            raise ValueError(_msg('py.gameplay_tools.implementation.evidence.must.quote.current.game.code'))
        item['sha256'] = creator.file_hash(path)
    import decisions
    _, pid = find_project(root)
    ids = value.get('work_ids')
    if not isinstance(ids, list) or not ids: raise ValueError(_msg('py.gameplay_tools.link.at.least.one.work.decision'))
    with decisions.database(project_path(root, 'data/decisions.sqlite'), 'work', project_root=root) as db:
        for identity in ids:
            if not db.execute("SELECT 1 FROM work_decisions WHERE project_id=? AND id=? AND status='active'", (pid, identity)).fetchone(): raise ValueError(_msg('py.gameplay_tools.use.current.work.decisions.from.this.project'))
    record['implementation'] = {'evidence': evidence, 'work_ids': ids, 'note': content.text(value.get('note'), 'note')}
    return save_record(root, kind, {**record, 'status': 'implemented'}, revision)


def runtime_publish(root):
    source = Path(__file__).resolve().parent / 'gameplay-runtime.js'
    if not source.is_file(): source = Path(__file__).resolve().parent / 'web/gameplay-runtime.js'
    target = project_path(root, 'game-tools/gameplay-runtime.js'); target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = project_path(root, 'data/runtime-history/' + uuid.uuid4().hex + '.js')
        backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(target.read_bytes())
    atomic_text(target, bundle_runtime(source.read_text(encoding='utf-8')))
    return {'path': target.relative_to(root).as_posix()}


def command(args):
    from decisions import input_text
    if args.command == 'runtime': return runtime_publish(args.project_root)
    if args.command == 'applied': return implementation(args.project_root, args.kind, json.loads(input_text(args)), args.revision)
    if args.command == 'save':
        value = json.loads(input_text(args))
        if args.kind == 'localization': return localization_register(args.project_root, value, args.revision)
        if args.kind == 'play_save': return play_save(args.project_root, value)
        return design_save(args.project_root, args.kind, value, args.revision)
    with content.database(args.project_root) as db:
        return content.get(db, args.kind, args.id) if args.command == 'show' else {'items': content.entries(db, args.kind)}
