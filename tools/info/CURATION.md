# 博览编辑规则

本文给编辑模型（Codex、Claude 等）使用：读取某一天的候选材料，产出该日的批次文件 `data/info/YYYY-MM-DD.json`。栏目定义见 [docs/info-column.md](../../docs/info-column.md)。

## 输入

- `~/pgsty/daily/YYYY-MM-DD.md`：当天的中文技术日报，含「今日重点」「简讯」「重磅新闻」三部分；这是主要来源。
- `tools/info/extract_daily.py YYYY-MM-DD` 的候选 JSON（若已可用）：把上面三部分拆成结构化条目，含链接、作者/发布方/日期、原文摘要与标签。
- pgnexus.ai 每日更新（可选，`extract_daily.py --pgnexus JOBID`）：PostgreSQL 技术博客、hackers 邮件讨论、补丁动态，用于补充 PostgreSQL 条目。

材料里没有的事实不要编造；没有链接的候选不能升为一、二档。

## 输出

一个 JSON 文件，UTF-8，缩进两空格，键顺序如下：

```json
{
  "date": "2026-09-10",
  "origin": "pgsty-daily 2026-09-10.md; pgnexus #264",
  "items": [
    {
      "tier": 1,
      "title": "PostgreSQL Anonymizer 3.2 修复三个高危漏洞",
      "summary": "Dalibo 发布 PostgreSQL Anonymizer 3.2，修复了自定义类型提权、规则导入 SQL 注入和并行静态脱敏提权三个漏洞，其中 PostgreSQL 14 及从更早版本升级而来的实例风险最高。新版本默认禁止超级用户执行各类脱敏操作，并用可本地化、速度快约 40 倍的 anon.seeded_* 系列取代 anon.pseudo_*，旧函数进入弃用期。使用静态、副本或备份脱敏的团队需要先准备专用低权限角色，回归规则的导入导出，再安排升级。",
      "url": "https://www.postgresql.org/about/news/postgresql-anonymizer-32-faster-pseudonymization-3373/",
      "author": "Dalibo",
      "source": "PostgreSQL 新闻",
      "source_date": "2026-09-09",
      "image": "",
      "domain": "pg",
      "tags": ["安全", "扩展", "脱敏"],
      "position": 1
    },
    {
      "tier": 2,
      "title": "Autobase 2.11 把副本扩缩与大版本升级收进界面",
      "summary": "新增 pgBackRest 与 WAL-G 的备份恢复 playbook，项目方给出的 5–10 秒写中断和 30–60 秒升级停机仍需自行演练。",
      "url": "https://www.postgresql.org/about/news/autobase-211-released-3374/",
      "author": "",
      "source": "PostgreSQL 新闻",
      "source_date": "2026-09-09",
      "image": "",
      "domain": "pg",
      "tags": ["高可用"],
      "position": 2
    },
    {
      "tier": 3,
      "title": "CodeQL 2.27.0 把 libpq 接口纳入 SQL 注入建模",
      "summary": "",
      "url": "https://github.blog/changelog/2026-09-09-codeql-2-27-0-adds-support-for-linux-arm64",
      "author": "",
      "source": "",
      "source_date": "2026-09-09",
      "image": "",
      "domain": "infra",
      "tags": [],
      "position": 3
    }
  ]
}
```

字段要求：

| 字段 | 一档 | 二档 | 三档 |
| --- | --- | --- | --- |
| `title` | 必填，≤ 40 字 | 必填，≤ 40 字 | 必填，≤ 40 字 |
| `summary` | 一个完整自然段，80–300 字 | 一句话，≤ 80 字 | 空字符串 |
| `url` | 必填，一手来源 | 必填 | 可空 |
| `author` | 必填（人名、团队或机构） | 可空 | 空 |
| `source` | 必填（发布站点或机构） | 可空 | 空 |
| `source_date` | 有则填 | 有则填 | 有则填 |
| `image` | 可选，原文的题图或 og:image 地址，必须是 https；站点通用标志或默认社交图（如 postgresql.org 的 elephant.png）不算题图，留空 | 空 | 空 |
| `domain` | `pg` / `db` / `cloud` / `infra` / `ai` 之一 | 同左 | 同左 |
| `tags` | 0–4 个短词 | 0–3 个 | 0–2 个 |
| `position` | 从 1 开始，一档在前，二档居中，三档在后，全日连续编号 | | |

`key` 由导入器按 `date + url（无链接时用 title）` 计算，编辑不用填写。

## 选题

- 当天目标 10–30 条。大新闻通常 3–8 条，小新闻 5–12 条，其余为迷你条目；不必凑满。
- 优先级：PostgreSQL 内核、发布、安全、扩展、工具与生态 → 其他数据库与数据平台 → 云与基础设施 → AI 基础设施与开发者工具。泛 AI 产品、消费电子、市场传闻、营销稿、无一手来源的转述不收。
- 材料过多时先去掉与数据库和基础设施关系弱的条目；过少时从「简讯」与 pgnexus 补充数据库、云数据库和云基础设施资讯；仍不足则宁少勿滥。
- 同一事件只收一条，选最一手的链接为 `url`；多个补充链接不进入字段。
- 日报「今日重点」与「重磅新闻」中的条目通常是一档；「简讯」多为二档；版本小更新、单条工具发布、会议通知等为三档。
- 一档必须有可核实的作者或发布方；找不到作者时用发布机构填 `author`。

## 文字

- 标题是完整陈述句，说清对象与变化，不用问句和悬念；不以「重磅」「震惊」等词开头。
- 一档摘要独立组织事实：背景一句、核心变化两三句、影响或注意事项一两句；不逐句翻译原文，不写「本文介绍了」。
- 二档一句话补充标题没说的关键信息（版本、条件、影响），不重复标题。
- 中文与英文、数字之间留一个空格；全角标点后不加空格；专有名词保留原文大小写（PostgreSQL、pgBackRest、pg_stat_statements）。
- 不写免责声明，不评价来源可信度；对厂商数据用「厂商称」「官方口径」标明即可。
- 数字与版本号照原文；不确定的信息不写。

## 交付前自查

1. JSON 可解析，`date` 与文件名一致，`position` 连续且按档位排列。
2. 一、二档都有 `url`；一档都有 `author`、`source` 与 80–300 字摘要。
3. 全日条目 10–30 条，无重复事件，无与数据库或基础设施无关的内容。
4. 标题不超过 40 字，摘要没有英文原句直译的痕迹。
