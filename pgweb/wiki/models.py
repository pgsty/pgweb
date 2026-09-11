"""百科 · 错误码大全。

数据是 pgsty/err.pg.center 仓库的投影，导入工具可以随时整体重建。权威三层在那边：
`evidence/<CODE>.json`（人工证据）、`data/errcodes/<CODE>.json`（规范事实）、
`content/docs/<CODE>.md` 与 `.zh.md`（正文）。这里的表只为渲染与查询服务。

热字段提成真列供筛选与排序，整份原始事实同时留在 `ErrorCode.facts` 里——
结构化是增量，不是替换。
"""

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


# 证据强度由弱到强。源数据把状态挂在单条证据上，一个码可以同时有好几档；
# 条目上存的是它达到过的最高档。
EVIDENCE_TIERS = (
    ('unknown', '未知'),
    ('definition_only', '仅定义'),
    ('source_path_confirmed', '源码确认'),
    ('observed_runtime', '已实测'),
)
TIER_ORDER = [tier for tier, _ in EVIDENCE_TIERS]
TIER_LABEL = dict(EVIDENCE_TIERS)

DEPTHS = (('reference', '参考'), ('full', '详解'))
DEPTH_LABEL = dict(DEPTHS)

# errcodes.txt 的严重级字母。
SEVERITIES = (('E', 'ERROR'), ('W', 'WARNING'), ('S', 'SUCCESS'))
SEVERITY_LABEL = dict(SEVERITIES)

STATUS_LABEL = {'active': '有效', 'removed': '已移除', 'preview': '预发行'}

RUNTIME_LABEL = {'passed': '实测通过', 'failed': '实测失败',
                 'not_run': '未实测', 'not_applicable': '不适用'}


class ErrorCodeClass(models.Model):
    """SQLSTATE 前两位的类别，44 个。"""

    code = models.CharField(max_length=2, primary_key=True)
    name = models.TextField()
    name_zh = models.TextField(blank=True, default='')
    summary = models.TextField(blank=True, default='')
    sqlstate_count = models.IntegerField(default=0)
    severity_classes = ArrayField(models.TextField(), default=list, blank=True)

    class Meta:
        db_table = 'wiki_errcode_class'
        ordering = ('code',)

    def __str__(self):
        return 'Class {} {}'.format(self.code, self.name)

    @property
    def anchor(self):
        return 'class-' + self.code

    @property
    def url(self):
        # 导航索引跳同页锚点，与手册附录 A 的读法一致。
        return '/docs/sqlstate/#class-' + self.code

    @property
    def label(self):
        return self.name_zh or self.name


class ErrorCodeRelease(models.Model):
    """一个锁定的版本快照。commit 让详情页能把源码链接切到指定版本。"""

    major = models.CharField(max_length=12, primary_key=True)
    channel = models.CharField(max_length=8, default='formal')
    release = models.TextField(blank=True, default='')
    tag = models.TextField(blank=True, default='')
    commit = models.CharField(max_length=40, blank=True, default='')
    path = models.TextField(blank=True, default='')
    code_count = models.IntegerField(default=0)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_release'
        ordering = ('position',)

    def __str__(self):
        return self.major

    @property
    def is_preview(self):
        return self.channel == 'preview'


class ErrorCode(models.Model):
    """一个 SQLSTATE，263 个。"""

    sqlstate = models.CharField(max_length=5, primary_key=True)
    klass = models.ForeignKey(ErrorCodeClass, related_name='codes', db_column='class_code',
                              on_delete=models.PROTECT)
    condition_name = models.TextField(blank=True, default='')
    condition_names = ArrayField(models.TextField(), default=list, blank=True)
    aliases = ArrayField(models.TextField(), default=list, blank=True)
    macros = ArrayField(models.TextField(), default=list, blank=True)
    primary_macro = models.TextField(blank=True, default='')
    severity_classes = ArrayField(models.TextField(), default=list, blank=True)
    status = models.TextField(default='active')

    # 两个都极稀疏：全库只有 57P04 有精确引入边界，removed 263 个全为 null。
    # 留空就是未取证，不要在页面上编一个版本出来。
    introduced = models.JSONField(null=True, blank=True)
    removed = models.JSONField(null=True, blank=True)
    # 历史扫描能到的下界，不是真实引入版本：170/263 个码是 7.4。
    known_present_by = models.TextField(blank=True, default='')

    # 大版本，按快照顺序；精确快照号留在 facts['present_in_snapshots'] 里。
    present_in = ArrayField(models.TextField(), default=list, blank=True)
    preview_in = ArrayField(models.TextField(), default=list, blank=True)

    depth = models.TextField(default='reference')
    # 错误码里恒为 reviewed，留着是为了跟上游字段对齐，不要做成筛选项。
    editorial_review = models.TextField(blank=True, default='')
    runtime_verification = models.TextField(blank=True, default='')
    evidence_tier = models.TextField(blank=True, default='')

    case_count = models.IntegerField(default=0)
    snippet_count = models.IntegerField(default=0)

    facts = models.JSONField(default=dict, blank=True)
    source_rev = models.TextField(blank=True, default='')
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wiki_errcode'
        # 与手册附录一致：先按类，再按码。
        ordering = ('klass', 'sqlstate')
        indexes = [
            models.Index(fields=('klass', 'sqlstate'), name='wiki_errcode_class_order'),
            models.Index(fields=('evidence_tier',), name='wiki_errcode_tier'),
            models.Index(fields=('condition_name',), name='wiki_errcode_condition'),
        ]

    def __str__(self):
        return '{} {}'.format(self.sqlstate, self.condition_name)

    @property
    def url(self):
        return '/docs/sqlstate/{}/'.format(self.sqlstate)

    @property
    def severity(self):
        return self.severity_classes[0] if self.severity_classes else ''

    @property
    def severity_label(self):
        return SEVERITY_LABEL.get(self.severity, self.severity)

    @property
    def status_label(self):
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def depth_label(self):
        return DEPTH_LABEL.get(self.depth, self.depth)

    @property
    def tier_label(self):
        return TIER_LABEL.get(self.evidence_tier, self.evidence_tier)

    @property
    def runtime_label(self):
        return RUNTIME_LABEL.get(self.runtime_verification, self.runtime_verification)

    @property
    def formal_present_in(self):
        """只取正式版。预发行快照单独标，不并进版本区间。"""
        preview = set(self.preview_in)
        return [major for major in self.present_in if major not in preview]

    @property
    def version_range(self):
        """展示用的版本区间。present_in 已按快照顺序导入。"""
        majors = self.formal_present_in
        if not majors:
            return ''
        return majors[0] if len(majors) == 1 else '{} – {}'.format(majors[0], majors[-1])


class ErrorCodeText(models.Model):
    """正文，每个码每种语言一行。站点只渲染中文，英文原文一并存着。"""

    errcode = models.ForeignKey(ErrorCode, related_name='texts', on_delete=models.CASCADE)
    lang = models.CharField(max_length=5)
    title = models.TextField(blank=True, default='')
    # 中文短名，只有 114/263 个码的标题里写了，缺的留空而不是回落到英文。
    name = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    # 「速览」首句，263 个码都有，索引页表格用它。
    summary = models.TextField(blank=True, default='')
    body_md = models.TextField(blank=True, default='')
    sections = models.JSONField(default=list, blank=True)
    # 对应英文正文的内容哈希；英文改了而译文没跟上时置 is_stale。
    translation_source_rev = models.TextField(blank=True, default='')
    is_stale = models.BooleanField(default=False)
    search_vector = SearchVectorField(null=True)

    class Meta:
        db_table = 'wiki_errcode_text'
        ordering = ('errcode', 'lang')
        constraints = [
            models.UniqueConstraint(fields=('errcode', 'lang'), name='wiki_errcode_text_lang'),
        ]
        indexes = [GinIndex(fields=('search_vector',), name='wiki_errcode_text_vector')]

    def __str__(self):
        return '{} [{}]'.format(self.errcode_id, self.lang)


class ErrorCodePresence(models.Model):
    """存在性区间。源数据的逐补丁版行（11 万条）压在这里，源仓库仍留有全量。"""

    errcode = models.ForeignKey(ErrorCode, related_name='presence', on_delete=models.CASCADE)
    era = models.CharField(max_length=8, default='modern')  # modern / pre9
    start = models.TextField(blank=True, default='')
    end = models.TextField(blank=True, default='')
    start_tag = models.TextField(blank=True, default='')
    end_tag = models.TextField(blank=True, default='')
    start_major = models.TextField(blank=True, default='')
    end_major = models.TextField(blank=True, default='')
    evidence_count = models.IntegerField(default=0)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_presence'
        ordering = ('errcode', 'era', 'position')
        indexes = [models.Index(fields=('errcode', 'era'), name='wiki_errcode_presence_era')]


class ErrorCodeSource(models.Model):
    """人工证据引用的源码位置，带 tag、commit 与行号。"""

    errcode = models.ForeignKey(ErrorCode, related_name='sources', on_delete=models.CASCADE)
    source_id = models.TextField()
    kind = models.TextField(blank=True, default='')
    tag = models.TextField(blank=True, default='')
    commit = models.CharField(max_length=40, blank=True, default='')
    path = models.TextField(blank=True, default='')
    location = models.TextField(blank=True, default='')
    url = models.TextField(blank=True, default='')
    docs_url = models.TextField(blank=True, default='')
    sha256 = models.CharField(max_length=64, blank=True, default='')
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_source'
        ordering = ('errcode', 'position')


class ErrorCodeClaim(models.Model):
    """一句可核实的论断，附佐证来源与限制条件。详情页证据面板的一行。"""

    errcode = models.ForeignKey(ErrorCode, related_name='claims', on_delete=models.CASCADE)
    claim_id = models.TextField()
    statement = models.TextField()
    method = models.TextField(blank=True, default='')
    limits = models.TextField(blank=True, default='')
    sources = ArrayField(models.TextField(), default=list, blank=True)
    runtime = ArrayField(models.TextField(), default=list, blank=True)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_claim'
        ordering = ('errcode', 'position')


class ErrorCodeMessage(models.Model):
    """一条报文记录。模板本身摊平进 ErrorCodeTemplate，这里留身份与限制。"""

    errcode = models.ForeignKey(ErrorCode, related_name='messages', on_delete=models.CASCADE)
    message_id = models.TextField()
    severity = models.TextField(blank=True, default='')
    path = models.TextField(blank=True, default='')
    limits = models.TextField(blank=True, default='')
    sources = ArrayField(models.TextField(), default=list, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_message'
        ordering = ('errcode', 'position')


class ErrorCodeTemplate(models.Model):
    """摊平后的报文模板。

    565 条报文里只有 539 条走 `primary_template` 一个键，其余散在单复数分支、
    变体数组与角色映射里。报文反查检索这张表，只认 primary_template 会漏掉那些码。
    """

    KINDS = (('primary', '主消息'), ('detail', 'DETAIL'), ('hint', 'HINT'), ('context', 'CONTEXT'))

    message = models.ForeignKey(ErrorCodeMessage, related_name='templates', on_delete=models.CASCADE)
    errcode = models.ForeignKey(ErrorCode, related_name='templates', on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=KINDS)
    # 变体标签：single/plural、roles[].role、variants 的 target 等，没有就留空。
    role = models.TextField(blank=True, default='')
    template = models.TextField()
    # 模板去掉 %s/%d 之类占位符后的字面部分，供反查匹配。
    literal = models.TextField(blank=True, default='')
    position = models.IntegerField(default=0)
    search_vector = SearchVectorField(null=True)

    class Meta:
        db_table = 'wiki_errcode_template'
        ordering = ('errcode', 'position')
        indexes = [
            GinIndex(fields=('search_vector',), name='wiki_errcode_tpl_vector'),
            models.Index(fields=('errcode', 'kind'), name='wiki_errcode_tpl_kind'),
        ]

    def __str__(self):
        return '{} {} {}'.format(self.errcode_id, self.kind, self.template[:40])


class ErrorCodeRuntime(models.Model):
    """一次被选定的真实运行记录。assertions/observed/environment 形状自由，整块留 JSON。"""

    errcode = models.ForeignKey(ErrorCode, related_name='runtimes', on_delete=models.CASCADE)
    runtime_id = models.TextField()
    run_id = models.TextField(blank=True, default='')
    status = models.TextField(blank=True, default='')
    target = models.TextField(blank=True, default='')
    server_version = models.TextField(blank=True, default='')
    cases = ArrayField(models.TextField(), default=list, blank=True)
    limits = models.TextField(blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_runtime'
        ordering = ('errcode', 'position')


class ErrorCodeCase(models.Model):
    """可复现案例。87 个码有用例定义，其中 66 个另有可执行 SQL 片段。"""

    errcode = models.ForeignKey(ErrorCode, related_name='cases', on_delete=models.CASCADE)
    case_id = models.TextField()
    versions = ArrayField(models.TextField(), default=list, blank=True)
    preconditions = ArrayField(models.TextField(), default=list, blank=True)
    trigger = models.TextField(blank=True, default='')
    assertions = ArrayField(models.TextField(), default=list, blank=True)
    repair = models.TextField(blank=True, default='')
    cleanup = models.TextField(blank=True, default='')
    has_snippet = models.BooleanField(default=False)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_errcode_case'
        ordering = ('errcode', 'position')


# ------------------------------------------------------------------ 系统目录

# 类别顺序固定，页面各处都按这个顺序走。
CATALOG_KINDS = (
    ('catalog', '系统目录表', 'SYSTEM CATALOG'),
    ('view', '系统视图', 'SYSTEM VIEW'),
    ('statistics', '统计视图', 'STATISTICS VIEW'),
    ('progress', '进度视图', 'PROGRESS REPORT'),
)
CATALOG_KIND_LABEL = {kind: label for kind, label, _ in CATALOG_KINDS}
CATALOG_KIND_EYEBROW = {kind: eyebrow for kind, _, eyebrow in CATALOG_KINDS}
CATALOG_KIND_ORDER = {kind: index for index, (kind, _, _) in enumerate(CATALOG_KINDS)}

# relkind 的可读名，事实卡用。
RELKIND_LABEL = {'r': '普通表', 'v': '视图', 'm': '物化视图', 'i': '索引',
                 'S': '序列', 't': 'TOAST 表', 'c': '复合类型', 'f': '外部表', 'p': '分区表'}

CATALOG_STATUS_LABEL = {'historical': '历史版本', 'stable': '当前稳定版',
                        'preview': '预发行', 'devel': '开发版'}


class CatalogVersion(models.Model):
    """一个大版本的系统目录快照概况，18 行（9.0 – 19 来自 cat，20 由本站 devel 手册推导）。"""

    major = models.CharField(max_length=8, primary_key=True)
    label = models.TextField(blank=True, default='')
    status = models.TextField(blank=True, default='')
    support_status = models.TextField(blank=True, default='')
    source_tag = models.TextField(blank=True, default='')
    documentation_version = models.TextField(blank=True, default='')
    release = models.TextField(blank=True, default='')
    # 本站手册地址段：'10' … '19'，20 为 'devel'；9.x 本站没有手册，仍照实记。
    doc_slug = models.TextField(blank=True, default='')
    relation_count = models.IntegerField(default=0)
    column_count = models.IntegerField(default=0)
    kinds = models.JSONField(default=dict, blank=True)
    runtime_verified = models.BooleanField(default=False)
    schema_source = models.TextField(blank=True, default='')
    # 与上一版的汇总（cat transitions[] 的一项），9.0 为 {}。
    transition = models.JSONField(default=dict, blank=True)
    # 版本次序只认这一列：'9.0' 与 '10' 字符串比不出先后。
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_catalog_version'
        ordering = ('position',)

    def __str__(self):
        return self.label or self.major

    @property
    def is_preview(self):
        return self.status == 'preview'

    @property
    def is_devel(self):
        return self.status == 'devel'

    @property
    def status_label(self):
        return CATALOG_STATUS_LABEL.get(self.status, self.status)

    @property
    def changes_url(self):
        return '/docs/catalog/changes/{}/'.format(self.major)


class CatalogRelation(models.Model):
    """一个系统目录表、系统视图、统计视图或进度视图，158 行。

    逐版本快照与变化记录整份放 JSON：一个大版本才变一次，读多写少，拆表没有收益。
    """

    name = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=12)
    summary = models.TextField(blank=True, default='')
    # 手册总览表里的中文一句话，采不到留空，页面显示英文。
    summary_zh = models.TextField(blank=True, default='')
    first_version = models.CharField(max_length=8, blank=True, default='')
    last_version = models.CharField(max_length=8, blank=True, default='')
    present_in = ArrayField(models.TextField(), default=list, blank=True)
    changed_in = ArrayField(models.TextField(), default=list, blank=True)
    column_count = models.IntegerField(default=0)
    relation_oid = models.IntegerField(null=True, blank=True)
    relkind = models.CharField(max_length=1, blank=True, default='')
    shared = models.BooleanField(default=False)
    versions = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=list, blank=True)
    # 类别序 × 1000 + 类别内按名排序。
    position = models.IntegerField(default=0)
    source_rev = models.TextField(blank=True, default='')
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wiki_catalog'
        ordering = ('position',)
        indexes = [
            models.Index(fields=('kind', 'name'), name='wiki_catalog_kind'),
        ]

    def __str__(self):
        return self.name

    @property
    def url(self):
        return '/docs/catalog/{}/'.format(self.name)

    @property
    def kind_label(self):
        return CATALOG_KIND_LABEL.get(self.kind, self.kind)

    @property
    def eyebrow(self):
        return CATALOG_KIND_EYEBROW.get(self.kind, '')

    @property
    def relkind_label(self):
        return RELKIND_LABEL.get(self.relkind, self.relkind)
