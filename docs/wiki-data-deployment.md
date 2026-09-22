# 百科数据发布验收与 2026-09-15 恢复记录

SQL 命令、系统目录、配置参数、等待事件、函数百科的数据均独立于代码和建表迁移。
发布完成必须同时核验数据、版本覆盖、检索条目与公网页面。

## 发布检查

在仓库根目录执行只读检查：

```bash
psql -X -d pgweb -f tools/wiki/check_data.sql
psql -X 'service=pgweb.pg' -f tools/wiki/check_data.sql
```

[检查脚本](../tools/wiki/check_data.sql) 检查五个栏目：

- 数据表非空，PG 10–20 每个版本均有快照。
- 每条记录的 `present_in` 与实际快照版本一致。
- 有版本汇总表的栏目，每个版本的汇总计数与实际快照数一致。
- 检索条目的 URL 集合与数据逐条对应，没有缺项、重复或遗留条目。

任何一项失败都以非零状态退出；脚本在只读事务中执行，不修改数据库。
检查通过仍须访问公网索引、详情、版本变更页及搜索 API；HTTP 200 本身不足以证明数据已加载。

发布顺序：应用 `wiki` 迁移 → 按各栏目契约导入固定快照 → 重建对应索引 →
执行上述检查 → 按栏目契约重启 `pgsql.cc`、清除工作进程缓存 → 核验公网页面。
源快照在本地验证，生产通过现有 `tools/wiki/sync_*.py --input ... --target production --write`
导入。只执行 `migrate wiki` 不会导入百科数据。

四个本次涉及的索引可一起重建：

```bash
ssh pg 'cd /data/app/pgsql.cc && .venv/bin/python manage.py index_docs --catalog --waitevents --sqlcmd --func'
```

各栏目的来源和导入契约见
[SQL 命令](sqlcmd-column.md)、[系统目录](catalog-column.md)、
[等待事件](waitevent-column.md)、[函数百科](func-column.md)、
[配置参数](guc-column.md)。

## 2026-09-15 故障证据

用户发现四个公网页面显示零条记录。直接查询实际运行于
`/data/app/pgsql.cc` 的 Django 配置，确认其连接生产 `pgweb` 数据库；
Nginx 仍将 `pgsql.cc` 转发至 `127.0.0.1:8001`。

- 9 月 13 日的部署合并提交为 `4c0d87f4`，随后执行了
  `wiki.0002_catalog` 至 `0006_func` 的建表迁移。
- 恢复前 `wiki_catalog`、`wiki_waitevent`、`wiki_sqlcmd`、
  `wiki_func` 及对应三张版本表均为空；统计视图中插入、更新、删除计数均为零。
- 对应 `catalog / wait / sqlcmd / func` 检索条目也不存在。
- 同次新增的配置参数已导入 449 条、18 个版本，对应检索条目齐全。
- 本地四个栏目完整，保留了所有 PG 10–20 版本快照。

以上证据指向部署漏做这四类数据的导入和索引重建。数据库统计不是完整的操作审计日志；
这里不把统计结果当作对历史上所有数据库操作的证明。

## 恢复与结果

先备份生产七张表，在独立临时数据库实际恢复该备份，再加载并验证四份快照。
SQL 与函数使用与本地库逐字段一致的既有快照；系统目录与等待事件从现有本地库冻结为
同格式快照，保留每条记录原有的 `source_rev`。所有快照均通过原导入器验证和本地一致性检查。

生产经原同步工具逐个导入，没有使用 `--prune`；随后重建四类检索索引并重启 `pgsql.cc`。

| 栏目 | 生产记录 | 版本快照数 | PG 10–20 |
| --- | ---: | ---: | --- |
| SQL 命令 | 188 | 2,009 | 每版有数据 |
| 系统目录 | 158 | 2,184 | 每版有数据 |
| 等待事件 | 302 | 2,733 | 每版有数据 |
| 函数百科 | 708 | 9,618 | 每版有数据 |

快照数包含该栏目已收录的全部历史版本，不只 PG 10–20。
PG 19 保留测试版身份，PG 20 保留开发版身份；单个条目在某版新增或移除按真实快照呈现。

验收证据：

- 七张恢复表的全部业务字段指纹与本地一致（排除各端导入时间 `imported_at`）。
- 1,356 条对应检索条目齐全。
- 公网 96 项 HTTP/HTML 检查全部通过：4 个完整索引、44 个逐版本详情、
  44 个逐版本变更页、4 个搜索 API 查询。索引逐条检查了版本筛选标记；
  详情验证了实际选中的版本和内容，并非仅检查状态码。
- 生产 SQL 铁道图验证覆盖 188 条命令、2,009 份版本快照、5,015 张图，错误为零。
- 上述发布检查在本地和生产均通过；从备份还原的空表场景按预期以非零状态退出。
- 浏览器自动化工具连续超时，本次没有把 HTTP/HTML 检查记作浏览器点击验收。

本次完整证据与快照保留在：

- 本地：`tmp/wiki-recovery-20260915T153955Z/`
- 生产：`/data/app/pgsql.cc/tmp/wiki-recovery-20260915T153955Z/`

目录内 `production-before.dump` 为变更前备份，`snapshots.json` 记录快照校验和及逐版本数量，
`scratch-restore-validation.json` 记录恢复演练，
`public-verification.json` 记录公网检查，
`local-fingerprints.json` 与 `production-fingerprints.json` 记录两端内容指纹。

