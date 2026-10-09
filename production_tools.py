"""Evidence-backed relationships, annotated feedback and reusable game timelines."""
from message_catalog import text as _msg, bundle_runtime
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import uuid

from content_editor import database, entries, get, put, text, timestamp, digest, read
from decisions import find_project, project_path, atomic_text, decoded_record
from creator_tools import archive_path, file_hash, game_files
from asset_store import AssetStore


def annotations(value):
    if value is None: return None
    if not isinstance(value, dict): raise ValueError(_msg('py.production_tools.invalid.image.selection'))
    size, regions = value.get('size'), value.get('regions')
    if not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or n < 1 or n > 10000 for n in size):
        raise ValueError(_msg('py.production_tools.image.dimensions.are.required'))
    if not isinstance(regions, list) or not 1 <= len(regions) <= 12: raise ValueError(_msg('py.production_tools.select.image.regions'))
    result = []
    for region in regions:
        rect = region.get('rect')
        if not isinstance(rect, list) or len(rect) != 4 or any(type(n) not in (int, float) or not math.isfinite(n) for n in rect):
            raise ValueError(_msg('py.production_tools.invalid.region.coordinates'))
        x, y, w, h = rect
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.00001 or y + h > 1.00001: raise ValueError(_msg('py.production_tools.region.must.stay.inside.the.image'))
        result.append({'rect': rect, 'label': text(region.get('label'), _msg('py.production_tools.region.label'), 500)})
    return {'size': size, 'regions': result, 'coordinate_space': 'normalized_screenshot'}


def node_id(kind, *parts): return json.dumps([kind, *parts], ensure_ascii=False, separators=(',', ':'))


def graph(root):
    root, pid = find_project(root)
    nodes, edges, warnings = {}, [], []
    def node(kind, key, label, record, **extra):
        identity = node_id(kind, key)
        nodes[identity] = {'id': identity, 'kind': kind, 'label': str(label), 'record': record, **extra}
        return identity
    def edge(source, target, relation, evidence, **extra):
        edges.append({'source': source, 'target': target, 'relation': relation, 'evidence': evidence, **extra})
    with database(root) as db:
        definitions = entries(db, 'content'); stories = entries(db, 'story'); manual = entries(db, 'relation'); timelines = entries(db, 'timeline')
        designs = [(kind, r) for kind in ('integration', 'content_plan', 'experiment') for r in entries(db, kind)]
    for kind, record in designs: node(kind, record['id'], record['name'], record)
    datasets = {}
    for definition in definitions:
        try: rows, checksum = read(root, definition)
        except (ValueError, OSError) as error:
            warnings.append(f'{definition["path"]}: {error}'); continue
        datasets[definition['id']] = (definition, rows, checksum)
        for row in rows:
            identity = row.get(definition['id_field'])
            key = node_id('content', definition['id'], identity)
            nodes[key] = {'id': key, 'kind': 'content', 'label': f'{definition["name"]} / {identity} · {row.get("name", row.get("title", ""))}',
                          'record': row, 'path': definition['path'], 'dataset': definition['id'], 'row_id': identity, 'digest': checksum}
    for definition, rows, checksum in datasets.values():
        for row in rows:
            source = node_id('content', definition['id'], row[definition['id_field']])
            for field in definition['fields']:
                if field['type'] == 'reference' and row.get(field['key']):
                    edge(source, node_id('content', field['dataset'], row[field['key']]), 'data_reference',
                         {'path': definition['path'], 'field': field['key'], 'value': row[field['key']], 'sha256': checksum})
    for story in stories: node('story', story['id'], story['title'], story)
    for story in stories:
        for target in story.get('links', []): edge(node_id('story', story['id']), node_id('story', target), 'story_link', {'record_id': story['id'], 'revision': story['revision'], 'field': 'links'})
    path = project_path(root, 'data/decisions.sqlite')
    records = {}
    if path.exists():
        with closing(sqlite3.connect(path)) as db:
            db.row_factory = sqlite3.Row
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, kind in (('user_decisions', 'user'), ('work_decisions', 'work'), ('user_references', 'reference')):
                if table not in tables: continue
                for row in db.execute(f'SELECT * FROM {table} WHERE project_id=?', (pid,)):
                    record = decoded_record(row); records[record['id']] = (kind, record)
                    node(kind, record['id'], f'{record["id"]} · {record.get("topic", record.get("title_or_url", record.get("decision", "")))}', record)
    for identity, (kind, record) in records.items():
        for field in ('reference_ids', 'user_decision_ids'):
            for linked in record.get(field, []) if isinstance(record.get(field), list) else []:
                if linked in records: edge(node_id(kind, identity), node_id(records[linked][0], linked), field, {'record_id': identity, 'field': field})
    for asset in AssetStore(root).list():
        source = node('asset', asset['id'], f'{asset["name"]} · {asset["id"]}', asset)
        for relative in asset['files']:
            target = node('file', relative, relative, {'path': relative}, path=relative)
            edge(source, target, 'asset_file', {'record_id': asset['id'], 'revision': asset['revision'], 'field': 'files'})
        for field in ('decision_ids', 'reference_ids'):
            for linked in asset.get(field, []):
                if linked in records: edge(source, node_id(records[linked][0], linked), field, {'record_id': asset['id'], 'revision': asset['revision'], 'field': field})
    for timeline in timelines:
        source = node('timeline', timeline['id'], timeline['name'], timeline)
        for step in timeline['steps']:
            for key, kind in (('asset_id', 'asset'), ('story_id', 'story')):
                if step.get(key): edge(source, node_id(kind, step[key]), 'timeline_' + key, {'record_id': timeline['id'], 'step_id': step['id'], 'field': key})
    for record in manual:
        evidence = dict(record['evidence'])
        path = archive_path(root, evidence['path'])
        stale = not path.is_file() or file_hash(path) != evidence['sha256']
        edge(record['source'], record['target'], record['relation'], evidence, id=record['id'], stale=stale, user_note=record.get('user_note', ''), interpretation=record.get('interpretation', ''))
    for item in edges: item['missing'] = item['source'] not in nodes or item['target'] not in nodes
    result = {'nodes': list(nodes.values()), 'edges': edges, 'warnings': warnings}
    result['fingerprint'] = digest(json.dumps(result, ensure_ascii=False, sort_keys=True).encode())
    return result


def related(root, key):
    result = graph(root)
    selected = next((n for n in result['nodes'] if n['id'] == key), None)
    if not selected: raise ValueError(_msg('py.production_tools.selected.item.no.longer.exists'))
    links = [e for e in result['edges'] if key in (e['source'], e['target'])]
    ids = {i for e in links for i in (e['source'], e['target'])} | {key}
    # Code occurrences are explicitly separate from recorded relationships.
    terms = [str(selected.get('row_id', '')), str(selected['record'].get('id', ''))]
    if selected.get('path'): terms.append(selected['path'])
    terms = [s for s in terms if len(s) >= 3]
    occurrences, scanned, truncated = [], 0, False
    for relative, path in game_files(root).items():
        if path.suffix.lower() not in ('.js', '.ts', '.json', '.html', '.css', '.cs', '.gd', '.lua', '.csv') or path.stat().st_size > 512000: continue
        if scanned >= 200: truncated = True; break
        scanned += 1
        source = path.read_text(encoding='utf-8-sig', errors='replace')
        for line, value in enumerate(source.splitlines(), 1):
            if any(term in value for term in terms):
                occurrences.append({'path': relative, 'line': line, 'text': value[:500], 'sha256': digest(path.read_bytes())})
                if len(occurrences) >= 40: truncated = True; break
        if len(occurrences) >= 40: break
    return {'selected': selected, 'nodes': [n for n in result['nodes'] if n['id'] in ids], 'edges': links,
            'occurrences': occurrences, 'coverage': {'files': scanned, 'truncated': truncated}, 'warnings': result['warnings'], 'fingerprint': result['fingerprint']}


def relation_save(root, value):
    user_note = value.get('user_note', '')
    if not isinstance(user_note, str) or len(user_note) > 10000: raise ValueError(_msg('py.production_tools.user.note.must.be.at.most.characters'))
    current = graph(root); ids = {n['id'] for n in current['nodes']}
    if value.get('source') not in ids or value.get('target') not in ids: raise ValueError(_msg('py.production_tools.choose.existing.relationship.endpoints'))
    evidence = value.get('evidence') or {}; path = archive_path(root, text(evidence.get('path'), _msg('py.production_tools.evidence.path'), 500))
    if path not in game_files(root).values() or path.stat().st_size > 512000: raise ValueError(_msg('py.production_tools.choose.a.game.source.file.up.to.kb'))
    quote = text(evidence.get('quote'), _msg('py.production_tools.evidence.quote'), 4000); line = evidence.get('line')
    source = path.read_text(encoding='utf-8-sig')
    if type(line) is not int or line < 1 or not source.splitlines()[line - 1:]: raise ValueError(_msg('py.production_tools.invalid.evidence.line'))
    if not '\n'.join(source.splitlines()[line - 1:]).startswith(quote): raise ValueError(_msg('py.production_tools.evidence.does.not.match.the.current.file'))
    record = {'id': 'REL-' + uuid.uuid4().hex[:12], 'source': value['source'], 'target': value['target'],
              'relation': text(value.get('relation'), 'relationship', 200), 'evidence': {'path': path.relative_to(root).as_posix(), 'line': line, 'quote': quote, 'sha256': file_hash(path)},
              'user_note': user_note, 'interpretation': text(value.get('interpretation'), 'interpretation'), 'created_at': timestamp()}
    with database(root) as db: put(db, 'relation', record['id'], record)
    return record


KINDS = ('dialogue', 'move', 'sound', 'image', 'transition', 'wait')


def timeline_targets(root, entry):
    from html.parser import HTMLParser
    path = archive_path(root, entry or 'index.html')
    if not path.is_file() or path.suffix.lower() not in ('.html', '.htm') or path.stat().st_size > 2000000: return []
    class Targets(HTMLParser):
        def __init__(self): super().__init__(); self.items = []
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            identity = values.get('data-timeline-target')
            if identity: self.items.append({'id': identity, 'label': values.get('data-timeline-label') or values.get('aria-label') or identity})
    parser = Targets(); parser.feed(path.read_text(encoding='utf-8-sig')); return parser.items


def number(value, name, minimum=0, maximum=600):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(_msg('py.production_tools.number.in.required' ,name,minimum,maximum))
    return value


def timeline_save(root, value, revision=None):
    name = text(value.get('name'), _msg('py.production_tools.timeline.name'), 200)
    steps = value.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100: raise ValueError(_msg('py.production_tools.a.timeline.needs.steps'))
    result, ids = [], set()
    for step in steps:
        if step.get('kind') not in KINDS: raise ValueError(_msg('py.production_tools.unknown.timeline.action'))
        item = {'id': step.get('id') or 'STEP-' + uuid.uuid4().hex[:10], 'kind': step['kind'],
                'delay': number(step.get('delay', 0), 'delay'), 'duration': number(step.get('duration', 1), 'duration', .05)}
        if not isinstance(item['id'], str) or item['id'] in ids: raise ValueError(_msg('py.production_tools.step.ids.must.be.unique'))
        ids.add(item['id'])
        if item['kind'] == 'move':
            item.update(target=text(step.get('target'), 'target', 500), x=number(step.get('x', 0), 'x', -100000, 100000), y=number(step.get('y', 0), 'y', -100000, 100000))
        if item['kind'] in ('sound', 'image'):
            asset = AssetStore(root).get(step.get('asset_id'))
            if asset['kind'] != ('sound' if item['kind'] == 'sound' else 'image') or asset['status'] == 'retired': raise ValueError(_msg('py.production_tools.select.a.matching.non.retired.asset'))
            asset_path = step.get('asset_path')
            allowed = ('.wav', '.mp3', '.ogg', '.m4a', '.flac') if item['kind'] == 'sound' else ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif')
            if asset_path not in asset['files'] or archive_path(root, asset_path).suffix.lower() not in allowed or not archive_path(root, asset_path).is_file(): raise ValueError(_msg('py.production_tools.select.an.existing.media.file.from.that.asset'))
            item.update(asset_id=asset['id'], asset_path=asset_path, asset_revision=asset['revision'])
        if item['kind'] == 'dialogue':
            with database(root) as db: story = get(db, 'story', step.get('story_id'))
            if story['status'] != 'confirmed': raise ValueError(_msg('py.production_tools.choose.a.confirmed.story.record'))
            item.update(story_id=story['id'], story_revision=story['revision'])
            excerpt = step.get('excerpt', '')
            if not isinstance(excerpt, str) or (excerpt and excerpt not in story['body']): raise ValueError(_msg('py.production_tools.dialogue.must.be.an.exact.excerpt.of.the'))
            item['excerpt'] = excerpt
        if item['kind'] == 'transition':
            import re
            color = step.get('color', '#000000')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color): raise ValueError(_msg('py.production_tools.choose.a.six.digit.transition.color'))
            item['color'] = color
        result.append(item)
    if sum(s['delay'] + s['duration'] for s in result) > 3600: raise ValueError(_msg('py.production_tools.a.timeline.may.last.at.most.one.hour'))
    with database(root) as db:
        old = get(db, 'timeline', value['id']) if value.get('id') else None
        if old and old['revision'] != revision: raise ValueError(_msg('py.production_tools.timeline.changed.reload.before.saving'))
        record = {'id': old['id'] if old else 'TL-' + uuid.uuid4().hex[:12], 'name': name, 'steps': result,
                  'revision': uuid.uuid4().hex, 'updated_at': timestamp(), 'published_revision': old.get('published_revision') if old else None}
        if old and old.get('path'): record['path'] = old['path']
        put(db, 'timeline', record['id'], record); put(db, 'timeline_history', record['revision'], record)
    return record


def timeline_resolve(root, key, revision):
    with database(root) as db: record = get(db, 'timeline', key)
    if record['revision'] != revision: raise ValueError(_msg('py.production_tools.timeline.changed.reload.before.using.it'))
    result = {**record, 'steps': [dict(s) for s in record['steps']]}
    for step in result['steps']:
        if step.get('asset_id'):
            asset = AssetStore(root).get(step['asset_id'])
            if asset['revision'] != step['asset_revision'] or step['asset_path'] not in asset['files'] or not archive_path(root, step['asset_path']).is_file(): raise ValueError(_msg('py.production_tools.a.timeline.asset.changed.review.and.save.this'))
            step['src'] = step['asset_path']
        if step.get('story_id'):
            with database(root) as db: story = get(db, 'story', step['story_id'])
            if story['revision'] != step['story_revision'] or story['status'] != 'confirmed': raise ValueError(_msg('py.production_tools.timeline.dialogue.changed.review.and.save.this.timeline'))
            step['text'] = step.get('excerpt') or story['body']
    return result


def timeline_publish(root, key, revision):
    root, _ = find_project(root)
    resolved = timeline_resolve(root, key, revision)
    runtime = Path(__file__).resolve().parent / 'timeline-player.js'
    if not runtime.is_file(): runtime = Path(__file__).resolve().parent / 'web/timeline-player.js'
    runtime_text = bundle_runtime(runtime.read_text(encoding='utf-8'))
    runtime_path = project_path(root, 'game-tools/timeline-player.js')
    if runtime_path.exists() and runtime_path.read_text(encoding='utf-8') != runtime_text:
        backup = project_path(root, 'data/timeline-history/runtime-' + uuid.uuid4().hex + '.js')
        backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(runtime_path.read_bytes())
    relative = 'content/timelines/' + key + '.json'; dest = project_path(root, relative)
    if dest.exists():
        backup = project_path(root, 'data/timeline-history/' + key + '-' + uuid.uuid4().hex + '.json')
        backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(dest.read_bytes())
    # Paths are relative to the game root, not the JSON file's directory.
    payload = {'id': key, 'name': resolved['name'], 'revision': revision, 'steps': resolved['steps']}
    runtime_path.parent.mkdir(parents=True, exist_ok=True); dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(runtime_path, runtime_text); atomic_text(dest, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    with database(root) as db:
        record = get(db, 'timeline', key)
        if record['revision'] != revision: raise ValueError(_msg('py.production_tools.timeline.changed.while.publishing.publish.the.current.version'))
        record.update(path=relative, published_revision=revision)
        put(db, 'timeline', key, record)
    return record


def published_media(root):
    if not project_path(root, 'data/creator.sqlite').is_file(): return []
    with database(root) as db: timelines = entries(db, 'timeline')
    paths = []
    for record in timelines:
        if not record.get('path'): continue
        path = archive_path(root, record['path'])
        if not path.is_file(): continue
        payload = json.loads(path.read_text(encoding='utf-8'))
        paths.extend(s['src'] for s in payload.get('steps', []) if s.get('kind') in ('image', 'sound') and isinstance(s.get('src'), str))
    return paths


def command(args):
    from decisions import input_text
    if args.store == 'relation':
        return relation_save(args.project_root, json.loads(input_text(args))) if args.command == 'add' else related(args.project_root, args.id) if args.command == 'show' else graph(args.project_root)
    if args.command == 'save': return timeline_save(args.project_root, json.loads(input_text(args)), args.revision)
    if args.command == 'publish': return timeline_publish(args.project_root, args.id, args.revision)
    with database(args.project_root) as db: return get(db, 'timeline', args.id) if args.command == 'show' else {'items': entries(db, 'timeline')}
