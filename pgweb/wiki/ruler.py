"""索引表「版本变动」那一列的横向刻度尺，以及版本号的配色，三个栏目共用。

每个大版本一格，格子下面都写出版本号——隔一个写一个读者得数格子，不如全写。
9.x 那七个版本比两位数长，把点号单独缩小（`9` · `0`），占位就和两位数差不多。

版本号的颜色按支持状态分四档：已停止维护、仍在支持、测试版、开发版。索引页的
版本导航条与刻度尺用同一套，读者扫一眼就知道哪些版本还值得关心。
"""

# `support_status` → 色调后缀；拿不到时退回按 `status` 判断。
TONES = {'supported': 'live', 'end-of-life': 'eol', 'preview': 'beta', 'devel': 'dev'}
TONE_LABEL = {'eol': '已停止维护', 'live': '仍在支持', 'beta': '测试版', 'dev': '开发版'}


def tone_of(version):
    tone = TONES.get(version.get('support_status') or '')
    if tone:
        return tone
    status = version.get('status') or ''
    return TONES.get(status, 'eol' if status == 'historical' else 'live')


def mark_ticks(versions):
    """给每个版本补上刻度尺要用的三个字段，原地改并把列表返回。

    `tick_head` / `tick_tail`：`9.0` 拆成 `9` 与 `0`，模板在中间放一个小号点号；
    两位数版本 `tick_tail` 为空。`tone`：eol | live | beta | dev。
    """
    for version in versions:
        head, _, tail = version['major'].partition('.')
        version['tick_head'] = head
        version['tick_tail'] = tail
        version['tone'] = tone_of(version)
        version['tone_label'] = TONE_LABEL[version['tone']]
    return versions
