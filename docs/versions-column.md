# 版本发布百科

`/wiki/versions/` 与 `/wiki/versions/<branch>/` 复用本站已有的 `core_version`、手册、中文发布比较库和安全矩阵，不新增业务表或数据副本。大版本身份保留字符串，`9.6` 不会截成 `9`；开发版 `tree=0` 映射到配置的开发大版本，手册路径仍为 `/docs/devel/`。

发布正文只读取已激活的 `releases:zh`，安全事实读取 `security`。加载器核验清单与修订，缺失时返回 503，不回退到文件或英文发布库。初版功能、每次维护发布及迁移正文保持原始 occurrence 身份；安全矩阵的明确分支事实与发布说明中的 CVE 提及分开呈现。

手册页数、索引文件与版本范围实时来自中文站本地数据库，不固定采用英文站的数量。2026-09-30 只读核验为 31 个分支、31 个手册入口、352 个非占位发布。PDF 只链接本地存在且非空的 A4/US 文件；本站没有可据以断言全部历史 PDF 语言的统一清单，因此页面明确保留语言不确定性。预览、开发版不把暂定日期显示为正式生命周期。

索引支持 `q`、`state`、`format=json`；详情支持 `q`、`kind`、`format=json`。导出保留当前筛选。`/wiki/versions/devel/` 带参数永久跳转到开发大版本身份。`collection_summary()` 从版本表读取首页卡片计数，不加载发布正文；`version_search.rebuild_versions()` 由共享索引命令调用。

维护现有来源仍遵循 [版本比较存储](version-compare-storage.md)，本阅读器没有独立发布流程。测试：

```sh
.venv/bin/python manage.py test pgweb.wiki.test_versions_encyclopedia --noinput
```
