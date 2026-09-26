# 开发者档案采集

```bash
.venv/bin/python tools/hacker/collect.py
.venv/bin/python tools/hacker/enrich_avatars.py \
  --input tmp/hacker/<run>/profiles.json \
  --output tmp/hacker/<run>/profiles-avatars.json
```

`collect.py` 每次创建独立 UTC 时间目录。用 `--output tmp/hacker/<run>` 可恢复中断批次，成功的原始响应按 URL 和 SHA-256 校验后复用，不重新下载覆盖。列表总数、唯一 ID 和实采人数必须相等。网络并发默认为 3，最多为 4；失败请求有限次重试。

来源为 PGNexus 列表页使用的公开 `/api/contributors/profiles` 接口、所有列出档案的 `/c/` 或 `/u/` 详情，以及详情组件使用的 `/api/profile/` 分页接口。原始 HTML、React Flight、列表/API JSON、头像及内容卡片图片保留在 `raw/`，每个 HTTP 成功响应旁有 `.meta.json`（请求/最终 URL、时间、状态、内容类型、长度、SHA-256），全目录校验在 `manifest.json`。`parsed/` 为可重建中间产物。目录外的网页不递归抓取。

详情中的讨论、补丁、提及、推荐文章、知识文章、公开 Sandbox 与评价全部分页采集；`initialItems` 保留首屏原值，`items` 保存全量，`responses` 保留分页响应。`DiscussionPeers` 与 `RelatedContributors` 单独保留，不计入本人贡献。Flight 的长文本按 UTF-8 字节长度解码，日期解为 ISO 字符串；源原文仍可在原始 HTML/Flight 查验。

头像保留原字节，并生成最大 512 × 512 的 WebP 供本站使用。LinkedIn 通用占位 SVG 保留为原始素材，不当作人物肖像；过期、删除或不可访问的头像记录具体失败。`enrich_avatars.py` 只从已核实同一身份的公开专业档案补充损坏头像，保留图片和页面来源，并将本人内容卡片中引用的图片去重归档，不抓文章正文。

快照格式为 `format: 1`，包含 `fetched_at`、`source_url`、`expected_count`、`profiles`。每人包含稳定 `source_id`、首次导入使用的 `slug`、常用展示字段、原始资料 `data` 与可空的 `avatar`。`data.list/detail/sections` 保留所有业务源字段；`emails`、`links` 保存公开职业联系方式与来源。头像 `path` 相对此 JSON 所在目录，所以后续补充应输出在同目录。

公开邮箱与 PostgreSQL 官方角色补充使用 `enrich_official.py`，说明见该脚本 `--help`。仅保存公开职业信息，不猜测地址或收集私人敏感资料。

解析回归测试：`.venv/bin/python -m unittest tools.hacker.test_collect`。
