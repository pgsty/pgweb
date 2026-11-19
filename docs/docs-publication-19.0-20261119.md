# PostgreSQL 19.0 中文手册正式发布（2026-11-19）

PGSQL.CC 本地与生产已发布 PostgreSQL 19.0 中文手册、A4/US PDF，并更新版本比较与对应搜索索引。`/docs/19/` 和 `/docs/current/` 均提供正式译文，RC2 提示已消失。

- [中文手册](https://pgsql.cc/docs/19/index.html)
- [A4 PDF](https://pgsql.cc/files/documentation/pdf/19/postgresql-19-A4.pdf) · [US PDF](https://pgsql.cc/files/documentation/pdf/19/postgresql-19-US.pdf)
- [中文发行说明](https://pgsql.cc/docs/release/19.0/) · [版本比较](https://pgsql.cc/docs/compare/?release=19.0)

## 来源与最终审阅

源更新提交为 pgdoc `b04ebc03e0c08b0922738836c7e574bde6a568f3`。最终自检重新比较 478 个英文源文件，覆盖 RC2 → 19.0 六个文件的全部 75 个原始差异块，并复核术语、限定条件、代码、链接、锚点、日期和新增致谢者；无需进一步改译。此结论针对本次增量，不代表全书重新审校。翻译、构建和既有检查器差异见 [pgdoc 更新记录](https://github.com/pgsty/pgdoc/blob/main/docs/sync-19.0-20261119.md)。

冻结制品为本机 `../pgdoc/tmp/release-19.0-final-20261119.tar.gz`，64,489,515 字节，SHA-256：

```text
be427be2f7a2ee8ea853b9a3f6835702a6d7b357c90b93c07b5624f5a350dc54
```

包内保存实际构建使用的中英文源码、规则、工具、HTML、中文 PDF、来源清单和校验记录，包含保留的工作区人工修改；不能仅凭上述 Git 提交重现全部输入。实际中文源文件清单指纹为 `2bcba97e65d998359c05df6a33c92a0cfee8c8aed1aaa4ceca6d8b13472a877c`。封存包保持原样，本记录补记其后的公开发布。

## 备份、恢复验证与导入

两端均在发布前建立完整 custom-format 数据备份，并实际恢复到隔离数据库；逐表行数及内容指纹、版本元数据、PG19 页面身份和正文摘要均与各自备份快照一致。

| 目标 | 恢复数据库 | 表数 | 行数 |
| --- | --- | ---: | ---: |
| 本地 | `test_pgweb_docs19_final_local` | 139 | 620,348 |
| 生产 | `test_pgweb_docs19_final_prod` | 139 | 620,372 |

随后在这两个隔离库演练完整手册导入和版本比较转正，再应用到各自的 `pgweb` 库。导入包装器复用原生 `tools/docs/docload.py`，检查完整文件集合、目标数据库、基线指纹和页面 ID，并使用串行化事务与事务级咨询锁。

- 两端均导入 1,155 个 HTML 页面和 5 个 SVG；更新 1,154 行，新增、删除均为 0，1,160 个页面 ID 全部保留。
- 入库后逐页比较冻结 HTML 与数据库正文的可见文本、全部原始锚点和 4,214 个代码／语法块；5 个 SVG 逐字节一致。
- 原生 Tidy 将 `indexes-types.html` 五个运算符列表中的不换行空格转为普通空格，字符和间距数量不变，已逐块记录。其余代码块按原始文本比较（仅忽略首尾换行），未发现差异。
- 两端 Tidy 序列化不同，数据库 HTML 摘要不要求跨端相等；各端均与自己的隔离演练和发布回执一致，正文、锚点及代码另按同一冻结源核验。

版本比较从目标自身最新完整快照生成，只将 `19.0` 从 `preview / 19rc2` 转为 `stable / 19.0`，日期为 `2026-11-19`。200 条有效事项（22 条迁移、178 条变更）的规范正文、提交与 CVE 一致；204 个已存 occurrence ID（含 4 条退役记录）、patch ID 和其他 357 份发布载荷保留。原生导入器先回滚预演再写入，未使用仓库中落后的 beta4 快照。

## PDF 与公开验收

两端原子替换 PDF，保留旧文件与来源回执；随后从公网完整下载两份 PDF，字节数和 SHA-256 与冻结产物一致。

| 纸型 | 页数 | 字节数 | SHA-256 |
| --- | ---: | ---: | --- |
| A4 | 3,046 | 18,107,689 | `9296268c9ae7e083d288ba7da3c4355608f9c9ad42f1a075ee0c4229765859e7` |
| US | 3,248 | 18,147,135 | `87b6371b142b784adb9f7b901fa40e4ffe7912c80447b36cbdaa089aea0d68b5` |

两端 PG19 文档检索均重建 7,644 条，提取 1,152 页、跳过 1 页未变内容；版本发布索引为 31 条。站内全文搜索各定向处理 2,314 个 URL，更新 2,299 个、新增 15 个、删除 0 个，覆盖全部 PG19/current HTML 及相关发布入口。`webpages` 两个索引均有效，已执行 `ANALYZE webpages`。

本地与公网分别通过 14 项 HTTP／正文／文档检索检查，覆盖六个变更文件、正式版首页、current、发行说明、版本比较和版本百科入口。另分别通过四项站内搜索检查：`BGWORKER_INTERRUPTIBLE` 与 `reject_limit` 在 `19` 和 `current` 范围均命中对应正文。站点将当前大版本搜索范围规范化为 `/docs/current/`，数据库原始两组路径也分别核验命中。

浏览器实看公网 PL/Python 共享数据页，确认新 `SD`/`GD` 说明、正式版入口及正常布局。构建阶段的 23 个 PDF 页和桌面／窄屏 HTML 抽查，以及既有 FOP 提示，见 pgdoc 更新记录。

## 应用部署与范围

部署提交为 `be8e86d30b2aa8a791b3a5f3e0800df218864068`：移除发布 YAML 中临时指向上游的 `notes_url`，同步已有测试断言，正式发行说明入口改用中文手册。25 项相关测试通过。生产 `/data/app/pgsql.cc` 快进到该提交，只重启 `pgsql.cc`；部署后中文、英文站服务均为 active。后续记录更新不改变此运行代码版本。

本批完成手册、PDF、PG19 版本比较和相应索引。百科中的系统目录、GUC、等待事件、SQLSTATE、钩子等固定来源仍需按各自流程校准，现有 beta/RC 采样事实未改标为 GA；PG20 固定快照未刷新。PG.CENTER 的双语手册本批未发布：官方下载的英文 A4/US PDF 仍声明为 19rc2，尚未通过 19.0 来源检查。

本地 `data/info/2026-11-02.json` 原有修改保留，SHA-256 仍为 `286f0397c4d91cceff2f8f8fe1f2bd1122f18f260a4df9a1a7ac0d23f08b1a0e`。

## 证据与回退

- 本地证据目录：`tmp/docs-19.0-20261119/`；有效全库备份和旧 PDF 在 `local-verified/`，发布前后比较快照在 `local-release-published/`。
- 生产证据目录：`/tmp/pgweb-docs19-final-20261119/`；全库备份、DDL 和旧 PDF 在 `production/`，比较快照在 `production-release-published/`。轻量发布回执另取回本地 `production-receipts/`。
- 本地备份 SHA-256：`b6254553a814ef68cbb9bf27bdf60da333b1e0841ba248126913511f3f658a87`；生产备份 SHA-256：`538cc63b4eb195ba330416d2f5c5b7aae8dade457fa203bfa5795d18a45790d7`。
- `*-storage-verify.json`、`*-search-verify.json`、`*-site-index.json`、`public-http.json`、`public-pdfs.json` 及部署／测试日志保留实际验收结果；大文件、数据库备份与生成制品均被 Git 忽略。

回退时先核对发布后的并行变更，从各目标自身备份或已恢复的隔离库提取 PG19 手册与比较记录，在事务内按原 ID 恢复所需范围；不得直接用全库备份覆盖线上后续内容。恢复相应旧 PDF 后重建受影响索引、清理页面缓存并再次验收。源快照、旧制品和隔离恢复库均保留。
