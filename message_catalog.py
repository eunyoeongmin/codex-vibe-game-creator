"""Stable message keys shared by Python, the browser and exported runtimes."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / 'messages/catalog.json').read_text(encoding='utf-8'))
SOURCE_KEYS = {entry['source']: key for key, entry in CATALOG.items()}


class Message(str):
    def __new__(cls, key, values=()):
        instance = super().__new__(cls, _format(CATALOG[key]['source'], values))
        instance.key, instance.values = key, values
        return instance


def _format(value, values):
    return re.sub(r'\{(\d+)\}', lambda match: str(values[int(match[1])])
                  if int(match[1]) < len(values) else match[0], value)


def text(key, *values):
    """Return source wording, retaining its key for HTTP error translation."""
    return Message(key, values)


def translate(value, language='ko', *values):
    key = value.key if isinstance(value, Message) else SOURCE_KEYS.get(value, value)
    if isinstance(value, Message) and not values:
        values = value.values
    entry = CATALOG.get(key)
    return _format(entry.get(language, entry['source']) if entry else value, values)


def error_payload(error):
    value = error.args[0] if error.args else str(error)
    result = {'error': str(error)}
    if isinstance(value, Message):
        result.update(message_key=value.key, message_args=[str(v) for v in value.values])
    return result


def browser_catalog(keys=None):
    entries = CATALOG if keys is None else {key: CATALOG[key] for key in keys}
    return 'globalThis.HarnessMessages=Object.assign(globalThis.HarnessMessages||{},' + json.dumps(entries, ensure_ascii=False) + ');\n'


def bundle_runtime(source):
    """Export only messages used by this runtime, without a server dependency."""
    keys = set(re.findall(r'HarnessText\.(?:raw|text)\([\'\"]([^\'\"]+)', source))
    helper = ROOT / 'messages.js'
    if not helper.is_file():
        helper = ROOT / 'web/messages.js'
    return "'use strict';\n" + browser_catalog(sorted(keys)) + helper.read_text(encoding='utf-8') + '\n' + source
