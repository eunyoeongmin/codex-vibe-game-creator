"""Create a named project on request; creating a project never launches an AI."""
from __future__ import annotations
from message_catalog import text as _msg
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import uuid
import tomllib
import re
import decisions
import runtime_setup

HARNESS_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = HARNESS_ROOT / 'template'
GUIDE_MIGRATIONS = tomllib.loads((HARNESS_ROOT / 'instructions/dashboard.toml').read_text(encoding='utf-8'))['project_migrations']


def _guide(key, *values):
    return re.sub(r'\{(\d+)\}', lambda m: str(values[int(m[1])]) if int(m[1]) < len(values) else m[0], GUIDE_MIGRATIONS[key])

PROJECTS_ROOT = (runtime_setup.APP_HOME / 'GameProjects' if (HARNESS_ROOT / '.installed').is_file()
                 else HARNESS_ROOT.parent / 'GameProjects')


def installed_runtime():
    marker = runtime_setup.runtime_home() / 'ready.json'
    if not marker.is_file():
        raise ValueError(_msg('ui.runtime.missing.run.the.launcher.or.start.bat'))
    runtime = json.loads(marker.read_text(encoding='utf-8'))
    if not Path(runtime['python']).is_file():
        raise ValueError(_msg('ui.python.runtime.missing.run.the.launcher.to.repair'))
    return runtime


def ensure_production_support(project):
    """Refresh runtime support and add missing role guides without overwriting custom guides."""
    root, _ = decisions.find_project(project)
    script = decisions.project_path(root, '.harness/decisions.py')
    source_script = (HARNESS_ROOT / 'decisions.py').read_text(encoding='utf-8')
    if not script.exists() or script.read_text(encoding='utf-8') != source_script:
        decisions.atomic_text(script, source_script)
    decisions.atomic_text(decisions.project_path(root, '.harness/asset_store.py'),
                          (HARNESS_ROOT / 'asset_store.py').read_text(encoding='utf-8'))
    decisions.atomic_text(decisions.project_path(root, '.harness/reference_trace.py'),
                          (HARNESS_ROOT / 'reference_trace.py').read_text(encoding='utf-8'))
    decisions.atomic_text(decisions.project_path(root, '.harness/project_workbench.py'),
                          (HARNESS_ROOT / 'project_workbench.py').read_text(encoding='utf-8'))
    for module in ('live_tools.py', 'message_catalog.py', 'content_editor.py', 'creator_tools.py', 'production_tools.py', 'gameplay_tools.py', 'studio_tools.py'):
        decisions.atomic_text(decisions.project_path(root, '.harness/' + module), (HARNESS_ROOT / module).read_text(encoding='utf-8'))
    for relative in ('guide/assets.md', 'guide/production-workflow.md', 'agents/developer.md',
                     'agents/art.md', 'agents/verification.md', 'agents/game-designer.md',
                     'agents/reference.md', 'guide/reference-tracing.md', 'guide/workbench.md', 'guide/game-architecture.md',
                     'agents/story.md', 'guide/creator-tools.md', 'guide/production-tools.md', 'guide/gameplay-tools.md', 'guide/sound-balance.md', 'guide/ui-design.md', 'guide/play-workspace.md'):
        target = decisions.project_path(root, relative)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            decisions.atomic_text(target, (TEMPLATE_ROOT / relative).read_text(encoding='utf-8'))
    decisions.atomic_text(decisions.project_path(root, '.harness/timeline-player.js'), (HARNESS_ROOT / 'web/timeline-player.js').read_text(encoding='utf-8'))
    decisions.atomic_text(decisions.project_path(root, '.harness/gameplay-runtime.js'), (HARNESS_ROOT / 'web/gameplay-runtime.js').read_text(encoding='utf-8'))
    for runtime_name in ('sound-runtime.js','balance-runtime.js','live-runtime.js'):
        decisions.atomic_text(decisions.project_path(root, '.harness/' + runtime_name), (HARNESS_ROOT / 'web' / runtime_name).read_text(encoding='utf-8'))
    for relative, source in (('messages/catalog.json', 'messages/catalog.json'), ('messages.js', 'web/messages.js')):
        target = decisions.project_path(root, '.harness/' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        decisions.atomic_text(target, (HARNESS_ROOT / source).read_text(encoding='utf-8'))
    entry = decisions.project_path(root, 'AGENTS.md')
    original = entry.read_text(encoding='utf-8')
    text = original.replace('guide/development.md', 'guide/production-workflow.md')
    if 'guide/play-workspace.md' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        text += '\n' + next(line for line in source.splitlines() if '(guide/play-workspace.md)' in line) + '\n'
    if 'guide/ui-design.md' not in text:
        template_entry = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        ui_route = next(line for line in template_entry.splitlines() if '(guide/ui-design.md)' in line)
        text += '\n' + ui_route + '\n'
    if 'guide/creator-tools.md' not in text:
        text += _guide('py.new_project.message')
    if 'guide/production-tools.md' not in text:
        text += _guide('py.new_project.message.2')
    if 'guide/gameplay-tools.md' not in text:
        text += _guide('py.new_project.message.3')
    if 'guide/sound-balance.md' not in text:
        text += _guide('py.new_project.message.4')
    workbench_route = _guide('py.new_project.message.5')
    text = text.replace(_guide('py.new_project.message.6'), workbench_route)
    if 'guide/workbench.md' not in text:
        text += '\n' + workbench_route + '\n'
    if _guide('py.new_project.message.7') not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        reading_policy = source[source.index(_guide('py.new_project.message.7')):source.index(_guide('py.new_project.message.8'))]
        position = text.find(_guide('py.new_project.message.8'))
        position = position if position >= 0 else len(text)
        text = text[:position] + '\n' + reading_policy + text[position:]
    if _guide('py.new_project.message.9') not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        role_scope = source[source.index(_guide('py.new_project.message.9')):source.index(_guide('py.new_project.message.10'))]
        # Put role boundaries before existing rules, preserving project-specific text.
        first_heading = text.find('\n## ')
        position = first_heading + 1 if first_heading >= 0 else len(text)
        text = text[:position] + '\n' + role_scope + text[position:]
    if 'agents/game-designer.md' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        row = next(line for line in source.splitlines() if '| agents/game-designer.md |' in line)
        table = _guide('py.new_project.message.11')
        if table in text:
            text = text.replace(table, table + '\n' + row, 1)
        else:
            text += _guide('py.new_project.message.12')
    if 'agents/reference.md' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        row = next(line for line in source.splitlines() if '| agents/reference.md |' in line)
        table = _guide('py.new_project.message.11')
        text = text.replace(table, table + '\n' + row, 1) if table in text else text + _guide('py.new_project.message.13')
    reference_guide = decisions.project_path(root, 'guide/references.md')
    if reference_guide.is_file():
        previous = reference_guide.read_text(encoding='utf-8')
        if 'reference-tracing.md' not in previous:
            decisions.atomic_text(reference_guide, previous + _guide('py.new_project.message.14'))
    for row in (
        _guide('py.new_project.message.15'),
        _guide('py.new_project.message.16'),
        _guide('py.new_project.message.17'),
    ):
        text = text.replace(row + '\n', '')
    for label, relative in ((_guide('py.new_project.message.18'), 'agents/developer.md'),
                            (_guide('py.new_project.message.19'), 'agents/art.md'),
                            (_guide('py.new_project.message.20'), 'agents/verification.md')):
        text = text.replace(_guide('py.new_project.message.21' ,label,label,relative), '')
    old_routing = _guide('py.new_project.message.22')
    text = text.replace(old_routing,
        _guide('py.new_project.message.23'))
    asset_routing = _guide('py.new_project.message.24')
    text = text.replace(_guide('py.new_project.message.25'), asset_routing)
    if 'guide/assets.md' not in text:
        text += '\n' + asset_routing + '\n'
    if 'guide/production-workflow.md' not in text:
        text += _guide('py.new_project.message.26')
    if text != original:
        decisions.atomic_text(entry, text)
    workflow = decisions.project_path(root, 'guide/production-workflow.md')
    if workflow.is_file():
        existing = workflow.read_text(encoding='utf-8')
        legacy = _guide('ui_design.legacy_asset_timing')
        if legacy in existing:
            source = (TEMPLATE_ROOT / 'guide/production-workflow.md').read_text(encoding='utf-8')
            replacement = next(line for line in source.splitlines() if '(ui-design.md#' in line)
            decisions.atomic_text(workflow, existing.replace(legacy, replacement))
    product = decisions.project_path(root, 'guide/product-design.md')
    if product.is_file():
        existing = product.read_text(encoding='utf-8')
        updated = existing.replace('development.md', 'production-workflow.md')
        if updated != existing:
            decisions.atomic_text(product, updated)
    work = decisions.project_path(root, 'guide/work-decisions.md')
    if work.is_file():
        existing = work.read_text(encoding='utf-8')
        if _guide('py.new_project.message.27') not in existing:
            source = (TEMPLATE_ROOT / 'guide/work-decisions.md').read_text(encoding='utf-8')
            selection = source[source.index(_guide('py.new_project.message.27')):source.index(_guide('py.new_project.message.28'))]
            condition = next(line for line in source.splitlines() if line.startswith(_guide('py.new_project.message.29')))
            updated = existing.replace(_guide('py.new_project.message.30'),
                                       _guide('py.new_project.message.31') + condition)
            updated = updated.replace(_guide('py.new_project.message.32'),
                _guide('py.new_project.message.33'))
            updated += '\n' + selection
            decisions.atomic_text(work, updated)


def create_project(projects_root=None, *, name=_msg('py.new_project.message.34'), runtime=None):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError(_msg('ui.project.names.must.contain.characters'))
    parent = Path(projects_root if projects_root is not None else PROJECTS_ROOT).resolve()
    if parent.is_relative_to(HARNESS_ROOT):
        raise ValueError(_msg('py.new_project.message.35'))
    runtime = runtime or installed_runtime()
    python = Path(runtime['python']).resolve()
    if not python.is_file():
        raise ValueError(_msg('ui.python.runtime.executable.not.found'))
    if not (TEMPLATE_ROOT / 'AGENTS.md').is_file():
        raise ValueError(_msg('py.new_project.message.36'))
    project_id = 'game-' + uuid.uuid4().hex
    parent.mkdir(parents=True, exist_ok=True)
    project = parent / project_id
    project.mkdir()
    try:
        support = project / '.harness'
        support.mkdir()
        shutil.copyfile(HARNESS_ROOT / 'decisions.py', support / 'decisions.py')
        shutil.copyfile(HARNESS_ROOT / 'asset_store.py', support / 'asset_store.py')
        shutil.copyfile(HARNESS_ROOT / 'reference_trace.py', support / 'reference_trace.py')
        shutil.copyfile(HARNESS_ROOT / 'project_workbench.py', support / 'project_workbench.py')
        for module in ('live_tools.py', 'message_catalog.py', 'content_editor.py', 'creator_tools.py', 'production_tools.py', 'gameplay_tools.py', 'studio_tools.py'):
            shutil.copyfile(HARNESS_ROOT / module, support / module)
        shutil.copyfile(HARNESS_ROOT / 'web/timeline-player.js', support / 'timeline-player.js')
        shutil.copyfile(HARNESS_ROOT / 'web/gameplay-runtime.js', support / 'gameplay-runtime.js')
        for runtime_name in ('sound-runtime.js','balance-runtime.js','live-runtime.js'):
            shutil.copyfile(HARNESS_ROOT / 'web' / runtime_name, support / runtime_name)
        (support / 'messages').mkdir()
        shutil.copyfile(HARNESS_ROOT / 'messages/catalog.json', support / 'messages/catalog.json')
        shutil.copyfile(HARNESS_ROOT / 'web/messages.js', support / 'messages.js')
        shutil.copyfile(HARNESS_ROOT / 'requirements-runtime.txt', support / 'requirements-runtime.txt')
        (support / 'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
        replacements = {
            '{{HARNESS_PYTHON}}': python.as_posix(),
            '{{HARNESS_DECISIONS}}': (support / 'decisions.py').as_posix(),
            '{{HARNESS_ROOT}}': support.as_posix(),
            '{{MODEL_CACHE}}': Path(runtime['model_cache']).as_posix(),
        }
        for source in sorted(TEMPLATE_ROOT.rglob('*')):
            if not source.resolve().is_relative_to(TEMPLATE_ROOT.resolve()):
                raise ValueError(_msg('py.new_project.message.37'))
            destination = project / source.relative_to(TEMPLATE_ROOT)
            if source.is_dir():
                destination.mkdir(exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.suffix == '.md':
                    text = source.read_text(encoding='utf-8')
                    for token, value in replacements.items():
                        text = text.replace(token, value)
                    destination.write_text(text, encoding='utf-8')
                else:
                    shutil.copyfile(source, destination)
        marker = {'project_id': project_id, 'name': name.strip(),
                  'created_at': datetime.now(timezone.utc).isoformat()}
        (project / '.project').write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding='utf-8')
        (project / '.gitignore').write_text('.harness/tmp/\n__pycache__/\n', encoding='utf-8')
        (support / 'tmp').mkdir()
        with decisions.database(project / 'data/decisions.sqlite', 'user', write=True, project_root=project):
            pass
        return project
    except Exception:
        if project.resolve().parent == parent and project.name == project_id:
            shutil.rmtree(project)
        raise


def main():
    parser = argparse.ArgumentParser(description=_msg('cli.new_project.create.a.named.project.on.request.creating.a'))
    parser.add_argument('name', help=_msg('py.new_project.message.38'))
    args = parser.parse_args()
    print(create_project(name=args.name))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
