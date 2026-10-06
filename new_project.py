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
    for relative in ('guide/assets.md', 'guide/production-workflow.md', 'agents/developer.md',
                     'agents/art.md', 'agents/verification.md', 'agents/game-designer.md',
                     'agents/reference.md', 'guide/reference-tracing.md'):
        target = decisions.project_path(root, relative)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            decisions.atomic_text(target, (TEMPLATE_ROOT / relative).read_text(encoding='utf-8'))
    entry = decisions.project_path(root, 'AGENTS.md')
    original = entry.read_text(encoding='utf-8')
    text = original.replace('guide/development.md', 'guide/production-workflow.md')
    if '## 역할별 적용 범위' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        role_scope = source[source.index('## 역할별 적용 범위'):source.index('## 실행 환경')]
        # Put role boundaries before existing rules, preserving project-specific text.
        first_heading = text.find('\n## ')
        position = first_heading + 1 if first_heading >= 0 else len(text)
        text = text[:position] + '\n' + role_scope + text[position:]
    if 'agents/game-designer.md' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        row = next(line for line in source.splitlines() if '| agents/game-designer.md |' in line)
        table = '| 배정할 작업 | 담당 | 담당에게 전달할 지침 |\n|---|---|---|'
        if table in text:
            text = text.replace(table, table + '\n' + row, 1)
        else:
            text += '\n게임 규칙·콘텐츠·수치와 시스템 연결 설계는 게임 디자이너에게 맡기고 agents/game-designer.md 경로를 전달한다. 해당 담당이 지침을 직접 읽는다.\n'
    if 'agents/reference.md' not in text:
        source = (TEMPLATE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        row = next(line for line in source.splitlines() if '| agents/reference.md |' in line)
        table = '| 배정할 작업 | 담당 | 담당에게 전달할 지침 |\n|---|---|---|'
        text = text.replace(table, table + '\n' + row, 1) if table in text else text + '\n레퍼런스 조사·해석 근거 정리는 레퍼런스 담당에게 맡기고 agents/reference.md 경로를 전달한다. 해당 담당이 지침을 직접 읽는다.\n'
    reference_guide = decisions.project_path(root, 'guide/references.md')
    if reference_guide.is_file():
        previous = reference_guide.read_text(encoding='utf-8')
        if 'reference-tracing.md' not in previous:
            decisions.atomic_text(reference_guide, previous + '\n조사·해석·적용의 추적 기록은 [레퍼런스 추적 기록](reference-tracing.md)을 따른다.\n')
    for row in (
        '| 개발 담당으로 구현이나 수정을 시작할 때 | agents/developer.md |',
        '| 아트 담당으로 에셋을 제작·관리할 때 | agents/art.md |',
        '| 검증 담당으로 확인 작업을 수행할 때 | agents/verification.md |',
    ):
        text = text.replace(row + '\n', '')
    for label, relative in (('개발 담당의 구현', 'agents/developer.md'),
                            ('아트 담당의 제작·관리', 'agents/art.md'),
                            ('검증 담당의 확인', 'agents/verification.md')):
        text = text.replace(f'{label} 전에 [{label} 지침]({relative})을 읽는다.\n', '')
    old_routing = '아래 상황이 되면 작업을 시작하기 전에 해당 문서를 읽는다. 읽지 않고 그 작업의 규칙을 추측해서 적용하지 않는다.'
    text = text.replace(old_routing,
        '아래 표는 해당 작업을 직접 수행하는 담당에게만 적용한다. 배정·결과 수신만 하는 오케스트레이터에게 하위 담당의 실무 문서 읽기를 요구하지 않는다. 읽지 않고 그 작업의 규칙을 추측해서 적용하지 않는다.')
    asset_routing = '에셋을 직접 제작·적용·교체하거나 관리하는 담당은 [에셋 관리 지침](guide/assets.md)을 읽는다.'
    text = text.replace('에셋을 제작·적용·교체하거나 관리할 때는 먼저 [에셋 관리 지침](guide/assets.md)을 읽는다.', asset_routing)
    if 'guide/assets.md' not in text:
        text += '\n' + asset_routing + '\n'
    if 'guide/production-workflow.md' not in text:
        text += '\n오케스트레이터는 작업 배분·진행·마감 전에 [제작 진행 절차](guide/production-workflow.md)를 읽는다.\n'
    if text != original:
        decisions.atomic_text(entry, text)
    product = decisions.project_path(root, 'guide/product-design.md')
    if product.is_file():
        existing = product.read_text(encoding='utf-8')
        updated = existing.replace('development.md', 'production-workflow.md')
        if updated != existing:
            decisions.atomic_text(product, updated)
    work = decisions.project_path(root, 'guide/work-decisions.md')
    if work.is_file():
        existing = work.read_text(encoding='utf-8')
        if '### AI가 선택한 내용과 승인 구분' not in existing:
            source = (TEMPLATE_ROOT / 'guide/work-decisions.md').read_text(encoding='utf-8')
            selection = source[source.index('### AI가 선택한 내용과 승인 구분'):source.index('### 테이블 구조')]
            condition = next(line for line in source.splitlines() if line.startswith('- 승인된 기능을 구현하는 데 필요한 미결정'))
            updated = existing.replace('### 저장 조건 (하나라도 해당하면 저장)',
                                       '### 저장 조건 (하나라도 해당하면 저장)\n' + condition)
            updated = updated.replace('저장하지 않는 것: 변수명, 포맷팅, 단순 버그 수정, 사소한 구현 선택',
                '저장하지 않는 것: 동작·결과에 영향을 주는 새 선택이 없는 변수명 변경, 포맷팅, 단순 버그 수정.')
            updated += '\n' + selection
            decisions.atomic_text(work, updated)


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
        shutil.copyfile(HARNESS_ROOT / 'asset_store.py', support / 'asset_store.py')
        shutil.copyfile(HARNESS_ROOT / 'reference_trace.py', support / 'reference_trace.py')
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
