"""配置参数栏目里导入与页面共用的两件小事：快照逐字段比较、默认值的人类可读形式。

比较规则只写这一份：导入用它算变化记录，页面用它做 ?from= 任意两版比较，两边口径一致。
"""

import decimal

from .models import GUC_DEFAULT_FIELDS, GUC_FIELDS, GUC_SUBSTANTIVE_FIELDS


def normal(value):
    """None、'' 与 [] 视为同一个空：老版本 pg_settings 把无单位存成 ''，新版本存 null。"""
    if value is None or value == '' or value == []:
        return None
    return value


def diff_fields(left, right):
    """两份快照之间变了的字段 → {field: {'from', 'to'}}，字段限 GUC_FIELDS，原值原样保留。"""
    left, right = left or {}, right or {}
    out = {}
    for field, _ in GUC_FIELDS:
        if normal(left.get(field)) != normal(right.get(field)):
            out[field] = {'from': left.get(field), 'to': right.get(field)}
    return out


def is_substantive(fields):
    return any(field in fields for field in GUC_SUBSTANTIVE_FIELDS)


def is_default_change(fields):
    return any(field in fields for field in GUC_DEFAULT_FIELDS)


# ---------------------------------------------------------------- 人类可读默认值

MEMORY_UNITS = {
    'B': decimal.Decimal(1), 'kB': decimal.Decimal(1024), 'MB': decimal.Decimal(1024) ** 2,
    'GB': decimal.Decimal(1024) ** 3, 'TB': decimal.Decimal(1024) ** 4,
    '8kB': decimal.Decimal(8192), '16kB': decimal.Decimal(16384), '32kB': decimal.Decimal(32768),
    '64kB': decimal.Decimal(65536), '16MB': decimal.Decimal(16) * decimal.Decimal(1024) ** 2,
}
BLOCK_UNITS = ('8kB', '16kB', '32kB', '64kB', '16MB')
MEMORY_LABELS = (('TiB', decimal.Decimal(1024) ** 4), ('GiB', decimal.Decimal(1024) ** 3),
                 ('MiB', decimal.Decimal(1024) ** 2), ('KiB', decimal.Decimal(1024)))
TIME_UNITS = {'us': decimal.Decimal('0.000001'), 'ms': decimal.Decimal('0.001'), 's': decimal.Decimal(1),
              'min': decimal.Decimal(60), 'h': decimal.Decimal(3600), 'd': decimal.Decimal(86400)}
TIME_LABELS = (('d', decimal.Decimal(86400)), ('h', decimal.Decimal(3600)), ('min', decimal.Decimal(60)),
               ('s', decimal.Decimal(1)), ('ms', decimal.Decimal('0.001')), ('us', decimal.Decimal('0.000001')))


def compact(value):
    return format(value.normalize(), 'f')


def human_value(raw, unit):
    """默认值的可读形式，与 guc.pg.center 同一规则：原值与单位仍是权威，这只是展示。

    无单位原样；内存单位换算成整数的 KiB/MiB/GiB，块单位再附 `(raw × unit)`；
    时间单位换算成整数的秒/分/时/天。换不成整数的保持原样加单位。
    """
    if raw is None:
        return '未设置'
    if raw == '':
        return '空字符串'
    if not unit:
        return str(raw)
    try:
        value = decimal.Decimal(str(raw))
    except decimal.InvalidOperation:
        return '{} {}'.format(raw, unit)
    if value < 0:
        return '{} {}'.format(raw, unit)
    if unit in MEMORY_UNITS:
        total = value * MEMORY_UNITS[unit]
        label, shown = 'B', total
        for candidate_label, factor in MEMORY_LABELS:
            candidate = total / factor
            if candidate >= 1 and candidate == candidate.to_integral_value():
                label, shown = candidate_label, candidate
                break
        rendered = '{} {}'.format(compact(shown), label)
        if unit in BLOCK_UNITS:
            rendered += ' ({} × {})'.format(raw, unit)
        return rendered
    if unit in TIME_UNITS:
        seconds = value * TIME_UNITS[unit]
        for label, factor in TIME_LABELS:
            candidate = seconds / factor
            if candidate >= 1 and candidate == candidate.to_integral_value():
                return '{} {}'.format(compact(candidate), label)
    return '{} {}'.format(raw, unit)
