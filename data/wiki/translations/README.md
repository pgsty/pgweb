# 新增百科中文快照

这套工具将 PG.CENTER 固定提交 `a709ab85` 的 18 个新增百科迁入 PGSQL.CC。原有 11 个中文栏目不在此次生成范围内。实体 slug、名称、版本集合、源码修订、目录属性、比较数据和原始英文证据保持不变；只替换用于展示的说明。

中文来源分为三类：

- 同一 PostgreSQL 大版本的本地中文手册。以稳定锚点或技术键定位语义节点，再核对结构、代码标识和数字，拒绝跨版本替换。每个实际使用的中文页面均单独记录内容 SHA-256 和匹配节点，不能把原英文页面的哈希标在中文译文上。
- `editorial_*.json`、`*.tsv` 中人工撰写的中文说明。键为完整原文，值为中文译文；源码注释、条件、限制和历史差异按原文保留。没有制造运行时测量结果。
- 现有 `pgweb.pgext.universe` 的中文扩展描述。仅在扩展 name 与固定英文描述同时匹配时使用 zh_desc，并记录扩展身份及描述快照哈希。扩展目录及能力证据仍保留原有观察日期和版本边界。

`technical_values.json` 记录经过检查后应保留的 SQL/函数签名、日期输入、正式名称和来源坐标。未翻译的实质正文必须进入 `fallback_fields`；手册摘录另用 `manual_language` 声明 `zh`、`mixed` 或 `en`。技术标识和源码证据本来就应维持原样，不能为了降低回退数量而改写。

每个版本的 `localization.original_text` 保留已替换展示字段的原文；`comparison_data` 和原比较哈希不参与翻译。英文手册证据链接改为同版本的 `https://pg.center/docs/...`，保留原 SHA；中文引用使用本地 `/docs/...`，带实际中文页哈希。`source_manifest.json` 记录固定源提交、输入快照、手册、扩展描述、词典及生成器的哈希。

## 生成

先在独立的忽略目录导出只读来源，再生成语义对齐及中文快照。命令只读数据库，不导入、不修改索引、不发布：

```sh
.venv/bin/python tools/wiki/localize_expansion.py \
  --source-root ../pg.center --source-commit a709ab85 \
  --bundle tmp/wiki-localization-20260930/manuals.json.gz --export-sources
.venv/bin/python tools/wiki/localize_expansion.py --align
.venv/bin/python tools/wiki/localize_expansion.py --build
.venv/bin/python -m unittest tools.wiki.test_localize_expansion
```

固定导出的 `manuals.json.gz` 与 `alignment.json.gz` 是可复用构建输入。重复生成前不要重新导出；输入手册或词典有意变更时，应重新核对差异和来源。gzip 时间戳固定为零，JSON 键排序；相同固定输入和工具产生相同字节。

`report.json` 汇总实体、版本、翻译字段及正文回退计数。完整回退原文与位置另写入构建目录 `fallbacks.json`，供人工逐项核对。数据库导入、页面和搜索验收、备份及部署是独立步骤，由正式发布流程执行。
