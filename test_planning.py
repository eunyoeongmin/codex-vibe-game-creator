"""Milestone CLI and dashboard planning checks using disposable projects only."""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

import decisions
from dashboard import App
from dashboard_planning import START_QUOTE, current_records
import new_project
from test_dashboard import DashboardTests


class PlanningTests(unittest.TestCase):
    server = DashboardTests.server
    request = DashboardTests.request

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harness-planning-test-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.runtime = new_project.installed_runtime()
        self.app = App(self.folder / 'state', self.folder / 'GameProjects', self.runtime)
        self.addCleanup(self.app.close)
        self.root = new_project.create_project(self.app.state.projects_root, runtime=self.runtime)
        self.project = self.app.state.add(self.root)
        self.pid = self.project['id']

    def cli(self, *args):
        return subprocess.run([self.runtime['python'], '-B', str(self.root / '.harness/decisions.py'),
                               'milestone', *args], cwd=self.root, capture_output=True, encoding='utf-8')

    def add(self, topic, *, category='scope', status='confirmed', supersedes=None, decision='한글 선택'):
        with decisions.database(self.root / 'data/decisions.sqlite', 'user', write=True,
                                project_root=self.root) as c, decisions.transaction(c):
            return decisions.insert_record(c, 'user', {
                'project_id': self.pid, 'category': category, 'topic': topic, 'decision': decision,
                'status': status, 'user_quote': '사용자 원문', 'assistant_reply': 'AI 답변 원문',
                'ai_role': 'proposal' if status == 'proposed' else 'explanation',
                'supersedes': supersedes, 'reference_ids': []})

    def test_milestone_rejects_invalid_status(self):
        result = self.cli('set-status', 'M-001', 'invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'milestones.json').exists())

    def test_milestone_rejects_second_active(self):
        for title in ('첫 마일스톤', '두 번째'):
            self.assertEqual(self.cli('add', '--title', title, '--done-condition', '화면 확인',
                                      '--not-doing', '추가 기능').returncode, 0)
        self.assertEqual(self.cli('set-status', 'M-001', 'active').returncode, 0)
        self.assertNotEqual(self.cli('set-status', 'M-002', 'active').returncode, 0)
        records = json.loads((self.root / 'milestones.json').read_text(encoding='utf-8'))
        self.assertEqual([r['status'] for r in records], ['active', 'pending'])

    def test_milestone_korean_round_trip_and_empty_fields(self):
        result = self.cli('add', '--title', '택시 승객 수송', '--done-condition', '목적지 도착',
                          '--not-doing', '에셋 교체')
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(self.cli('list').stdout)['milestones'][0]
        self.assertEqual(record, {'id': 'M-001', 'title': '택시 승객 수송',
                                  'done_condition': '목적지 도착', 'not_doing': '에셋 교체', 'status': 'pending'})
        for title, done in [(' ', '완료'), ('제목', ' ')]:
            self.assertNotEqual(self.cli('add', '--title', title, '--done-condition', done,
                                         '--not-doing', '').returncode, 0)

    def test_summary_approval_preserves_records_vectors_and_versions(self):
        old = self.add('장르', category='genre')
        current = self.add('장르', category='genre', supersedes=old['id'], decision='퍼즐')
        proposed = self.add('조작 방식', category='platform', status='proposed', decision='키보드')
        planning = self.app.planning
        card = planning.open_summary(self.pid)
        self.assertEqual(card['confirmed_count'], 1)
        self.assertEqual(card['categories'][0]['items'][0]['id'], current['id'])
        self.assertEqual(next(c for c in card['categories'] if c['category'] == 'mood')['status'], 'undecided')
        self.assertEqual(planning.approve(self.pid, card['fingerprint']), 1)
        with decisions.database(self.root / 'data/decisions.sqlite', 'user', project_root=self.root) as c:
            original = c.execute('SELECT * FROM user_decisions WHERE id=?', (proposed['id'],)).fetchone()
            self.assertEqual(original['status'], 'proposed')
            self.assertEqual(original['user_quote'], '사용자 원문')
            saved = next(r for r in current_records(c, self.pid) if r['category'] == 'platform')
            self.assertEqual(saved['user_quote'], START_QUOTE)
            self.assertEqual(saved['assistant_reply'], 'AI 답변 원문')
            self.assertEqual(saved['supersedes'], proposed['id'])
            vectors = [c.execute('SELECT embedding FROM user_decision_vectors WHERE id=?', (rid,)).fetchone()[0]
                       for rid in (proposed['id'], saved['id'])]
            self.assertEqual(*vectors)
        spec1 = (self.root / 'SPEC.md').read_text(encoding='utf-8')
        self.assertIn(saved['id'], spec1)
        self.assertIn(saved['created_at'], spec1)
        planning.delivered(self.pid)
        self.add('장르', category='genre', supersedes=current['id'], decision='액션')
        updated = planning.progress(self.pid)
        self.assertEqual(updated['spec_version'], 2)
        self.assertFalse(updated['show_summary'])
        self.assertEqual((self.root / '.harness/specs/SPEC.v001.md').read_text(encoding='utf-8'), spec1)
        self.assertIn('액션', (self.root / 'SPEC.md').read_text(encoding='utf-8'))
        self.assertEqual(planning.progress(self.pid)['spec_version'], 2)

    def test_milestone_progress_round_trip_and_planning_isolation(self):
        self.add('플레이 시간')
        planning = self.app.planning
        card = planning.open_summary(self.pid)
        planning.approve(self.pid, card['fingerprint'])
        planning.delivered(self.pid)
        self.assertEqual(self.cli('add', '--title', '승객 수송', '--done-condition', '도착 확인',
                                  '--not-doing', '에셋').returncode, 0)
        self.assertNotEqual(self.cli('set-progress', 'M-001', '--completed', '0', '--total', '3',
                                     '--note', '시작').returncode, 0)
        self.assertEqual(self.cli('set-status', 'M-001', 'active').returncode, 0)
        for completed, total in [(-1, 3), (4, 3), (0, 0)]:
            self.assertNotEqual(self.cli('set-progress', 'M-001', '--completed', str(completed),
                                         '--total', str(total), '--note', '잘못된 수').returncode, 0)
        saved = self.cli('set-progress', 'M-001', '--completed', '1', '--total', '3',
                         '--note', '승객 탑승 구현 완료')
        self.assertEqual(saved.returncode, 0, saved.stderr)
        record = json.loads(self.cli('list').stdout)['milestones'][0]
        self.assertEqual(record['progress']['note'], '승객 탑승 구현 완료')
        progress = planning.progress(self.pid)
        self.assertEqual(progress['production']['current'], record)
        self.assertEqual(progress['production']['completed'], 0)
        self.assertEqual(progress['confirmed_count'], 1)
        self.assertEqual(progress['spec_version'], 1)
        self.assertEqual(self.cli('set-progress', 'M-001', '--completed', '3', '--total', '3',
                                  '--note', '완료 조건 확인 대기').returncode, 0)
        self.assertEqual(planning.progress(self.pid)['production']['current']['status'], 'active')
        self.assertEqual(self.cli('set-status', 'M-001', 'done').returncode, 0)
        progress = planning.progress(self.pid)['production']
        self.assertEqual(progress['completed'], 1)
        self.assertIsNone(progress['current'])

    def test_legacy_milestones_and_invalid_progress_do_not_break_planning(self):
        self.assertEqual(self.cli('add', '--title', '기존 작업', '--done-condition', '화면 확인',
                                  '--not-doing', '').returncode, 0)
        progress = self.app.planning.progress(self.pid)
        self.assertFalse(progress['production']['started'])
        self.assertNotIn('progress', progress['production']['milestones'][0])
        (self.root / 'milestones.json').write_text('{broken', encoding='utf-8')
        progress = self.app.planning.progress(self.pid)
        self.assertTrue(progress['production']['error'])
        self.assertEqual(progress['confirmed_count'], 0)

    def test_stale_summary_and_conflicts_do_not_partially_approve(self):
        self.add('조작', status='proposed')
        card = self.app.planning.open_summary(self.pid)
        self.add('화풍', category='art_style')
        with self.assertRaisesRegex(ValueError, '변경'):
            self.app.planning.approve(self.pid, card['fingerprint'])
        self.add('조작', status='confirmed')
        card = self.app.planning.progress(self.pid)
        with self.assertRaisesRegex(ValueError, '겹칩니다'):
            self.app.planning.approve(self.pid, card['fingerprint'])
        self.assertFalse((self.root / 'SPEC.md').exists())
        self.assertEqual(self.app.planning.progress(self.pid)['confirmed_count'], 2)

    def test_http_checkpoint_more_and_start_prompt(self):
        server = self.server()
        route = f'projects/{self.pid}/'
        for i in range(10):
            self.add(f'항목 {i}')
        card = self.request(server, route + 'progress')
        self.assertTrue(card['show_summary'])
        card = self.request(server, route + 'summary-more', {'fingerprint': card['fingerprint']})
        self.assertFalse(card['show_summary'])
        self.assertFalse(self.request(server, route + 'progress')['show_summary'])
        session = Mock(closed=False, turn_id=None)
        import threading
        session.lock = threading.RLock()
        self.app.sessions[self.pid] = session
        result = self.request(server, route + 'message', {'text': '시작하자'})
        self.assertTrue(result['progress']['show_summary'])
        session.send_message.assert_not_called()
        card = self.request(server, route + 'summary-start', {'fingerprint': result['progress']['fingerprint']})
        self.assertEqual(card['spec_version'], 1)
        self.assertFalse(card['show_summary'])
        session.send_instruction.assert_called_once_with('production_start', version=1)
        self.assertIn('milestone', (self.root / '.harness/decisions.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
