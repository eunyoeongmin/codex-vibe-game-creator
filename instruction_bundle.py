"""Load one immutable set of dashboard instructions for a connection."""
import hashlib
from pathlib import Path
import tomllib

SOURCE = Path(__file__).resolve().parent / 'instructions/dashboard.toml'
SECTIONS = ('host', 'startup', 'question_tool', 'planning_more', 'production_start', 'asset_request')


class InstructionBundle:
    def __init__(self, path=SOURCE):
        self.path = Path(path).resolve()
        raw = self.path.read_bytes()
        data = tomllib.loads(raw.decode('utf-8'))
        if not isinstance(data.get('version'), int) or data['version'] < 1:
            raise ValueError('지침 파일의 version은 양의 정수여야 합니다.')
        self.prompts = data.get('prompts', {})
        for section in SECTIONS:
            if not isinstance(self.prompts.get(section), str) or not self.prompts[section].strip():
                raise ValueError(f'지침 파일에 {section} 본문이 필요합니다.')
        self.source = {'path': str(self.path), 'version': data['version'],
                       'sha256': hashlib.sha256(raw).hexdigest()}

    def render(self, section, **values):
        values.setdefault('language', 'Korean')
        return self.prompts[section].format(**values)

    def trace(self, section, text):
        return {**self.source, 'section': section, 'text': text,
                'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
