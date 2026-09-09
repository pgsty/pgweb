"""Deterministic mixed Chinese/English indexing; the same pipeline serves queries."""
import logging
import re
from functools import lru_cache

import jieba

jieba.setLogLevel(logging.WARNING)

PG_TERMS = ('共享缓冲区', '缓冲区', '逻辑复制', '物理复制', '复制槽', '预写日志', '检查点', '表空间',
            '物化视图', '外部表', '外键', '主键', '唯一约束', '唯一性约束', '访问方法', '执行计划',
            '窗口函数', '聚合函数', '操作符', '运算符', '行级安全', '多版本并发控制', '事务隔离',
            '序列化', '可串行化', '死锁', '分区表', '索引扫描', '连接池', '热备', '归档', '排序',
            '全文检索', '全文搜索', '哈希表', '数据类型', '系统目录', '系统视图')
TOKEN = re.compile(r'[\u3400-\u9fff]+|[A-Za-z_][A-Za-z_0-9.]*|[0-9]+')
STOP = frozenset(('的', '了', '是', '在', '和', '与', '或', '一个', '可以', '如何', '怎么', '什么',
                  '怎样', '为什么', '请问', '我', '你', '它', 'the', 'a', 'an', 'of', 'to', 'is', 'and'))


@lru_cache(maxsize=1)
def tokenizer():
    segmenter = jieba.Tokenizer()
    segmenter.initialize()
    for term in PG_TERMS:
        segmenter.add_word(term, freq=100000)
    return segmenter


def words(text, query=False):
    result = []
    for match in TOKEN.finditer(text):
        word = match.group()
        if '\u3400' <= word[0] <= '\u9fff':
            tokens = tokenizer().cut_for_search(word, HMM=False) if not query else tokenizer().cut(word, HMM=False)
        else:
            tokens = [word.casefold()]
        result.extend(t for t in tokens if t not in STOP and t.strip())
    return result


def index_text(text):
    return ' '.join(words(text))


def query_text(text):
    # Query punctuation never becomes PostgreSQL's tsquery syntax.
    return ' '.join(words(text, query=True))
