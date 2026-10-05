"""Locale persistence, unchanged original records, and clean distribution checks."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from urllib.request import urlopen
import zipfile

from build_release import build, payload_files
from dashboard_session import ProjectSession
from dashboard_state import State
from localization import CATALOG, LANGUAGES, translate
from test_dashboard import FakeRpc
import test_dashboard
import test_planning


class LocalizationTests(unittest.TestCase):
    setUp = test_planning.PlanningTests.setUp
    add = test_planning.PlanningTests.add
    server = test_dashboard.DashboardTests.server
    request = test_dashboard.DashboardTests.request

    def test_language_setting_assets_and_session_instruction(self):
        server = self.server()
        for language in LANGUAGES:
            result = self.request(server, 'preferences', {'language': language})
            self.assertEqual(result['language'], language)
        with self.assertRaises(Exception):
            self.request(server, 'preferences', {'language': 'invalid'})
        self.assertEqual(self.app.state.setting('language'), 'zh-Hant')
        reopened = State(self.folder / 'state', self.app.state.projects_root)
        self.assertEqual(reopened.setting('language'), 'zh-Hant')
        for name in ('i18n.js', 'locales.json'):
            with urlopen(f'http://127.0.0.1:{server.server_port}/{name}') as response:
                self.assertEqual(response.status, 200)
        with patch('dashboard_session.CodexRpc', FakeRpc):
            session = ProjectSession(self.app.state, self.pid, self.folder / 'codex')
            self.app.sessions[self.pid] = session
            session.connect()
            self.assertIn('Traditional Chinese', session.rpc.calls[0][1]['developerInstructions'])
            before = len(session.rpc.calls)
            self.request(server, 'preferences', {'language': 'en'})
            self.assertEqual(len(session.rpc.calls), before)  # No automatic model turn.
            session.turn_id = None
            session.send_message('keep this original message')
            resumes = [p for method, p in session.rpc.calls if method == 'thread/resume']
            self.assertIn('English', resumes[-1]['developerInstructions'])
            self.assertEqual(session.rpc.calls[-1][1]['input'][0]['text'], 'keep this original message')

    def test_spec_language_is_snapshotted_and_original_decisions_are_preserved(self):
        self.app.state.set_setting('language', 'ja')
        self.add('操作方式', category='platform', status='proposed', decision='キーボード — 用户原文')
        summary = self.app.planning.open_summary(self.pid)
        self.app.planning.approve(self.pid, summary['fingerprint'])
        self.app.planning.delivered(self.pid)
        original = (self.root / 'SPEC.md').read_bytes()
        self.assertIn('プラットフォーム・操作', original.decode())
        self.assertIn('キーボード — 用户原文', original.decode())
        self.app.state.set_setting('language', 'zh-Hans')
        self.assertEqual(self.app.planning.progress(self.pid)['spec_version'], 1)
        self.assertEqual((self.root / 'SPEC.md').read_bytes(), original)

    def test_catalog_coverage_and_placeholder_parity(self):
        for key, translations in CATALOG.items():
            self.assertEqual(set(translations), set(LANGUAGES) - {'ko'}, key)
            for language, text in translations.items():
                self.assertTrue(text.strip(), key)
                self.assertEqual(set(re.findall(r'\{\d+\}', text)), set(re.findall(r'\{\d+\}', key)), key)
        source = Path('web/app.js').read_text(encoding='utf-8')
        for key in re.findall(r"\bt\('((?:[^'\\]|\\.)*)'", source):
            key = key.replace('\\n', '\n').replace("\\'", "'")
            self.assertIn(key, CATALOG)
        self.assertEqual(translate('확정 {0} / {1} 항목', 'zh-Hant', 2, 11), '已確認 2 / 11 項')

    def test_release_payload_is_allowlisted_and_contains_no_private_data(self):
        assets = build(self.folder / 'dist', windows=False)
        with zipfile.ZipFile(assets[0]) as archive:
            self.assertEqual(set(archive.namelist()), set(payload_files()) | {'MANIFEST.json'})
            for name in archive.namelist():
                self.assertNotIn('AGENTS.override', name)
                self.assertNotIn('.local/', name)
                self.assertFalse(name.endswith(('.sqlite', '.pyc')))
            manifest = json.loads(archive.read('MANIFEST.json'))
            for name, digest in manifest.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
            self.assertEqual(archive.read('AGENTS.md'), Path('template/AGENTS.md').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
