"""Render a frozen center Chinese text without changing its stored evidence bytes."""
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, urlunsplit


def local_url(value):
    parsed = urlsplit(value)
    if parsed.netloc and parsed.netloc != "pg.center":
        return value
    path = parsed.path
    if path.startswith(("/zh/docs/", "/zh/wiki/", "/zh/e/")):
        path = path[3:]
        parsed = parsed._replace(scheme="", netloc="", path=path)
    # PGSQL.CC has an explicit redirect for this historical command spelling.
    if (not parsed.netloc) and parsed.path.startswith("/wiki/sql/wait-for/"):
        parsed = parsed._replace(path=parsed.path.replace("/wiki/sql/wait-for/", "/wiki/sql/wait/", 1))
    return urlunsplit(parsed)


def localized_html(body_html, base_url="/docs/", link_map=None):
    """Adapt verified same-site links, then apply the existing preview sanitizer.

    link_map is an optional fixed, offline-verified old URL -> local URL mapping.
    No database lookups or source-language inference occur during rendering.
    """
    from .encyclopedia import localized_preview_html
    soup = BeautifulSoup(body_html or "", "html.parser")
    mapping = link_map or {}
    for node in soup.select("a[href], img[src]"):
        attr = "href" if node.name == "a" else "src"
        original = node[attr]
        node[attr] = mapping.get(original, mapping.get(local_url(original), local_url(original)))
    return localized_preview_html([str(soup)], local_url(base_url))


def plain_text(body_html):
    soup = BeautifulSoup(body_html or "", "html.parser")
    for node in soup.select("script, style"):
        node.decompose()
    return soup.get_text(" ", strip=True)


def prepare(snapshot, version):
    if not snapshot or not isinstance(snapshot.get("center_zh"), dict):
        return snapshot
    text = snapshot["center_zh"]
    base_url = "/docs/{}/".format("devel" if str(version) == "20" else version)
    snapshot["center_zh_rendered"] = localized_html(text.get("body_html", ""), base_url,
                                                  link_map=text.get("link_map"))
    return snapshot
