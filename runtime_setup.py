"""Install the shared runtime outside the distributed harness, then open the dashboard."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
APP_HOME = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'GameHarness'
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


def runtime_home():
    digest = hashlib.sha256((ROOT / 'requirements-runtime.txt').read_bytes()).hexdigest()[:12]
    return APP_HOME / 'runtimes' / f'py{sys.version_info.major}{sys.version_info.minor}-{digest}'


def python_path(folder):
    return folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def prepare():
    target = runtime_home()
    python = python_path(target)
    marker = target / 'ready.json'
    if marker.is_file() and python.is_file():
        return json.loads(marker.read_text(encoding='utf-8'))
    print('공용 Python 환경을 준비합니다. 첫 실행에는 시간이 걸릴 수 있습니다.', flush=True)
    venv.EnvBuilder(with_pip=True).create(target)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-runtime.txt')], check=True)
    cache = target / 'model-cache'
    existing = ROOT / '.venv-runtime/model-cache'
    if existing.is_dir() and not cache.exists():
        print('기존 모델 캐시를 공용 환경에 복사합니다.', flush=True)
        shutil.copytree(existing, cache, ignore=shutil.ignore_patterns('.locks', '*.lock'))
    print('기록 저장에 필요한 모델과 패키지를 확인합니다.', flush=True)
    script = ('import sys, sqlite_vec, semantica; from fastembed import TextEmbedding; '
              'model=TextEmbedding(model_name=sys.argv[1],cache_dir=sys.argv[2],threads=2); '
              'assert len(next(iter(model.embed(["환경 확인"])))) == 384')
    subprocess.run([str(python), '-c', script, MODEL, str(cache)], check=True)
    manifest = {'python': str(python.resolve()), 'model_cache': str(cache.resolve()),
                'runtime_version': target.name}
    marker.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    runtime = prepare()
    print(f'공용 환경: {runtime["python"]}', flush=True)
    if args.launch:
        return subprocess.call([runtime['python'], '-B', str(ROOT / 'dashboard.py'), '--open'], cwd=ROOT)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'환경 준비 실패: {error}', file=sys.stderr)
        raise SystemExit(1)
