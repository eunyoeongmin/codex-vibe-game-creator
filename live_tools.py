"""Game-owned systems, bounded play observations and state-bound alternatives."""
import json
import re
import uuid
from pathlib import Path

import content_editor as content
import creator_tools as creator
import gameplay_tools as gameplay
import production_tools as production
from decisions import find_project, project_path, atomic_text
from message_catalog import text as msg, bundle_runtime

REGISTRY = 'content/creator-systems.json'
NODE_KINDS = ('system', 'entity', 'stage', 'event', 'reward', 'unlock')


def build_fingerprint(files):
    return content.digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def fail(key):
    raise ValueError(msg('live.' + key))


def items(value, maximum=200):
    if not isinstance(value, list) or len(value) > maximum: fail('invalid_list')
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value): fail('invalid_id')
    return value


def strings(value, maximum=40):
    return [content.text(v, 'value', 300) for v in items(value, maximum)]


def evidence(root, value):
    files = creator.game_files(root)
    result = []
    for item in items(value, 20):
        if not isinstance(item, dict): fail('invalid_evidence')
        path, quote = item.get('path'), content.text(item.get('quote'), 'quote', 4000)
        file = files.get(path)
        if not file or file.stat().st_size > 2000000 or quote not in file.read_text(encoding='utf-8-sig'): fail('invalid_evidence')
        result.append({'path': path, 'quote': quote, 'sha256': creator.file_hash(file)})
    return result


def validate_registry(root, value):
    gameplay.object_value(value)
    entry = content.text(value.get('entry'), 'entry', 500)
    if entry not in creator.game_files(root) or not entry.endswith(('.html', '.htm')): fail('entry')
    # Existing record graph supplies project-scoped asset, decision and data identities.
    known = {node['id']: node for node in production.graph(root)['nodes']}
    def refs(raw):
        values = strings(raw)
        if any(v not in known for v in values): fail('references')
        return values
    nodes, edges, targets = [], [], []
    for node in items(value.get('nodes')):
        if not isinstance(node, dict): fail('invalid_list')
        if node.get('kind') not in NODE_KINDS: fail('node_kind')
        nodes.append({'id': identity(node.get('id')), 'name': content.text(node.get('name'), 'name', 150),
            'kind': node['kind'], 'role': content.text(node.get('role'), 'role', 2000),
            'reads': strings(node.get('reads', [])), 'writes': strings(node.get('writes', [])),
            'refs': refs(node.get('refs', [])), 'evidence': evidence(root, node.get('evidence', []))})
    ids = {n['id'] for n in nodes}
    if not ids or len(ids) != len(nodes): fail('duplicate_id')
    for edge in items(value.get('edges'), 500):
        if not isinstance(edge, dict): fail('invalid_list')
        if edge.get('source') not in ids or edge.get('target') not in ids: fail('edge_target')
        if edge.get('status') not in ('planned', 'implemented'): fail('edge_status')
        proof = evidence(root, edge.get('evidence', []))
        if edge['status'] == 'implemented' and not proof: fail('invalid_evidence')
        edges.append({'id': identity(edge.get('id')), 'source': edge['source'], 'target': edge['target'],
            'trigger': content.text(edge.get('trigger'), 'trigger', 1000),
            'condition': str(edge.get('condition', ''))[:2000], 'effect': content.text(edge.get('effect'), 'effect', 2000),
            'status': edge['status'], 'refs': refs(edge.get('refs', [])), 'evidence': proof})
    if len({e['id'] for e in edges}) != len(edges): fail('duplicate_id')
    if ids & {e['id'] for e in edges}: fail('duplicate_id')
    for target in items(value.get('targets')):
        if not isinstance(target, dict): fail('invalid_list')
        selected = strings(target.get('node_ids', []))
        if not selected or any(n not in ids for n in selected): fail('edge_target')
        selector = target.get('selector', '')
        if not isinstance(selector, str) or len(selector) > 500: fail('invalid_target')
        targets.append({'id': identity(target.get('id')), 'name': content.text(target.get('name'), 'name', 150),
                        'node_ids': selected, 'selector': selector, 'refs': refs(target.get('refs', []))})
    if len({t['id'] for t in targets}) != len(targets): fail('duplicate_id')
    return {'entry': entry, 'nodes': nodes, 'edges': edges, 'targets': targets}


def registry(root):
    path = project_path(root, REGISTRY)
    if not path.is_file(): return None
    if path.stat().st_size > 2000000: fail('invalid_list')
    value = json.loads(path.read_text(encoding='utf-8'))
    with content.database(root) as db: saved = content.get(db, 'live_registry', 'current')
    if saved != value: fail('registry_changed')
    return saved


def register(root, value, revision=None):
    root, _ = find_project(root)
    old = registry(root)
    if old and revision != old['revision']: fail('registry_changed')
    result = {**validate_registry(root, value), 'id': 'current', 'revision': uuid.uuid4().hex, 'updated_at': content.timestamp()}
    path = project_path(root, REGISTRY); path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding='utf-8') if old else None
    try:
        with content.database(root) as db:
            content.put(db, 'live_registry', 'current', result)
            content.put(db, 'live_registry_history', result['revision'], result)
            atomic_text(path, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    except Exception:
        if previous is not None: atomic_text(path, previous)
        elif path.exists(): path.unlink()
        raise
    return result


def fresh(root, item):
    return all(project_path(root, e['path']).is_file() and creator.file_hash(project_path(root, e['path'])) == e['sha256'] for e in item['evidence'])


def graph(root, observation_id=None):
    value = registry(root)
    if not value: return {'registry': None, 'nodes': [], 'edges': [], 'targets': []}
    observed = {}
    if observation_id:
        with content.database(root) as db: observation = content.get(db, 'live_point', observation_id)
        if observation['registry']['revision'] == value['revision'] and observation['fingerprint'] == creator.manifest(root):
            for event in observation['events']: observed[event['edge_id']] = observed.get(event['edge_id'], 0) + 1
    return {**value, 'registry': value['revision'],
            'nodes': [{**n, 'evidence_current': fresh(root, n)} for n in value['nodes']],
            'edges': [{**e, 'evidence_current': fresh(root, e), 'observed': observed.get(e['id'], 0)} for e in value['edges']]}


def points(root):
    with content.database(root) as db:
        return [{k: r[k] for k in ('id', 'name', 'entry', 'created_at', 'selected', 'variant_id', 'status')} for r in content.entries(db, 'live_point')]


def point(root, key):
    with content.database(root) as db: return content.get(db, 'live_point', key)


def capture(root, body):
    gameplay.object_value(body)
    value = registry(root)
    if not value or value['revision'] != body.get('registry_revision') or value['entry'] != body.get('entry'): fail('registry_changed')
    selected = body.get('selected')
    if selected not in {t['id'] for t in value['targets']}: fail('invalid_target')
    fingerprint = creator.manifest(root)
    if body.get('build_fingerprint') != build_fingerprint(fingerprint): fail('game_changed')
    events = []
    edge_ids = {e['id'] for e in value['edges']}
    last = -1
    for event in items(body.get('events', []), 120):
        if not isinstance(event, dict): fail('invalid_events')
        if event.get('edge_id') not in edge_ids or type(event.get('seq')) is not int or event['seq'] <= last: fail('invalid_events')
        last = event['seq']
        payload = event.get('values', {})
        if not isinstance(payload, dict) or len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > 4000: fail('invalid_events')
        events.append({'edge_id': event['edge_id'], 'seq': last, 'at': content.text(event.get('at'), 'at', 100), 'values': payload})
    snapshot = gameplay.snapshot(body.get('snapshot')) if body.get('snapshot') is not None else None
    saved = {'id': 'LP-' + uuid.uuid4().hex[:12], 'name': content.text(body.get('name'), 'name', 200),
             'entry': value['entry'], 'registry': value, 'selected': selected, 'events': events,
             'snapshot': snapshot, 'paused': body.get('paused') is True, 'captured_at': content.text(body.get('captured_at'), 'captured_at', 100),
             'created_at': content.timestamp(), 'fingerprint': fingerprint, 'variant_id': None, 'status': 'captured'}
    with content.database(root) as db: content.put(db, 'live_point', saved['id'], saved)
    return saved


def context(root, key):
    saved = point(root, key)
    value = saved['registry']
    target = next(t for t in value['targets'] if t['id'] == saved['selected'])
    ids = set(target['node_ids'])
    linked = [e for e in value['edges'] if e['source'] in ids or e['target'] in ids]
    nearby = ids | {e[k] for e in linked for k in ('source', 'target')}
    nodes = [n for n in value['nodes'] if n['id'] in nearby]
    refs = set(target['refs']) | {r for n in nodes + linked for r in n['refs']}
    records = [n for n in production.graph(root)['nodes'] if n['id'] in refs]
    return {'guide': 'guide/play-workspace.md', 'point_id': key, 'target': target, 'nodes': nodes, 'edges': linked,
            'events': [e for e in saved['events'] if e['edge_id'] in {r['id'] for r in linked}],
            'state': saved['snapshot'], 'paused': saved['paused'], 'captured_at': saved['captured_at'],
            'records': records, 'registry_revision': value['revision'],
            'changed_since_capture': creator.manifest(root) != saved['fingerprint']}


def branch(root, key):
    saved = point(root, key)
    if saved['status'] != 'captured' or saved['variant_id']: fail('branch_exists')
    if saved['snapshot'] is None: fail('no_snapshot')
    if creator.manifest(root) != saved['fingerprint']: fail('game_changed')
    variant = creator.variant_create(root, saved['name'], json.dumps({'point_id': key, 'target': saved['selected']}, ensure_ascii=False), saved['entry'])
    saved.update(variant_id=variant['id'], status='comparison')
    with content.database(root) as db: content.put(db, 'live_point', key, saved)
    return saved


def variant_context(root, key):
    saved = point(root, key)
    if saved['status'] != 'comparison': fail('branch_exists')
    with content.database(root) as db: variant = content.get(db, 'variant', saved['variant_id'])
    if variant['status'] != 'comparison' or creator.manifest(root) != saved['fingerprint']: fail('game_changed')
    return saved, variant


def select(root, key, choice, expected_files=None):
    saved, variant = variant_context(root, key)
    if choice not in ('original', 'alternative'): fail('selection')
    if choice == 'alternative':
        files = creator.game_files(project_path(root, variant['folder']), include_media=True)
        if expected_files != build_fingerprint({name: creator.file_hash(path) for name, path in files.items()}): fail('game_changed')
        # The registry belongs to the baseline; edits to it require explicit re-registration.
        other = project_path(root, variant['folder']) / REGISTRY
        if not other.is_file() or other.read_bytes() != project_path(root, REGISTRY).read_bytes(): fail('registry_changed')
        creator.variant_adopt(root, variant['id'])
    else:
        variant.update(status='not_selected', selected_at=content.timestamp())
        with content.database(root) as db: content.put(db, 'variant', variant['id'], variant)
    saved.update(status=choice, selection_quote=str(msg('live.keep_original' if choice == 'original' else 'live.adopt')), selected_at=content.timestamp())
    with content.database(root) as db: content.put(db, 'live_point', key, saved)
    return saved


def runtime(root):
    base = Path(__file__).resolve().parent
    source = base / 'live-runtime.js'
    if not source.is_file(): source = base / 'web/live-runtime.js'
    target = project_path(root, 'game-tools/live-runtime.js'); target.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(target, bundle_runtime(source.read_text(encoding='utf-8')))
    return {'path': 'game-tools/live-runtime.js', 'registry': REGISTRY}


def command(args):
    from decisions import input_text
    if args.command == 'register': return register(args.project_root, json.loads(input_text(args)), args.revision)
    if args.command == 'runtime': return runtime(args.project_root)
    if args.command == 'graph': return graph(args.project_root)
    if args.command == 'points': return {'items': points(args.project_root)}
    return point(args.project_root, args.id)
