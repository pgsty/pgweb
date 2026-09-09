# pgsql.cc 独立服务部署

`main` 是 `https://pgsql.cc` 的生产分支；`pg.center` 分支保留旧站的 `92141275` 提交。两站共用生产 `pgweb` 数据库，分别运行 Django/Gunicorn。新站只绑定 `pgsql.cc`，不配置 `www` 或通配域名。

| 项目 | 新站 | 旧入口 |
| --- | --- | --- |
| 域名 | `pgsql.cc` | `pg.center` |
| 代码 | `/data/app/pgsql.cc`，`main` | `/data/app/pgweb`，`pg.center` |
| 服务 | `pgsql.cc.service` | `pgweb.service` |
| 监听 | `127.0.0.1:8001` | `127.0.0.1:8000` |
| Pigsty 条目 | `pgsql` | `pgweb` |
| Nginx 配置 | `/etc/nginx/conf.d/pgsql.conf` | `/etc/nginx/conf.d/pgweb.conf` |

## 代码、配置与文件

先在本地提交并推送 `main`，再在 `ssh pg` 上克隆 `https://github.com/pgsty/pgweb.git` 的 `main` 到 `/data/app/pgsql.cc`。旧目录固定在旧提交，不随新站发布拉取 `main`。

新建独立 `.venv`，首次部署按旧站 `pip freeze --all` 的版本安装，包括 Gunicorn；不要直接复制带有旧绝对路径的虚拟环境。复制旧站的 `static/` 业务文件及存在的 `data/yum.json`、`data/ftpsite.pickle`。两份业务文件以后应随内容更新同步。

复制生产 `/data/app/pgweb/pgweb/settings_local.py` 到新目录相同位置，再追加 [`tools/deploy/pgsql.cc/settings.py`](../tools/deploy/pgsql.cc/settings.py)。数据库、`SEARCH_DSN`、密钥和邮件配置继续共用，域名、Cookie 和文件路径按新站覆盖。配置文件包含秘密，不提交 Git。实际加载的是包内 `pgweb/settings_local.py`，不是仓库根目录的同名文件。

在新目录执行 `manage.py check`、`manage.py migrate --check` 和 `manage.py collectstatic --noinput`。这次新增实例没有数据库迁移，不重新导入数据或重建索引。以后的结构变更必须兼容两站，迁移和后台任务只安排一套。

安装 [`pgsql.cc.service`](../tools/deploy/pgsql.cc/pgsql.cc.service) 到 `/etc/systemd/system/`，执行 `systemctl daemon-reload`、`systemctl enable --now pgsql.cc.service`。该 unit 沿用旧站运行用户与重启策略，只更换应用目录、名称和端口。

## Pigsty、Nginx 与证书

备份 `/root/pigsty/pigsty.yml`、Nginx 模板和 `/etc/nginx`。将 [`portal.yml`](../tools/deploy/pgsql.cc/portal.yml) 的单个 `pgsql` 条目追加到既有 `infra_portal`，保留 `pgweb` 和其他站点。

[`nginx/pgweb.conf`](../tools/deploy/pgsql.cc/nginx/pgweb.conf) 对应 `/root/pigsty/roles/infra/templates/nginx/pgweb.conf`，通过条目参数区分端口和目录。三个新站静态映射为：

| URL | 目录 |
| --- | --- |
| `/media/` | `/data/app/pgsql.cc/media/` |
| `/media/admin/` | `/data/app/pgsql.cc/static_collected/admin/` |
| `/files/` | `/data/app/pgsql.cc/static/` |

确认 `pgsql.cc` 的 A 记录指向 `ssh -G pg` 核验的源站地址；首次签发使用仅 DNS。只申请 `pgsql.cc`，不申请其他域名。HTTP 的 `/.well-known/acme-challenge/` 使用 `/www/acme`。首次签发前可用临时 HTTP vhost 服务验证文件，签发成功后再生成完整 HTTPS 配置。

```sh
certbot certonly --webroot -w /www/acme --cert-name pgsql.cc -d pgsql.cc
cd /root/pigsty
ansible-playbook -i pigsty.yml infra.yml --limit 10.10.10.19 --tags nginx_config --skip-tags nginx_firewall
/etc/nginx/link-cert
nginx -t && systemctl reload nginx
certbot renew --cert-name pgsql.cc --dry-run
```

`nginx_config` 会重新生成 `/etc/nginx/link-cert`，但不会执行它；必须显式运行，确保新域名链接到 `/etc/letsencrypt/live/pgsql.cc/`。正常续期复用已有 `certbot-renew.timer` 和 `/etc/letsencrypt/renewal-hooks/deploy/10-reload-nginx`。若开启 Cloudflare 代理，使用 Full (strict)，并确认验证路径不被拦截。

## 页面与搜索

首页公告、导航、页脚和版权署名使用 pgsql.cc。关于页为 `/about/pgsql/`；旧 `/about/pgcenter/` 保留路径级 301。canonical、Open Graph、JSON-LD、RSS、robots.txt 和 sitemap 使用本实例的 `SITE_ROOT`。

手册实体检索与扩展索引使用相对链接，共用现有索引即可。全文搜索的新站结果由 `SITE_ROOT` 生成，但旧站代码仍使用搜索库 `sites.baseurl`。双站并存期间，保留旧站爬虫配置及 `sites.id=1` 的 `pg.center` 域名，不在新目录运行爬虫：新版爬虫成功运行会修改这条共用记录。旧站退出后，才将爬虫切换到 `pgsql.cc`、`local_baseurl=http://127.0.0.1:8001` 并刷新全文索引。

## 验收与回滚

分别验证源站与公网 HTTPS：首页、`/docs/`、手册正文、`/ext/`、两种搜索、管理入口、CSS/JS、PDF、RSS 和 sitemap。检查新站 canonical 为 pgsql.cc，旧站继续返回旧入口页面。确认新服务的进程、工作目录、监听端口和 Git SHA；通过 `migrate --check` 确认共库结构兼容。

新站回滚时停用 `pgsql.cc.service`，恢复备份的 Pigsty/Nginx 配置并通过 `nginx -t` 后 reload。不要回滚共用数据库或覆盖旧站目录。保留证书续期配置，待确认新站退役后再清理。
