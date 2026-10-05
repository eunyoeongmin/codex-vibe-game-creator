"""Create a named project on request; creating a project never launches an AI."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import uuid
import decisions
import runtime_setup

HARNESS_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = HARNESS_ROOT / 'template'
PROJECTS_ROOT = (runtime_setup.APP_HOME / 'GameProjects' if (HARNESS_ROOT / '.installed').is_file()
                 else HARNESS_ROOT.parent / 'GameProjects')


def installed_runtime():
    marker = runtime_setup.runtime_home() / 'ready.json'
    if not marker.is_file():
        raise ValueError('공용 실행 환경이 없습니다. start.bat을 먼저 실행하세요.')
    runtime = json.loads(marker.read_text(encoding='utf-8'))
    if not Path(runtime['python']).is_file():
        raise ValueError('공용 Python이 없습니다. start.bat으로 환경을 다시 준비하세요.')
    return runtime


def ensure_production_support(project):
    """Upgrade harness-owned milestone support when an older project starts production."""
    root, _ = decisions.find_project(project)
    script = decisions.project_path(root, '.harness/decisions.py')
    source_script = (HARNESS_ROOT / 'decisions.py').read_text(encoding='utf-8')
    if not script.exists() or script.read_text(encoding='utf-8') != source_script:
        decisions.atomic_text(script, source_script)
    guide = decisions.project_path(root, 'guide/development.md')
    existing = guide.read_text(encoding='utf-8')
    if '## 제작 진행 규칙' not in existing:
        source = (TEMPLATE_ROOT / 'guide/development.md').read_text(encoding='utf-8')
        addition = source[source.index('## 제작 진행 규칙'):]
        decisions.atomic_text(guide, existing + '\n' + addition)


def create_project(projects_root=None, *, name='새 게임', runtime=None):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError('프로젝트 이름은 1~100자로 입력하세요.')
    parent = Path(projects_root if projects_root is not None else PROJECTS_ROOT).resolve()
    if parent.is_relative_to(HARNESS_ROOT):
        raise ValueError('GameProjects는 하네스 폴더 밖에 있어야 합니다.')
    runtime = runtime or installed_runtime()
    python = Path(runtime['python']).resolve()
    if not python.is_file():
        raise ValueError('공용 Python 실행 파일을 찾을 수 없습니다.')
    if not (TEMPLATE_ROOT / 'AGENTS.md').is_file():
        raise ValueError('template/AGENTS.md가 필요합니다.')
    project_id = 'game-' + uuid.uuid4().hex
    parent.mkdir(parents=True, exist_ok=True)
    project = parent / project_id
    project.mkdir()
    try:
        support = project / '.harness'
        support.mkdir()
        shutil.copyfile(HARNESS_ROOT / 'decisions.py', support / 'decisions.py')
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
                raise ValueError('템플릿 외부 파일은 복사할 수 없습니다.')
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', help='프로젝트 표시 이름')
    args = parser.parse_args()
    print(create_project(name=args.name))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
