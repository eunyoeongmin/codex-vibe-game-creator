"""Sound direction and evidence-bound balance studies for project games."""
from message_catalog import text as _msg, bundle_runtime
import json
import math
import re
import uuid
from pathlib import Path

import content_editor as content
import creator_tools as creator
from gameplay_tools import save_record, get_record, object_value
from asset_store import AssetStore
from decisions import project_path, atomic_text

KINDS = ('soundscape', 'balance', 'balance_run')
ROLES = ('music', 'effect', 'ambient', 'voice')


def number(value, label, minimum, maximum, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum or (integer and type(value) is not int):
        raise ValueError(f'{label}: {minimum}–{maximum}' + (' (integer)' if integer else ''))
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}', value): raise ValueError(_msg('py.studio_tools.use.a.stable.letter.based.key.up.to'))
    return value


def sound_save(root, value, revision=None):
    object_value(value)
    cues = value.get('cues')
    if not isinstance(cues, list) or not 1 <= len(cues) <= 100: raise ValueError(_msg('py.studio_tools.use.sound.cues'))
    result, seen = [], set()
    for cue in cues:
        object_value(cue); key = identifier(cue.get('key'))
        if key in seen: raise ValueError(_msg('py.studio_tools.sound.cue.keys.must.be.unique'))
        seen.add(key)
        role = cue.get('role')
        if role not in ROLES: raise ValueError(_msg('py.studio_tools.choose.music.effect.ambient.or.voice'))
        asset = AssetStore(root).get(cue.get('asset_id'))
        path = cue.get('path')
        if asset['kind'] != 'sound' or asset['status'] == 'retired' or path not in asset['files']: raise ValueError(_msg('py.studio_tools.choose.an.active.registered.sound.asset'))
        file = AssetStore(root).file(path)
        if not file.is_file() or file.suffix.lower() not in ('.mp3', '.wav', '.ogg', '.m4a', '.flac'): raise ValueError(_msg('py.studio_tools.choose.an.existing.audio.file'))
        loop = cue.get('loop', False)
        if type(loop) is not bool: raise ValueError(_msg('py.studio_tools.loop.must.be.boolean'))
        start = number(cue.get('loop_start', 0), 'loop_start', 0, 86400)
        end = number(cue.get('loop_end', 0), 'loop_end', 0, 86400)
        if end and end <= start: raise ValueError(_msg('py.studio_tools.loop.end.must.be.after.its.start.zero'))
        result.append({'key': key, 'name': content.text(cue.get('name'), 'name', 200),
            'event': content.text(cue.get('event'), 'event'), 'role': role, 'asset_id': asset['id'], 'asset_revision': asset['revision'],
            'path': path, 'sha256': creator.file_hash(file), 'gain': number(cue.get('gain', 1), 'gain', 0, 1),
            'loop': loop, 'loop_start': start, 'loop_end': end,
            'fade_in': number(cue.get('fade_in', 0), 'fade_in', 0, 30), 'fade_out': number(cue.get('fade_out', .2), 'fade_out', 0, 30),
            'priority': number(cue.get('priority', 0), 'priority', 0, 100, True),
            'max_voices': number(cue.get('max_voices', 1), 'max_voices', 1, 16, True)})
    buses = value.get('buses', {})
    volumes = {role: number(buses.get(role, 1), role, 0, 1) for role in ROLES}
    old = get_record(root, 'soundscape', value['id'], revision) if value.get('id') else {}
    return save_record(root, 'soundscape', {'id': value.get('id'), 'name': content.text(value.get('name'), 'name', 200),
        'cues': result, 'buses': volumes, 'duck_music': number(value.get('duck_music', .3), 'duck_music', 0, 1),
        'published_revision': old.get('published_revision'), 'path': old.get('path')}, revision)


def sound_resolve(root, key, revision):
    record = get_record(root, 'soundscape', key, revision)
    for cue in record['cues']:
        asset = AssetStore(root).get(cue['asset_id']); file = AssetStore(root).file(cue['path'])
        if (asset['revision'] != cue['asset_revision'] or asset['status'] == 'retired' or cue['path'] not in asset['files']
                or not file.is_file() or creator.file_hash(file) != cue['sha256']):
            raise ValueError(_msg('py.studio_tools.sound.asset.changed.review.and.save.this.soundscape'))
    return record


def publish_file(root, relative, data):
    target = project_path(root, relative); target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = project_path(root, 'data/studio-history/' + uuid.uuid4().hex + target.suffix)
        backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(target.read_bytes())
    atomic_text(target, data)


def runtime_publish(root):
    for name in ('sound-runtime.js', 'balance-runtime.js'):
        source = Path(__file__).resolve().parent / name
        if not source.is_file(): source = Path(__file__).resolve().parent / 'web' / name
        publish_file(root, 'game-tools/' + name, bundle_runtime(source.read_text(encoding='utf-8')))
    return {'paths': ['game-tools/sound-runtime.js', 'game-tools/balance-runtime.js']}


def sound_publish(root, key, revision):
    record = sound_resolve(root, key, revision)
    runtime_publish(root)
    relative = 'content/soundscapes/' + key + '.json'
    publish_file(root, relative, json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    with content.database(root) as db:
        latest = content.get(db, 'soundscape', key)
        if latest['revision'] != revision: raise ValueError(_msg('py.studio_tools.soundscape.changed.while.publishing'))
        latest.update(path=relative, published_revision=revision)
        content.put(db, 'soundscape', key, latest)
    return latest


def published_media(root):
    if not project_path(root, 'data/creator.sqlite').is_file(): return []
    with content.database(root) as db: records = content.entries(db, 'soundscape')
    paths = []
    for record in records:
        if record.get('path'):
            path = creator.archive_path(root, record['path'])
            if path.is_file(): paths.extend(cue['path'] for cue in json.loads(path.read_text(encoding='utf-8'))['cues'])
    return paths


def balance_save(root, value, revision=None):
    object_value(value)
    entry = content.text(value.get('entry'), 'entry', 500)
    if entry not in creator.game_files(root) or Path(entry).suffix.lower() not in ('.html', '.htm'): raise ValueError(_msg('py.studio_tools.choose.a.game.html.entry'))
    parameters, outputs = value.get('parameters'), value.get('outputs')
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= 20 or not isinstance(outputs, list) or not 1 <= len(outputs) <= 20: raise ValueError(_msg('py.studio_tools.use.inputs.and.outputs'))
    seen, params, metrics = set(), [], []
    for param in parameters:
        key = identifier(param.get('key'))
        if key in seen: raise ValueError(_msg('py.studio_tools.input.keys.must.be.unique'))
        seen.add(key)
        lo, hi = number(param.get('min'), 'min', -1e12, 1e12), number(param.get('max'), 'max', -1e12, 1e12)
        if lo > hi: raise ValueError(_msg('py.studio_tools.input.min.exceeds.max'))
        p = {'key': key, 'label': content.text(param.get('label'), 'label', 200), 'min': lo, 'max': hi,
             'default': number(param.get('default'), 'default', lo, hi), 'step': number(param.get('step', 1), 'step', 1e-9, 1e12)}
        if param.get('binding'):
            binding = param['binding']; info = content.show(root, binding.get('dataset'))
            field = next((f for f in info['definition']['fields'] if f['key'] == binding.get('field') and f['type'] in ('number','integer')), None)
            row = next((r for r in info['rows'] if r[info['definition']['id_field']] == binding.get('row_id')), None)
            if field is None or row is None: raise ValueError(_msg('py.studio_tools.choose.an.existing.numeric.content.field'))
            p.update(binding={k: binding[k] for k in ('dataset','row_id','field')}, dataset_digest=info['digest'])
            if p['default'] != row[field['key']]: raise ValueError(_msg('py.studio_tools.bound.input.default.must.match.the.current.content'))
        params.append(p)
    seen.clear()
    for metric in outputs:
        key = identifier(metric.get('key'))
        if key in seen: raise ValueError(_msg('py.studio_tools.output.keys.must.be.unique'))
        seen.add(key)
        metrics.append({'key': key, 'label': content.text(metric.get('label'), 'label', 200), 'unit': str(metric.get('unit', ''))[:80]})
    evidence = value.get('evidence')
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20: raise ValueError(_msg('py.studio_tools.quote.the.actual.game.calculation.code'))
    proof, files = [], creator.game_files(root)
    for e in evidence:
        file = files.get(e.get('path')); quote = content.text(e.get('quote'), 'quote', 10000)
        if file is None or file.stat().st_size > 2000000 or file.suffix.lower() not in ('.js','.mjs','.ts') or quote not in file.read_text(encoding='utf-8-sig'): raise ValueError(_msg('py.studio_tools.calculation.evidence.must.quote.current.game.code'))
        proof.append({'path':e['path'],'quote':quote,'sha256':creator.file_hash(file)})
    return save_record(root, 'balance', {'id': value.get('id'), 'name': content.text(value.get('name'), 'name', 200),
        'entry': entry, 'adapter': identifier(value.get('adapter')), 'adapter_version': number(value.get('adapter_version'), 'adapter_version', 1, 1000000, True),
        'parameters': params, 'outputs': metrics, 'evidence': proof}, revision)


def balance_context(root, key, revision):
    record = get_record(root, 'balance', key, revision)
    for evidence in record['evidence']:
        path = creator.archive_path(root, evidence['path'])
        if not path.is_file() or creator.file_hash(path) != evidence['sha256']: raise ValueError(_msg('py.studio_tools.calculation.code.changed.reconnect.the.balance.definition'))
    for param in record['parameters']:
        if param.get('binding') and content.show(root,param['binding']['dataset'])['digest'] != param['dataset_digest']:
            raise ValueError(_msg('py.studio_tools.bound.game.data.changed.reconnect.the.balance.definition'))
    return {'record': record, 'fingerprint': content.digest(json.dumps(creator.manifest(root),sort_keys=True).encode())}


def balance_result(root, value):
    object_value(value)
    context = balance_context(root, value.get('id'), value.get('revision')); record = context['record']
    if value.get('fingerprint') != context['fingerprint']: raise ValueError(_msg('py.studio_tools.game.files.changed.during.comparison.run.it.again'))
    runs = value.get('scenarios')
    if not isinstance(runs,list) or not 1 <= len(runs) <= 20: raise ValueError(_msg('runtime.balance.compare.scenarios'))
    goals = value.get('goals', {})
    if not isinstance(goals, dict) or set(goals) - {m['key'] for m in record['outputs']}: raise ValueError(_msg('py.studio_tools.unknown.goal.metric'))
    for goal in goals.values():
        lo=number(goal.get('min'),_msg('py.studio_tools.goal.min'),-1e15,1e15);hi=number(goal.get('max'),_msg('py.studio_tools.goal.max'),-1e15,1e15)
        if lo > hi: raise ValueError(_msg('py.studio_tools.goal.min.exceeds.max'))
    result=[]
    for run in runs:
        inputs,outputs=run.get('inputs'),run.get('outputs')
        if not isinstance(inputs,dict) or set(inputs)!={p['key'] for p in record['parameters']} or not isinstance(outputs,dict) or set(outputs)!={m['key'] for m in record['outputs']}:
            raise ValueError(_msg('py.studio_tools.scenario.inputs.and.outputs.must.match.the.registered'))
        for p in record['parameters']:number(inputs[p['key']],p['key'],p['min'],p['max'])
        for key,v in outputs.items():number(v,key,-1e15,1e15)
        checks={key:'below' if outputs[key]<g['min'] else 'above' if outputs[key]>g['max'] else 'within' for key,g in goals.items()}
        result.append({'name':content.text(run.get('name'),'name',200),'inputs':inputs,'outputs':outputs,'checks':checks})
    return save_record(root,'balance_run',{'name':content.text(value.get('name'),'name',200),'balance_id':record['id'],
        'balance_revision':record['revision'],'adapter':record['adapter'],'adapter_version':record['adapter_version'],
        'fingerprint':context['fingerprint'],'goals':goals,'scenarios':result,'evidence':record['evidence'],
        'parameters':record['parameters'],'output_metrics':record['outputs'],'source':'game_adapter'})


def command(args):
    from decisions import input_text
    if args.command == 'runtime': return runtime_publish(args.project_root)
    if args.command == 'save':
        fn = sound_save if args.store == 'soundscape' else balance_save
        return fn(args.project_root,json.loads(input_text(args)),args.revision)
    if args.command == 'publish': return sound_publish(args.project_root,args.id,args.revision)
    with content.database(args.project_root) as db:
        return content.get(db,args.store,args.id) if args.command=='show' else {'items':content.entries(db,args.store)}
