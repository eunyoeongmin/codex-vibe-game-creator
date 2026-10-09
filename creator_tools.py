"""User-controlled checkpoints, alternatives, story records, feedback and exports."""
from message_catalog import text as _msg
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid
import zipfile
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

from decisions import find_project, project_path
from content_editor import database, entries, get, put, text, timestamp, digest

EXCLUDED = {'data', 'guide', 'agents', 'catalogs', 'genres', 'references', 'uploads', 'feedback', 'discarded', 'variants',
            'node_modules', '__pycache__', 'venv'}
PRIVATE = {'agents.md', 'agents.override.md', 'spec.md', 'state.md', 'architecture.md', 'milestones.json'}


def game_files(root, *, include_media=False):
    root = Path(root).resolve()
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        excluded = EXCLUDED - {'references', 'uploads'} if include_media else EXCLUDED
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d.lower() not in excluded
                         and (Path(folder) / d).resolve().is_relative_to(root) and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            if name.startswith('.') or name.lower() in PRIVATE or path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            result[path.relative_to(root).as_posix()] = path
    if (root / '.project').is_file():
        from asset_store import AssetStore
        from production_tools import published_media
        from studio_tools import published_media as sound_media
        referenced = list(published_media(root)) + sound_media(root)
        for asset in AssetStore(root).list():
            if asset['usage_state'] != 'in_use': continue
            referenced.extend(asset['files'])
        for relative in referenced:
            path = archive_path(root, relative)
            parts = path.relative_to(root).parts
            if (path.is_file() and not path.is_symlink() and not any(p.startswith('.') for p in parts)
                    and parts[0].lower() not in EXCLUDED - {'references', 'uploads'} and path.name.lower() not in PRIVATE):
                result[path.relative_to(root).as_posix()] = path
    return result


def checkpoint_files(root):
    files = game_files(root)
    for folder in ('references', 'uploads'):
        base = project_path(root, folder)
        if base.is_dir():
            for name, path in game_files(base).items(): files[folder + '/' + name] = path
    for name in ('SPEC.md', 'STATE.md', 'ARCHITECTURE.md', 'milestones.json'):
        path = project_path(root, name)
        if path.is_file(): files[name] = path
    return files


def manifest(root):
    return {name: file_hash(path) for name, path in game_files(root).items()}


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def archive_path(root, name):
    if name.startswith('/') or ':' in name or any(p in ('', '.', '..') for p in name.replace('\\', '/').split('/')):
        raise ValueError(_msg('py.creator_tools.invalid.archive.path'))
    return project_path(root, name)


def checkpoint(root, name):
    root, pid = find_project(root)
    record = {'id': 'CP-' + uuid.uuid4().hex[:12], 'name': text(name, 'name', 200), 'created_at': timestamp()}
    destination = project_path(root, 'data/checkpoints/' + record['id'] + '.zip')
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = checkpoint_files(root)
    with database(root) as db:
        state = {kind: entries(db, kind) for kind in ('content', 'story', 'timeline', 'relation', 'localization', 'experiment', 'integration', 'content_plan', 'soundscape', 'balance', 'live_registry')}
    hashes = {}
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            raw = path.read_bytes(); hashes[name] = digest(raw)
            archive.writestr('files/' + name, raw)
        db_path = project_path(root, 'data/decisions.sqlite')
        if db_path.exists():
            temporary = destination.with_suffix('.sqlite')
            try:
                with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(temporary)) as copy:
                    source.backup(copy)
                raw = temporary.read_bytes(); hashes['data/decisions.sqlite'] = digest(raw)
                archive.writestr('files/data/decisions.sqlite', raw)
            finally:
                if temporary.exists(): temporary.unlink()
        archive.writestr('manifest.json', json.dumps({'project_id': pid, 'files': hashes, 'state': state}, ensure_ascii=False))
    record.update(path=destination.relative_to(root).as_posix(), size=destination.stat().st_size, sha256=file_hash(destination))
    with database(root) as db: put(db, 'checkpoint', record['id'], record)
    return record


def load_checkpoint(root, record):
    root, pid = find_project(root)
    path = project_path(root, record['path'])
    if file_hash(path) != record['sha256']:
        raise ValueError(_msg('py.creator_tools.checkpoint.archive.changed.restore.refused'))
    with zipfile.ZipFile(path) as archive:
        data = json.loads(archive.read('manifest.json'))
        if data['project_id'] != pid:
            raise ValueError(_msg('py.creator_tools.checkpoint.belongs.to.another.project'))
        for name, expected in data['files'].items():
            archive_path(root, name)
            if digest(archive.read('files/' + name)) != expected:
                raise ValueError(_msg('py.creator_tools.checkpoint.checksum.mismatch'))
        return data


def restore(root, key):
    root, _ = find_project(root)
    with database(root) as db: record = get(db, 'checkpoint', key)
    data = load_checkpoint(root, record)
    backup = checkpoint(root, _msg('py.creator_tools.before.restore') + record['name'])
    parked = project_path(root, 'discarded/restore-' + uuid.uuid4().hex[:12])
    current = checkpoint_files(root)
    # Never delete the current game. Preserve its files in an explicit discarded folder.
    for name, path in current.items():
        dest = archive_path(parked, name); dest.parent.mkdir(parents=True, exist_ok=True)
        path.rename(dest)
    with zipfile.ZipFile(project_path(root, record['path'])) as archive:
        for name in data['files']:
            dest = archive_path(root, name); dest.parent.mkdir(parents=True, exist_ok=True)
            if name == 'data/decisions.sqlite':
                temporary = project_path(root, 'data/restore-' + uuid.uuid4().hex + '.sqlite')
                temporary.write_bytes(archive.read('files/' + name))
                try:
                    with closing(sqlite3.connect(temporary)) as source, closing(sqlite3.connect(dest)) as existing:
                        source.backup(existing)
                finally: temporary.unlink()
            else:
                dest.write_bytes(archive.read('files/' + name))
    with database(root) as db:
        for kind in ('content', 'story', 'timeline', 'relation', 'localization', 'experiment', 'integration', 'content_plan', 'soundscape', 'balance', 'live_registry'):
            db.execute('DELETE FROM entries WHERE kind=?', (kind,))
            for entry in data['state'].get(kind, []): put(db, kind, entry['id'], entry)
        put(db, 'control', 'restored', {'id': key, 'backup': backup['id'], 'created_at': timestamp(),
                                      'notice': _msg('py.creator_tools.game.files.and.decisions.were.restored.read.current')})
    return {'restored': key, 'backup': backup['id'], 'preserved_files': parked.relative_to(root).as_posix()}


def variant_create(root, name, hypothesis, entry):
    root, _ = find_project(root)
    files = game_files(root)
    if entry not in files or not entry.lower().endswith(('.html', '.htm')):
        raise ValueError(_msg('py.creator_tools.select.an.existing.html.entry.point'))
    record = {'id': 'V-' + uuid.uuid4().hex[:12], 'name': text(name, 'name', 200),
              'hypothesis': text(hypothesis, 'hypothesis'), 'entry': entry, 'status': 'comparison', 'created_at': timestamp()}
    folder = project_path(root, 'variants/' + record['id']); folder.mkdir(parents=True)
    hashes = {}
    for name, source in files.items():
        dest = archive_path(folder, name); dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest); hashes[name] = file_hash(dest)
    record.update(folder=folder.relative_to(root).as_posix(), baseline=hashes)
    with database(root) as db: put(db, 'variant', record['id'], record)
    return record


def variant_adopt(root, key):
    root, _ = find_project(root)
    with database(root) as db: record = get(db, 'variant', key)
    if record['status'] != 'comparison': raise ValueError(_msg('py.creator_api.this.alternative.was.already.selected'))
    if manifest(root) != record['baseline']:
        raise ValueError(_msg('py.creator_tools.the.main.game.changed.after.this.alternative.was'))
    folder = project_path(root, record['folder'])
    variant_files = game_files(folder, include_media=True)
    if record['entry'] not in variant_files: raise ValueError(_msg('py.creator_tools.alternative.entry.point.is.missing'))
    backup = checkpoint(root, _msg('py.creator_tools.before.selecting') + record['name'])
    parked = project_path(root, 'discarded/variant-' + key)
    if parked.exists(): raise ValueError(_msg('py.creator_tools.selection.backup.folder.already.exists'))
    for name, source in game_files(root).items():
        dest = archive_path(parked, name); dest.parent.mkdir(parents=True, exist_ok=True); source.rename(dest)
    for name, source in variant_files.items():
        dest = archive_path(root, name); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, dest)
    record.update(status='selected', selected_at=timestamp(), backup=backup['id'])
    with database(root) as db:
        put(db, 'variant', key, record)
        put(db, 'control', 'restored', {'id': key, 'backup': backup['id'], 'created_at': timestamp(),
                                      'notice': _msg('py.creator_tools.the.user.selected.this.alternative.current.game.files')})
    return record


def story_save(root, value, revision=None, *, actor='user'):
    if not isinstance(value, dict): raise ValueError(_msg('py.creator_tools.a.story.record.object.is.required'))
    if value.get('kind') not in ('character', 'event', 'branch', 'world'):
        raise ValueError(_msg('py.creator_tools.choose.character.event.branch.or.world'))
    status = value.get('status', 'proposed')
    if status not in ('proposed', 'confirmed') or (actor != 'user' and status != 'proposed'):
        raise ValueError(_msg('py.creator_tools.only.the.user.can.confirm.a.story.record'))
    record = {'id': value.get('id') or 'S-' + uuid.uuid4().hex[:12], 'kind': value['kind'], 'status': status,
              'title': text(value.get('title'), 'title', 200), 'body': text(value.get('body'), 'body', 20000),
              'condition': str(value.get('condition', ''))[:4000], 'game_effect': str(value.get('game_effect', ''))[:4000],
              'links': value.get('links', []), 'revision': uuid.uuid4().hex, 'updated_at': timestamp(), 'actor': actor}
    if not isinstance(record['links'], list) or any(not isinstance(link, str) for link in record['links']):
        raise ValueError(_msg('py.creator_tools.story.links.must.be.a.list.of.record'))
    with database(root) as db:
        previous = next((r for r in entries(db, 'story') if r['id'] == record['id']), None)
        if previous and previous['revision'] != revision: raise ValueError(_msg('py.creator_tools.story.record.changed.reload.before.saving'))
        if not previous and value.get('id'): raise ValueError(_msg('py.creator_tools.unknown.story.record'))
        for key in record['links']: get(db, 'story', key)
        put(db, 'story', record['id'], record)
        put(db, 'story_history', record['revision'], {**record, 'previous_revision': previous['revision'] if previous else None})
    return record


def feedback_save(root, value):
    from production_tools import annotations
    record = {'id': 'F-' + uuid.uuid4().hex[:12], 'comment': text(value.get('comment'), 'comment', 10000),
              'entry': text(value.get('entry'), 'entry', 500), 'created_at': timestamp(),
              'state': value.get('state'), 'captured_at': value.get('captured_at'), 'state_at': value.get('state_at')}
    record['annotations'] = annotations(value.get('annotations'))
    if record['annotations'] and not value.get('image'): raise ValueError(_msg('py.creator_tools.annotated.feedback.requires.an.image'))
    root, _ = find_project(root)
    archive_path(root, record['entry'])
    if value.get('comparison_to'):
        with database(root) as db: before = get(db, 'feedback', value['comparison_to'])
        if before['entry'] != record['entry'] or not before.get('image') or not value.get('image'): raise ValueError(_msg('py.creator_tools.compare.images.of.the.same.game.entry'))
        record['comparison_to'] = before['id']
    if len(json.dumps(record['state'], ensure_ascii=False)) > 32000: raise ValueError(_msg('py.creator_tools.game.state.exceeds.kb'))
    image = value.get('image')
    if image:
        if not isinstance(image, str) or not image.startswith('data:image/png;base64,'):
            raise ValueError(_msg('py.creator_tools.a.png.screenshot.is.required'))
        raw = base64.b64decode(image.split(',', 1)[1], validate=True)
        if len(raw) > 12 * 1024 * 1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(_msg('py.creator_tools.screenshot.must.be.a.png.up.to.mb'))
        if record['annotations']:
            import struct
            if len(raw) < 24 or list(struct.unpack('>II', raw[16:24])) != record['annotations']['size']:
                raise ValueError(_msg('py.creator_tools.selection.dimensions.do.not.match.the.png.image'))
        path = project_path(root, 'feedback/' + record['id'] + '.png'); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw); record['image'] = path.relative_to(root).as_posix()
    with database(root) as db: put(db, 'feedback', record['id'], record)
    return record


def export_game(root, entry, name):
    root, _ = find_project(root)
    entry_path = archive_path(root, entry)
    if not entry_path.is_file() or entry_path.suffix.lower() not in ('.html', '.htm'):
        raise ValueError(_msg('py.creator_tools.choose.an.html.entry.point.build.engine.projects'))
    # Export the selected build folder, or the project root for a root entry point.
    folder = entry_path.parent
    if folder != root and any(p in EXCLUDED or p.startswith('.') for p in folder.relative_to(root).parts):
        raise ValueError(_msg('py.creator_tools.choose.the.main.game.or.its.build.output'))
    files = game_files(folder)
    from asset_store import AssetStore
    assets = AssetStore(root).list()
    protected = {p for a in assets if a['usage_state'] == 'in_use' for p in a['files']}
    from production_tools import published_media
    protected.update(published_media(root))
    from studio_tools import published_media as sound_media
    protected.update(sound_media(root))
    unused = {p for a in assets if a['usage_state'] == 'unused' or a['status'] == 'retired' for p in a['files']} - protected
    for relative in protected:
        path = archive_path(root, relative)
        parts = path.relative_to(root).parts
        if (path.is_file() and path.is_relative_to(folder) and not any(p.startswith('.') for p in parts)
                and parts[0].lower() not in EXCLUDED - {'references', 'uploads'} and path.name.lower() not in PRIVATE):
            files[path.relative_to(folder).as_posix()] = path
    files = {n: p for n, p in files.items() if p.relative_to(root).as_posix() not in unused
             and not any(part.lower() in ('tests', 'test') or part.startswith('test_') or '.test.' in part or '.spec.' in part
                         for part in Path(n).parts)}
    if entry_path.name not in files: raise ValueError(_msg('py.creator_tools.the.selected.entry.is.excluded.from.export'))
    check_export_links(folder, files)
    record = {'id': 'EX-' + uuid.uuid4().hex[:12], 'name': text(name, 'name', 200), 'entry': entry_path.name, 'created_at': timestamp()}
    dest = project_path(root, 'data/exports/' + record['id'] + '.zip'); dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as archive:
        for relative, path in files.items(): archive.write(path, relative)
        archive.writestr('HOW-TO-RUN.txt', _msg('py.creator_tools.extract.the.entire.zip.keep.its.folder.structure' ,record['name'],entry_path.name))
    record.update(path=dest.relative_to(root).as_posix(), size=dest.stat().st_size, files=list(files), sha256=file_hash(dest))
    with database(root) as db: put(db, 'export', record['id'], record)
    return record


def check_export_links(folder, files):
    """Reject missing static HTML/CSS/module resources, without claiming gameplay validation."""
    class Resources(HTMLParser):
        def __init__(self): super().__init__(); self.urls = []
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag in ('script', 'img', 'audio', 'video', 'source', 'iframe', 'embed') and values.get('src'): self.urls.append(values['src'])
            if tag == 'link' and values.get('href'): self.urls.append(values['href'])
            if tag == 'video' and values.get('poster'): self.urls.append(values['poster'])
    for name, path in files.items():
        if name.startswith('content/timelines/') and path.suffix == '.json':
            for step in json.loads(path.read_text(encoding='utf-8')).get('steps', []):
                if step.get('src') and step['src'] not in files: raise ValueError(_msg('py.creator_tools.timeline.media.missing' ,step['src']))
        if name.startswith('content/soundscapes/') and path.suffix == '.json':
            for cue in json.loads(path.read_text(encoding='utf-8')).get('cues', []):
                if cue.get('path') not in files: raise ValueError(_msg('py.creator_tools.soundscape.media.missing') + str(cue.get('path')))
        suffix = path.suffix.lower()
        if suffix not in ('.html', '.htm', '.css', '.js', '.mjs'): continue
        source = path.read_text(encoding='utf-8-sig')
        urls = []
        if suffix in ('.html', '.htm'):
            parser = Resources(); parser.feed(source); urls = parser.urls
        elif suffix == '.css': urls = [m.group(2) for m in re.finditer(r'''url\(\s*(['"]?)(.*?)\1\s*\)''', source)]
        else: urls = [m.group(1) for m in re.finditer(r'''(?:\bfrom\s*|\bimport\s*\(?\s*)['"]([^'"]+)['"]''', source) if m.group(1).startswith(('.', '/'))]
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path: continue
            relative = unquote(parsed.path)
            candidate = (folder / relative.lstrip('/') if relative.startswith('/') else path.parent / relative).resolve()
            if not candidate.is_relative_to(folder) or candidate.relative_to(folder).as_posix() not in files:
                raise ValueError(_msg('py.creator_tools.export.resource.missing.place.resources.inside.the.selected' ,name,url))


def command(args):
    if args.store == 'story' and args.command == 'save':
        from decisions import input_text
        return story_save(args.project_root, json.loads(input_text(args)), args.revision, actor='ai')
    with database(args.project_root) as db:
        if args.command == 'show': return get(db, args.store, args.id)
        return {'items': entries(db, args.store)}
