# 数据类型百科

`/wiki/type/` 按版本、分类和名称筛选；`/wiki/type/<slug>/?v=<major>` 展示类型定义、别名、源码 `pg_type` 属性、显式类型转换、运算符重载、操作符类与范围定义，并可用 `from` 比较两份已收录样本。稳定身份仍用 `pg_catalog` 名称；`bpchar` 对应 SQL `character`，内部 `"char"` 与之分开。

数据通过固定本地化快照和共享 `wiki_import_topics` 导入。核心源码事实与中文说明分开保留，原始英文手册 URL 指向 PG.CENTER，原始哈希不附到中文页面上；`snapshot.localization.sources` 单独记录实际中文来源与页面哈希。缺少核验译文时显示英文回退提示。`manual_language` 决定手册区块的语言标记；绝对来源 URL 不得被错误拼成本站 `/docs/.../https://...` 路径。手册 HTML 使用现有允许列表清理主动内容。

源码样本覆盖 PostgreSQL 10–20，不由缺少早期样本推断类型不存在。系统目录值是源码初始化声明，不标成运行时实测；空 `pg_cast` 或 `pg_opclass` 列表也不等于不能转换或使用索引。比较使用快照中的结构化语义字段；说明正文和来源指纹不作为系统目录变化。

页面使用中文 Wiki 公共外壳与原生 CSS，无英文导航和 Tailwind 依赖。关联对象链接使用稳定运算符签名及操作符类身份。筛选、版本选择和 JSON 导出保留参数。

```sh
.venv/bin/python manage.py test pgweb.wiki.test_specialized_readers --noinput
```
