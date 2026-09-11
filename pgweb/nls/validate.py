"""Checks a translation must pass before it is stored, and the stricter set
before it is approved. Mirrors pgnls `workbench/importer.validate_candidate`:
an approved translation is compiled with GNU msgfmt in an isolated PO fixture."""

import os
import re
import shutil
import subprocess
import tempfile

MAX_FORM = 32767
MAX_NOTE = 20000
TOKEN = re.compile(r"%(?:\d+\$)?[-+#0 ']*(?:\*|\d+)?(?:\.(?:\*|\d+))?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspnm%]")
_HEADER = ('Project-Id-Version: candidate-validation-only\n'
           'Report-Msgid-Bugs-To: \nPOT-Creation-Date: 2026-09-09 00:00+0000\n'
           'PO-Revision-Date: 2026-09-09 00:00+0000\n'
           'Last-Translator: isolated validation fixture\nLanguage-Team: isolated validation fixture\n'
           'Language: zh_CN\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\n'
           'Content-Transfer-Encoding: 8bit\nPlural-Forms: {plural}\n')


class ValidationError(ValueError):
    pass


def quote(text):
    return '"' + (text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                  .replace('\t', '\\t').replace('\r', '\\r')) + '"'


def candidate_po(message, forms):
    plural = message.plural_forms.strip() if message.msgid_plural else ''
    out = ['msgid ""', 'msgstr ' + quote(_HEADER.format(plural=plural or 'nplurals=1; plural=0;')), '']
    flags = [f for f in message.flags if f != 'fuzzy']
    if flags:
        out.append('#, ' + ', '.join(flags))
    if message.msgctxt is not None:
        out.append('msgctxt ' + quote(message.msgctxt))
    out.append('msgid ' + quote(message.msgid))
    if message.msgid_plural:
        out.append('msgid_plural ' + quote(message.msgid_plural))
        for key in sorted(forms, key=int):
            out.append('msgstr[{}] {}'.format(int(key), quote(forms[key])))
    else:
        out.append('msgstr ' + quote(forms['']))
    return '\n'.join(out) + '\n'


def placeholders(text):
    return sorted(re.sub(r'^%\d+\$', '%', t) for t in TOKEN.findall(text or '') if t != '%%')


def check_forms(message, forms):
    """Shape and size checks that every save must pass."""
    if not isinstance(forms, dict) or set(forms) != set(message.suggested_forms):
        raise ValidationError('必须同时保存此消息的全部译文形式。')
    for value in forms.values():
        if not isinstance(value, str) or len(value) > MAX_FORM:
            raise ValidationError('译文不是文本或长度超限。')
        if '\0' in value:
            raise ValidationError('译文不能包含 NUL 字符。')


def _boundary(value):
    return (re.match(r'^[ \t\r\n\v\f]*', value)[0], re.search(r'[ \t\r\n\v\f]*$', value)[0])


def check_approval(message, forms, msgfmt='msgfmt'):
    """The stricter checks an approved translation must pass. Raises ValidationError."""
    for key, text in forms.items():
        if not text:
            raise ValidationError('已校对的译文各形式都不能为空。')
        source = message.msgid if key in ('', '0') else message.msgid_plural
        if _boundary(source) != _boundary(text) or any(source.count(c) != text.count(c) for c in '\n\r\t'):
            raise ValidationError('首尾空白以及换行、制表符的数量必须与英文原文一致。')
    binary = shutil.which(msgfmt)
    if binary is None:
        # Fall back to a placeholder multiset comparison when gettext is not installed.
        for key, text in forms.items():
            source = message.msgid if key in ('', '0') else message.msgid_plural
            if 'c-format' in message.flags and placeholders(source) != placeholders(text):
                raise ValidationError('格式占位符与英文原文不一致（服务器缺少 msgfmt，仅比较占位符）。')
        return 'placeholders'
    with tempfile.TemporaryDirectory(prefix='pgweb-nls-') as folder:
        path = os.path.join(folder, 'candidate.po')
        with open(path, 'w', encoding='utf-8') as stream:
            stream.write(candidate_po(message, forms))
        result = subprocess.run([binary, '--check', '--check-format', '-o', os.devnull, path],
                                capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'), timeout=30)
    if result.returncode != 0:
        raise ValidationError('msgfmt 校验未通过：' +
                              result.stderr.replace(path, '<candidate.po>').strip())
    return 'msgfmt'
