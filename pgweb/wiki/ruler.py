"""索引表「版本变动」那一列的横向刻度尺，三个栏目共用。

一版一格，格子只有 12 像素宽，版本号横排挨个写必然糊成一团；这里挑出要写出
版本号的那几格，其余留白，靠格子自己的 title 补齐。取舍：隔一格写一个，最新
那版一定写得出来——读者看这张表最先要找的就是它。
"""


def mark_ticks(versions):
    """给每个版本加上 `tick`：为真的在表头写出版本号。原地改，并把列表返回。"""
    last = len(versions) - 1
    ticks = set(range(0, last + 1, 2))
    if last >= 0 and last not in ticks:
        # 末版落在双数位之外时把它补上，免得刻度尺在最右边断掉；
        # 补完与前一个相邻，就让前一个让位，两个版本号不会挤在一起。
        ticks.add(last)
        ticks.discard(last - 1)
    for index, version in enumerate(versions):
        version['tick'] = index in ticks
    return versions
