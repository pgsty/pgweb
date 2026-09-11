"""等待事件栏目里导入与页面共用的两件小事：身份归一、快照比较。

规则只写这一份：导入用它把各版本的 (类型, 名称) 认成同一个事件、算相邻版本的变化记录，
页面用它做 ?from= 任意两版比较，两边口径一致。契约见 docs/waitevent-column.md §2。
"""

import re

from .models import WAITEVENT_TYPE_ORDER

# 手册里出现过、但不是规范类型的标签 → 规范类型。9.6 把轻量级锁分成具名锁与 tranche 两类，
# 10 起合并为 LWLock；BufferPin 在 19 改叫 Buffer。
CANONICAL_TYPE = {'LWLockNamed': 'LWLock', 'LWLockTranche': 'LWLock', 'BufferPin': 'Buffer'}
NON_ALNUM = re.compile(r'[^a-z0-9]+')


def canonical_type(label):
    return CANONICAL_TYPE.get(label or '', label or '')


def is_canonical_type(label):
    return label in WAITEVENT_TYPE_ORDER


def canonical_name(type_label, name):
    """小写并去掉非字母数字；轻量级锁再去掉结尾的 lock：
    WALWriteLock（≤ 12）与 WALWrite（13 起）、buffer_content 与 BufferContent 都对得上。"""
    stem = NON_ALNUM.sub('', (name or '').lower())
    if canonical_type(type_label) == 'LWLock' and stem.endswith('lock') and len(stem) > 4:
        stem = stem[:-4]
    return stem


def identity(type_label, name, canonical_map=None):
    """身份 key：'lwlock/buffermapping'。

    `canonical_map` 是图谱的 'Type/Name' → 'Type/Name'（拼写更名与类型迁移），先按原始
    标签查一次，再按规范类型查一次（图谱的键用的是它自己那一版的类型标签）。
    """
    pair = '{}/{}'.format(type_label, name)
    if canonical_map:
        # 沿着映射走到底：12 的 buffer_io → 13 的 LWLock/BufferIO → 14 起的 IPC/BufferIO。
        for _ in range(4):
            type_label, _, name = pair.partition('/')
            ctype = canonical_type(type_label)
            target = canonical_map.get(pair) or (
                canonical_map.get('{}/{}'.format(ctype, name)) if ctype != type_label else None)
            if not target or target == pair:
                break
            pair = target
    type_label, _, name = pair.partition('/')
    ctype = canonical_type(type_label)
    return '{}/{}'.format(ctype.lower(), canonical_name(ctype, name))


def normal_text(text):
    """比较英文描述时忽略空白与末尾句号：16 → 17 整批去句号不算措辞变化。"""
    return ' '.join((text or '').split()).rstrip('.。 ').strip()


def compare_snapshots(left, right, from_major, to_major):
    """两份版本快照之间的变化记录；两边都没有、或没有任何变化时返回 None。

    快照形状见契约 §3：{type, name, description, description_zh, ...}。
    变化只看三样：名称（更名）、类型标签（类型变动）、英文描述（措辞更新；两侧都有
    英文且归一后仍不同才算）。中文译文的变化不算变化。
    """
    left, right = left or {}, right or {}
    if not left and not right:
        return None
    record = {'from': from_major, 'to': to_major, 'renamed': None, 'moved': None, 'reworded': None}
    if not left:
        return dict(record, status='added')
    if not right:
        return dict(record, status='removed')
    record['status'] = 'changed'
    if (left.get('name') or '') != (right.get('name') or ''):
        record['renamed'] = {'from': left.get('name', ''), 'to': right.get('name', '')}
    if (left.get('type') or '') != (right.get('type') or ''):
        record['moved'] = {'from': left.get('type', ''), 'to': right.get('type', '')}
    before, after = left.get('description') or '', right.get('description') or ''
    if before and after and normal_text(before) != normal_text(after):
        record['reworded'] = {'from': before, 'to': after}
    if not (record['renamed'] or record['moved'] or record['reworded']):
        return None
    return record


def position_of(type_label, rank):
    """索引顺序：类型序 × 1000 + 类型内按名的序号。"""
    return WAITEVENT_TYPE_ORDER.get(canonical_type(type_label), len(WAITEVENT_TYPE_ORDER)) * 1000 + rank
