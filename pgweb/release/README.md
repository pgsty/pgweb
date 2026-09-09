# pgsql.cc 发布数据流程

首页、Beta 页面和发布摘要由 `data/releases/` 中日期最新的 `.yaml` 文件驱动。
文件名必须使用 `YYYY-MM-DD.yaml`，其中的新闻 `id` 必须指向 pgsql.cc 本地数据库中的
中文发布公告，而不是上游 postgresql.org 数据库的主键。

## 安全默认值

本地化站点默认设置 `RELEASE_AUTO_PROCESS = False`。因此，普通的
`manage.py migrate` 只更新数据库结构，不会批准新闻、修改版本、置顶文章或发送邮件。
审核发布 YAML 和本地新闻主键后，可先演练，再显式执行：

```console
python manage.py process_release --dry-run
python manage.py process_release
```

默认不发送公告邮件；只有明确需要时才使用 `--send-email`。

## 准备步骤

1. 在需要时创建新闻禁发时段。
2. 导入并完成中文发布公告，记录本地新闻主键。
3. 创建 `data/releases/<date>.yaml`，填写本地新闻主键。
4. 若为首个 Alpha、Beta 或 RC，先创建对应的 `Version` 记录。
5. 检查首页与 Beta 页面预览，再显式执行发布处理。

## 版本组合规则

- 主版本或首个 Alpha/Beta/RC 通常只列一个版本，用于生成完整发布摘要。
- 列出多个版本时统一按小版本组合发布处理。
- 主版本摘要应写入 `announcetext_zh`，避免把上游英文正文直接显示在中文首页。

## 显式发布处理会执行的操作

- 将 `Version` 的发布日期和最新小版本调整为 YAML 中的值。
- 在测试版本转正式主版本时更新 `testing`、`supported` 和 `current` 状态。
- 将 YAML 中列出的 CVE 设为公开并关联本地中文新闻。
- 批准发布公告并将其置顶。
- 仅在 `RELEASE_SEND_ANNOUNCEMENT_EMAIL = True` 时发送公告邮件。
