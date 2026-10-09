"""Dashboard language selection; wording lives in messages/catalog.json."""
from message_catalog import CATALOG, text, translate

LANGUAGES = {'ko': 'Korean', 'en': 'English', 'ja': 'Japanese',
             'zh-Hans': 'Simplified Chinese', 'zh-Hant': 'Traditional Chinese'}


def valid_language(value):
    if value not in LANGUAGES:
        raise ValueError(text('language.unsupported'))
    return value
