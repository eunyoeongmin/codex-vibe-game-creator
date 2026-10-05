"""Dashboard UI catalog shared by HTTP responses and generated SPEC headings."""
import json
from pathlib import Path

LANGUAGES = {'ko': 'Korean', 'en': 'English', 'ja': 'Japanese',
             'zh-Hans': 'Simplified Chinese', 'zh-Hant': 'Traditional Chinese'}
CATALOG = json.loads((Path(__file__).parent / 'web/locales.json').read_text(encoding='utf-8'))


def valid_language(value):
    if value not in LANGUAGES:
        raise ValueError('Unsupported language.')
    return value


def translate(text, language='ko', *values):
    result = CATALOG.get(text, {}).get(language, text)
    # Substitute only numbered placeholders, preserving arbitrary braces in errors.
    import re
    return re.sub(r'\{(\d+)\}', lambda m: str(values[int(m[1])])
                  if int(m[1]) < len(values) else m[0], result)
