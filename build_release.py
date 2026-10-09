"""Build a clean ZIP and self-extracting Windows launcher; never publish automatically."""
from message_catalog import text as _msg
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ('VERSION', 'LICENSE', 'README.md', 'CHANGELOG.md', 'bootstrap.json', 'start.bat', 'start.ps1',
         'requirements-runtime.txt', 'runtime_setup.py', 'new_project.py', 'decisions.py',
         'codex_bridge.py', 'dashboard.py', 'dashboard_state.py', 'dashboard_session.py',
         'dashboard_planning.py', 'instruction_bundle.py', 'localization.py', 'message_catalog.py', 'asset_store.py', 'reference_trace.py', 'project_workbench.py',
         'content_editor.py', 'creator_tools.py', 'creator_api.py', 'production_tools.py', 'gameplay_tools.py', 'studio_tools.py', 'live_tools.py')
# List every shipped resource explicitly. Test fixtures and scratch files must
# never become release content merely by being placed beside runtime resources.
RESOURCE_FILES = (
    'web/live.js', 'web/live-runtime.js', 'template/guide/play-workspace.md',
    'web/index.html', 'web/style.css', 'web/app.js', 'web/assets.js',
    'web/i18n.js', 'messages/catalog.json', 'web/messages.js', 'web/references.js', 'web/workbench.js', 'template/guide/workbench.md',
    'web/creator.js', 'web/feedback-bridge.js', 'template/guide/creator-tools.md', 'template/agents/story.md',
    'web/studio.js', 'web/sound-runtime.js', 'web/balance-runtime.js', 'template/guide/sound-balance.md',
    'web/gameplay.js', 'web/gameplay-runtime.js', 'template/guide/gameplay-tools.md',
    'web/production.js', 'web/timeline-player.js', 'template/guide/production-tools.md',
    'instructions/dashboard.toml',
    'template/AGENTS.md',
    'template/agents/developer.md', 'template/agents/art.md',
    'template/agents/verification.md', 'template/agents/game-designer.md',
    'template/agents/reference.md', 'template/guide/reference-tracing.md',
    'template/guide/commands.md', 'template/guide/assets.md', 'template/guide/game-architecture.md',
    'template/guide/work-decisions.md', 'template/guide/topic-additions.md',
    'template/guide/references.md', 'template/guide/production-workflow.md', 'template/guide/ui-design.md',
    'template/guide/product-design.md', 'template/guide/genre.md',
    'template/genres/steam-tags.md', 'template/genres/steam-genres.md',
    'template/catalogs/product-design-topics.md',
    'docs/third-party-licenses.md', 'docs/maintaining.md',
    'docs/README.ko.md', 'docs/README.ja.md',
    'docs/README.zh-Hans.md', 'docs/README.zh-Hant.md',
)


def payload_files():
    result = {name: ROOT / name for name in (*FILES, *RESOURCE_FILES)}
    # This is the end-user instruction document, never the local developer override.
    result['AGENTS.md'] = ROOT / 'template/AGENTS.md'
    for name, path in result.items():
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(_msg('py.build_release.external.distribution.path' ,path))
        if not path.is_file():
            raise ValueError(_msg('py.build_release.missing.distribution.file' ,name))
    return result


def build(output, windows=True):
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', version):
        raise ValueError(_msg('py.build_release.version.must.be.a.release.version.such.as'))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = f'Codex-Vibe-Game-Creator-{version}-windows-x64'
    archive = output / (stem + '.zip')
    manifest = {}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, path in sorted(payload_files().items()):
            data = path.read_bytes()
            manifest[name] = hashlib.sha256(data).hexdigest()
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
        z.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    assets = [archive]
    if windows:
        framework = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319'
        compiler = framework / 'csc.exe'
        if not compiler.is_file():
            raise RuntimeError(_msg('py.build_release.windows.net.framework.compiler.is.required.for.the'))
        executable = output / (stem + '-setup.exe')
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/optimize+',
                        f'/out:{executable}', f'/resource:{archive},payload.zip',
                        f'/resource:{ROOT / "messages/catalog.json"},messages.json',
                        f'/reference:{framework / "System.Web.Extensions.dll"}',
                        f'/reference:{framework / "System.IO.Compression.dll"}',
                        str(ROOT / 'packaging/Launcher.cs')], check=True)
        assets.append(executable)
    (output / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in assets), encoding='ascii')
    return assets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=_msg('cli.build_release.build.a.clean.zip.and.self.extracting.windows'))
    parser.add_argument('--output', default=str(ROOT / 'dist'))
    parser.add_argument('--zip-only', action='store_true')
    args = parser.parse_args()
    for asset in build(args.output, not args.zip_only):
        print(asset)
