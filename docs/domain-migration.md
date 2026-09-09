# pgsql.cc 域名配置与切换

目标站点为 `https://pgsql.cc`。`pg.center` 分支保留改名前的 `92141275` 提交，改名工作在 `codex/pgsql-cc` 分支进行。

## 页面与链接

首页公告、导航、页脚、联系页、国际化入口、版权署名和维护文档统一使用 pgsql.cc。关于页为 `/about/pgsql/`；旧 `/about/pgcenter/` 地址通过 301 跳转保留访问兼容。

首页 JSON-LD、canonical、Open Graph、Twitter 卡片、robots.txt、站点地图与 RSS 使用 `SITE_ROOT` 生成本站地址。默认值为 `https://pgsql.cc`，页面 SEO 数据也使用新站名。站点样式文件为 `media/css/pgsql.css`。

## Django 运行配置

将 [`tools/deploy/pgsql.cc/settings.py`](../tools/deploy/pgsql.cc/settings.py) 中的域名设置合入生产 `/data/app/pgweb/pgweb/settings_local.py`。保留该文件的数据库、密钥、邮件与其他现有配置。

运行时加载的是 `pgweb/settings_local.py`。仓库根目录同名文件只可能被本地包装配置显式引用，不是 Django 默认读取的位置。部署时必须同步 `SITE_ROOT`、`ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` 和两种 Cookie 域名，避免旧的本地覆盖值继续生成旧域名链接。

开发预览可保留 Cookie 域为 `None` 及非 HTTPS Cookie；canonical 仍指向 `https://pgsql.cc`。本机两份私有设置和爬虫配置已调整，原文件备份位于 `tmp/pgsql-cc-domain-change/`，其中含连接信息，不应提交到 Git。

## Nginx 与声明式配置

[`tools/deploy/pgsql.cc/portal.yml`](../tools/deploy/pgsql.cc/portal.yml) 是生产 Pigsty `infra_portal` 的增量配置。将这三个条目合入 `/root/pigsty/pigsty.yml` 已有映射，保留其他站点。`pgweb` 键继续使用既有应用端口、日志及文件目录；新增条目用于 `www.pgsql.cc` 和旧域名的永久跳转。

[`nginx/pgweb.conf`](../tools/deploy/pgsql.cc/nginx/pgweb.conf) 与 [`nginx/redirect.conf`](../tools/deploy/pgsql.cc/nginx/redirect.conf) 是配套 Ansible 模板，放到 `/root/pigsty/roles/infra/templates/nginx/`。应用模板沿用生产配置，转发到 `127.0.0.1:8000`；三个静态文件映射保持如下配置：

| URL | 生产目录 |
| --- | --- |
| `/media/` | `/data/app/pgweb/media/` |
| `/media/admin/` | `/data/app/pgweb/static_collected/admin/` |
| `/files/` | `/data/app/pgweb/static/` |

新域名及 `www` 需要对应 DNS 和 TLS 证书。旧域名的证书继续保留以完成 HTTPS 跳转。跳转保留完整路径和查询参数；HTTP 请求直接跳到新域名 HTTPS 地址。

配置源准备好后，在生产 Pigsty 目录按既有流程生成配置：

```sh
ansible-playbook -i pigsty.yml infra.yml --limit 10.10.10.19 --tags nginx_config --skip-tags nginx_firewall
nginx -t && systemctl reload nginx
systemctl restart pgweb
```

生成配置前应先备份原配置并准备证书；上述命令本身不完成 DNS 切换或证书签发。

## 爬虫与搜索

[`tools/search/crawler/search.ini.sample`](../tools/search/crawler/search.ini.sample) 使用 `web=pgsql.cc`、`https=true`，并通过 `local_baseurl=http://127.0.0.1:8000` 抓取本机服务。将这些非敏感字段同步到生产爬虫目录的 `search.ini`，保留现有 `db` 连接字符串。

全文搜索的本站结果链接立即跟随 `SITE_ROOT`，不依赖 `sites.baseurl` 中是否仍保留旧域名。爬虫下次完成抓取后，会更新 `sites` 中主站记录的域名、基地址和协议，保留已有站点 ID。其他站点的链接不受影响。

新库的 `tools/search/sql/data.sql` 初始化记录同样使用 `pgsql.cc` 和 HTTPS，无需初始化后另行改域名。

生产应用完成域名切换后，可按以下命令刷新全文搜索正文与站点记录：

```sh
cd /data/app/pgweb/tools/search/crawler
../../../.venv/bin/python webcrawler.py
```

本次改名没有数据库迁移，也没有执行数据库写入或爬虫。手册实体检索采用相对链接，无需因域名变化重建索引。代码中的旧名称仅用于兼容跳转、相关回归测试和本迁移说明；历史报告、备份与 Git 记录保留原貌。
