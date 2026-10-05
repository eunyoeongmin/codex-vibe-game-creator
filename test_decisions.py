"""Three requested isolation checks, each using disposable external projects."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import decisions
import new_project


class ProjectIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harness-isolation-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.projects = self.root / 'GameProjects'

    def create(self):
        return new_project.create_project(self.projects)

    def invoke(self, cwd, *args, payload=None):
        try:
            root, _ = decisions.find_project(cwd)
            script = root / '.harness/decisions.py'
        except ValueError:
            script = Path(decisions.__file__).resolve()
        return subprocess.run(
            [new_project.installed_runtime()['python'], '-B', str(script), *args],
            cwd=cwd, input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True, encoding='utf-8', check=False)

    def rows(self, project, table):
        connection = sqlite3.connect(project / 'data' / 'decisions.sqlite')
        try:
            return connection.execute(f'SELECT * FROM {table}').fetchall()
        finally:
            connection.close()

    def test_1_missing_marker_rejected(self):
        result = self.invoke(self.root, 'user', 'list')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.project', json.loads(result.stderr)['error'])
        self.assertFalse((self.root / 'data').exists())

    def test_2_external_reference_path_rejected(self):
        project = self.create()
        outside = self.root / 'outside.png'
        outside.write_bytes(b'outside-project-reference')
        result = self.invoke(project, 'reference', 'add', payload={
            'kind': 'image', 'title_or_url': '외부 이미지', 'file_path': str(outside),
            'user_note': '이 이미지를 참고', 'aspects': ['art_style']})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('프로젝트 폴더 밖', json.loads(result.stderr)['error'])
        self.assertEqual(self.rows(project, 'user_references'), [])
        self.assertFalse((project / 'references').exists())
        self.assertEqual(outside.read_bytes(), b'outside-project-reference')

    def test_3_two_project_databases_are_isolated(self):
        first, second = self.create(), self.create()
        identities = []
        for project in (first, second):
            self.assertFalse(project.is_relative_to(new_project.HARNESS_ROOT))
            project_id = json.loads((project / '.project').read_text(encoding='utf-8'))['project_id']
            identities.append(project_id)
            self.assertEqual(project.name, project_id)
            for table in ('work_decisions', 'user_decisions', 'user_references', 'topic_additions'):
                self.assertEqual(self.rows(project, table), [])
            agents = (project / 'AGENTS.md').read_text(encoding='utf-8')
            self.assertIn((project / '.harness/decisions.py').as_posix(), agents)
            self.assertIn(Path(new_project.installed_runtime()['python']).as_posix(), agents)
            self.assertNotIn(new_project.HARNESS_ROOT.as_posix(), agents)
            for path in [project / 'AGENTS.md', *project.glob('guide/*.md')]:
                self.assertNotIn('{{HARNESS_', path.read_text(encoding='utf-8'))
                self.assertNotIn('--project-id', path.read_text(encoding='utf-8'))
            self.assertTrue((project / 'catalogs/product-design-topics.md').is_file())
            self.assertTrue((project / 'genres/steam-genres.md').is_file())
            result = self.invoke(project, 'user', 'add', payload={
                'category': 'genre', 'topic': '장르', 'decision': project_id,
                'status': 'confirmed', 'user_quote': f'{project_id}의 사용자 원문',
                'assistant_reply': '이 프로젝트에만 저장합니다.', 'ai_role': 'explanation'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['saved']['project_id'], project_id)
        self.assertNotEqual(*identities)
        for project, project_id in zip((first, second), identities):
            nested = project / 'game' / 'src'
            nested.mkdir(parents=True)
            result = self.invoke(nested, 'user', 'list')
            self.assertEqual(result.returncode, 0, result.stderr)
            records = json.loads(result.stdout)['records']
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['project_id'], project_id)
            self.assertEqual(records[0]['decision'], project_id)
            self.assertFalse((nested / 'data').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
