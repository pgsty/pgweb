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


# ================================================================ 配置参数

# pg_settings.context 的七个取值：改动生效的方式，从"不能改"到"任何会话都能改"。
GUC_CONTEXTS = (
    ('internal', '内部', '由编译或 initdb 决定，运行时不能修改'),
    ('postmaster', '重启生效', '只能在服务器启动时设置，修改后需要重启'),
    ('sighup', '重载生效', '改配置文件后重载（pg_ctl reload / SIGHUP）即可生效'),
    ('superuser-backend', '连接时（超级用户）', '只能在连接建立时由超级用户设置'),
    ('backend', '连接时', '只能在连接建立时设置，会话内不能再改'),
    ('superuser', '会话（超级用户）', '超级用户可在会话内用 SET 修改'),
    ('user', '会话', '任何用户都可在会话内用 SET 修改'),
)
GUC_CONTEXT_LABEL = {context: label for context, label, _ in GUC_CONTEXTS}
GUC_CONTEXT_NOTE = {context: note for context, _, note in GUC_CONTEXTS}

GUC_VARTYPES = (('bool', '布尔'), ('integer', '整数'), ('real', '浮点'),
                ('string', '字符串'), ('enum', '枚举'))
GUC_VARTYPE_LABEL = dict(GUC_VARTYPES)

# 逐版本比较的字段与中文标签。前七个是"实质变化"（默认值、单位、上下文、类型、范围、
# 枚举值），后三个只算措辞或归类变化。
GUC_FIELDS = (
    ('boot_val', '默认值'), ('unit', '单位'), ('context', '上下文'), ('vartype', '类型'),
    ('min_val', '最小值'), ('max_val', '最大值'), ('enumvals', '枚举值'),
    ('category', '分类'), ('short_desc', '简述'), ('extra_desc', '补充说明'),
)
GUC_FIELD_LABEL = dict(GUC_FIELDS)
GUC_SUBSTANTIVE_FIELDS = ('boot_val', 'unit', 'context', 'vartype', 'min_val', 'max_val', 'enumvals')
GUC_DEFAULT_FIELDS = ('boot_val', 'unit')

# 十六个一级分类，按手册第 19 章的先后。slug 是索引页锚点与筛选值。
GUC_GROUPS = (
    ('File Locations', '文件位置', 'file-locations'),
    ('Connections and Authentication', '连接和认证', 'connection'),
    ('Resource Usage', '资源消耗', 'resource'),
    ('Write-Ahead Log', '预写式日志', 'wal'),
    ('Replication', '复制', 'replication'),
    ('Query Tuning', '查询规划', 'query'),
    ('Reporting and Logging', '错误报告和日志', 'logging'),
    ('Statistics', '运行时统计数据', 'statistics'),
    ('Vacuuming', '清理', 'vacuum'),
    ('Client Connection Defaults', '客户端连接默认值', 'client'),
    ('Lock Management', '锁管理', 'locks'),
    ('Version and Platform Compatibility', '版本和平台兼容性', 'compatible'),
    ('Error Handling', '错误处理', 'error-handling'),
    ('Preset Options', '预置选项', 'preset'),
    ('Customized Options', '自定义选项', 'custom'),
    ('Developer Options', '开发者选项', 'developer'),
)
GUC_GROUP_LABEL = {group: label for group, label, _ in GUC_GROUPS}
GUC_GROUP_SLUG = {group: slug for group, _, slug in GUC_GROUPS}
GUC_GROUP_BY_SLUG = {slug: group for group, _, slug in GUC_GROUPS}
GUC_GROUP_ORDER = {group: index for index, (group, _, _) in enumerate(GUC_GROUPS)}
# 老版本 pg_settings 里几个不带一级分类的名字，归到今天的所属一级分类。
GUC_GROUP_OF_BARE = {'Autovacuum': 'Vacuuming', 'Process Title': 'Reporting and Logging',
                     'Replication': 'Replication'}

# pg_settings.category 在 9.0 – 19 出现过的全部 58 个取值及其中文。字典顺序就是索引页里
# 同一一级分类下子分类的显示顺序（沿用手册顺序，已消失的老分类排在相近的现代分类旁边）。
GUC_CATEGORY_ZH = {
    'File Locations': '文件位置',
    'Connections and Authentication / Connection Settings': '连接和认证 / 连接设置',
    'Connections and Authentication / TCP Settings': '连接和认证 / TCP 设置',
    'Connections and Authentication / Authentication': '连接和认证 / 认证',
    'Connections and Authentication / Security and Authentication': '连接和认证 / 安全和认证',
    'Connections and Authentication / SSL': '连接和认证 / SSL',
    'Resource Usage / Memory': '资源消耗 / 内存',
    'Resource Usage / Disk': '资源消耗 / 磁盘',
    'Resource Usage / Kernel Resources': '资源消耗 / 内核资源',
    'Resource Usage / Cost-Based Vacuum Delay': '资源消耗 / 基于代价的清理延迟',
    'Resource Usage / Time': '资源消耗 / 计时',
    'Resource Usage / Background Writer': '资源消耗 / 后台写入器',
    'Resource Usage / I/O': '资源消耗 / I/O',
    'Resource Usage / Asynchronous Behavior': '资源消耗 / 异步行为',
    'Resource Usage / Worker Processes': '资源消耗 / 工作进程',
    'Write-Ahead Log / Settings': '预写式日志 / 设置',
    'Write-Ahead Log / Checkpoints': '预写式日志 / 检查点',
    'Write-Ahead Log / Archiving': '预写式日志 / 归档',
    'Write-Ahead Log / Recovery': '预写式日志 / 恢复',
    'Write-Ahead Log / Archive Recovery': '预写式日志 / 归档恢复',
    'Write-Ahead Log / Recovery Target': '预写式日志 / 恢复目标',
    'Write-Ahead Log / Summarization': '预写式日志 / WAL 汇总',
    'Write-Ahead Log / Streaming Replication': '预写式日志 / 流复制',
    'Write-Ahead Log / Standby Servers': '预写式日志 / 备用服务器',
    'Replication': '复制',
    'Replication / Sending Servers': '复制 / 发送服务器',
    'Replication / Master Server': '复制 / 主服务器',
    'Replication / Primary Server': '复制 / 主库',
    'Replication / Standby Servers': '复制 / 备库',
    'Replication / Subscribers': '复制 / 订阅者',
    'Query Tuning / Planner Method Configuration': '查询规划 / 规划器方法配置',
    'Query Tuning / Planner Cost Constants': '查询规划 / 规划器代价常量',
    'Query Tuning / Genetic Query Optimizer': '查询规划 / 遗传查询优化',
    'Query Tuning / Other Planner Options': '查询规划 / 其他规划器选项',
    'Reporting and Logging / Where to Log': '错误报告和日志 / 记录到哪里',
    'Reporting and Logging / When to Log': '错误报告和日志 / 何时记录',
    'Reporting and Logging / What to Log': '错误报告和日志 / 记录什么',
    'Reporting and Logging / Process Title': '错误报告和日志 / 进程标题',
    'Process Title': '进程标题',
    'Statistics / Cumulative Query and Index Statistics': '运行时统计数据 / 累积查询和索引统计',
    'Statistics / Query and Index Statistics Collector': '运行时统计数据 / 查询和索引统计收集器',
    'Statistics / Monitoring': '运行时统计数据 / 统计监控',
    'Vacuuming / Automatic Vacuuming': '清理 / 自动清理',
    'Autovacuum': '自动清理',
    'Vacuuming / Cost-Based Vacuum Delay': '清理 / 基于代价的清理延迟',
    'Vacuuming / Default Behavior': '清理 / 默认行为',
    'Vacuuming / Freezing': '清理 / 冻结',
    'Client Connection Defaults / Statement Behavior': '客户端连接默认值 / 语句行为',
    'Client Connection Defaults / Locale and Formatting': '客户端连接默认值 / 区域和格式化',
    'Client Connection Defaults / Shared Library Preloading': '客户端连接默认值 / 共享库预载入',
    'Client Connection Defaults / Other Defaults': '客户端连接默认值 / 其他默认值',
    'Lock Management': '锁管理',
    'Version and Platform Compatibility / Previous PostgreSQL Versions': '版本和平台兼容性 / 以前的 PostgreSQL 版本',
    'Version and Platform Compatibility / Other Platforms and Clients': '版本和平台兼容性 / 其他平台和客户端',
    'Error Handling': '错误处理',
    'Preset Options': '预置选项',
    'Customized Options': '自定义选项',
    'Developer Options': '开发者选项',
}
GUC_CATEGORY_ORDER = {category: index for index, category in enumerate(GUC_CATEGORY_ZH)}


def guc_group_of(category):
    """一级分类：取 ' / ' 前的那一段；老版本几个裸名字按 GUC_GROUP_OF_BARE 归类。"""
    head = (category or '').split(' / ')[0]
    return GUC_GROUP_OF_BARE.get(head, head)


class GucVersion(models.Model):
    """一个大版本的配置参数快照概况，18 行（9.0 – 19 来自 guc.pg.center，20 由本站 devel 手册推导）。"""

    major = models.CharField(max_length=8, primary_key=True)
    label = models.TextField(blank=True, default='')
    status = models.TextField(blank=True, default='')
    support_status = models.TextField(blank=True, default='')
    # guc 仓库里的版本键（'19beta3'），20 为空。
    source_key = models.TextField(blank=True, default='')
    # 实测的服务器版本（'18.6'），20 为空。
    server_version = models.TextField(blank=True, default='')
    # 本站手册地址段：'10' … '19'，20 为 'devel'；9.x 本站没有手册，仍照实记。
    doc_slug = models.TextField(blank=True, default='')
    parameter_count = models.IntegerField(default=0)
    added_count = models.IntegerField(default=0)
    removed_count = models.IntegerField(default=0)
    default_changed_count = models.IntegerField(default=0)
    changed_count = models.IntegerField(default=0)
    reworded_count = models.IntegerField(default=0)
    # 'runtime'（pg_settings 实测）或 'documentation'（20：只有手册）。
    schema_source = models.TextField(blank=True, default='')
    # 与上一版的汇总，见 docs/guc-column.md §2；9.0 为 {}。
    transition = models.JSONField(default=dict, blank=True)
    # 版本次序只认这一列：'9.0' 与 '10' 字符串比不出先后。
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'wiki_guc_version'
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
        return '/docs/guc/changes/{}/'.format(self.major)


class GucParameter(models.Model):
    """一个配置参数（pg_settings 的一行），逐版本快照、变化记录、默认值变迁、手册坐标与
    编辑分析整份放 JSON：一个大版本才变一次，读多写少，拆表没有收益。

    热字段是最新存在版本的取值，供索引页筛选与排序；索引页查询要 defer 掉几个 JSON 列。
    """

    # 规范大小写（DateStyle、TimeZone），key 是小写形式，供不分大小写查找。
    name = models.CharField(max_length=64, primary_key=True)
    key = models.CharField(max_length=64, unique=True)
    group = models.CharField(max_length=64, blank=True, default='')
    group_slug = models.CharField(max_length=32, blank=True, default='')
    category = models.TextField(blank=True, default='')
    category_zh = models.TextField(blank=True, default='')
    vartype = models.CharField(max_length=16, blank=True, default='')
    context = models.CharField(max_length=24, blank=True, default='')
    unit = models.TextField(blank=True, default='')
    boot_val = models.TextField(null=True, blank=True)
    boot_human = models.TextField(blank=True, default='')
    short_desc = models.TextField(blank=True, default='')
    short_desc_zh = models.TextField(blank=True, default='')
    enumvals = ArrayField(models.TextField(), default=list, blank=True)
    min_val = models.TextField(blank=True, default='')
    max_val = models.TextField(blank=True, default='')
    first_version = models.CharField(max_length=8, blank=True, default='')
    last_version = models.CharField(max_length=8, blank=True, default='')
    present_in = ArrayField(models.TextField(), default=list, blank=True)
    # 实质变化（默认值、单位、上下文、类型、范围、枚举值）落地的版本，以及其中默认值变化的版本。
    changed_in = ArrayField(models.TextField(), default=list, blank=True)
    default_changed_in = ArrayField(models.TextField(), default=list, blank=True)
    # 9.0 就已存在：9.0 是收录基线，不代表首次于 9.0 引入。
    baseline = models.BooleanField(default=False)
    versions = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=list, blank=True)
    default_history = models.JSONField(default=list, blank=True)
    docs = models.JSONField(default=dict, blank=True)
    editorial = models.JSONField(default=dict, blank=True)
    intro_commit = models.JSONField(default=dict, blank=True)
    # 一级分类序 × 10000 + 子分类序 × 100 + 子分类内按名排序。
    position = models.IntegerField(default=0)
    source_rev = models.TextField(blank=True, default='')
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wiki_guc'
        ordering = ('position',)
        indexes = [
            models.Index(fields=('group_slug', 'name'), name='wiki_guc_group'),
        ]

    def __str__(self):
        return self.name

    @property
    def url(self):
        return '/docs/guc/{}/'.format(self.name)

    @property
    def group_label(self):
        return GUC_GROUP_LABEL.get(self.group, self.group)

    @property
    def eyebrow(self):
        return 'CONFIGURATION PARAMETER'

    @property
    def vartype_label(self):
        return GUC_VARTYPE_LABEL.get(self.vartype, self.vartype)

    @property
    def context_label(self):
        return GUC_CONTEXT_LABEL.get(self.context, self.context)

    @property
    def context_note(self):
        return GUC_CONTEXT_NOTE.get(self.context, '')


# ================================================================ 等待事件

# 九个规范类型，顺序沿用手册。标签与一句话在这里定义，`waitevent.TYPE_META` 只做派生。
WAITEVENT_TYPES = (
    ('Activity', '空闲等待', '服务器进程在主循环里空闲等待。'),
    ('Buffer', '缓冲区', '等待访问数据缓冲区。'),
    ('Client', '客户端', '等待客户端套接字。'),
    ('Extension', '扩展', '扩展代码中的等待。'),
    ('IO', '文件 I/O', '等待文件 I/O。'),
    ('IPC', '进程间', '等待其它进程。'),
    ('Lock', '重量级锁', '等待重量级锁。'),
    ('LWLock', '轻量级锁', '等待轻量级锁。'),
    ('Timeout', '超时', '等待超时到期。'),
)
WAITEVENT_TYPE_ORDER = {name: index for index, (name, _, _) in enumerate(WAITEVENT_TYPES)}
WAITEVENT_TYPE_LABEL = {name: label for name, label, _ in WAITEVENT_TYPES}
WAITEVENT_TYPE_BLURB = {name: blurb for name, _, blurb in WAITEVENT_TYPES}
WAITEVENT_TYPE_SLUG = {name.lower(): name for name, _, _ in WAITEVENT_TYPES}

WAITEVENT_STATUS_LABEL = {'historical': '历史版本', 'stable': '当前稳定版',
                          'preview': '预发行', 'devel': '开发版'}

# 图谱的触发路径状态：源码里能走到这个等待点的把握程度。
WAITEVENT_SOURCE_STATUS_LABEL = {'live_trigger': '实测触发', 'dynamic_trigger': '动态触发',
                                 'catalog_only': '仅定义'}


class WaitEventVersion(models.Model):
    """一个大版本的等待事件清单概况，18 行（9.0 – 9.5 没有这套机制，事件数为 0）。"""

    major = models.CharField(max_length=8, primary_key=True)
    label = models.TextField(blank=True, default='')
    status = models.TextField(blank=True, default='')
    support_status = models.TextField(blank=True, default='')
    # 本站手册地址段：'9.6' … '19'，20 为 'devel'。
    doc_slug = models.TextField(blank=True, default='')
    # 9.6 才引入 wait_event_type / wait_event 两列，9.0 – 9.5 为 False。
    has_wait_events = models.BooleanField(default=True)
    # atlas | manual | manual+upstream | upstream | none
    method = models.TextField(blank=True, default='')
    event_count = models.IntegerField(default=0)
    # 该版手册里写的原始类型标签 → 数量（9.6 是 LWLockNamed / LWLockTranche）。
    type_counts = models.JSONField(default=dict, blank=True)
    # 与上一版的汇总；9.0 – 9.5 与 9.6（机制起点）为 {}。
    transition = models.JSONField(default=dict, blank=True)
    # 版本次序只认这一列：'9.6' 与 '10' 字符串比不出先后。
    position = models.IntegerField(default=0)
    # 来源说明：文档版本、tag、抓取时间。
    notes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'wiki_waitevent_version'
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
        return WAITEVENT_STATUS_LABEL.get(self.status, self.status)

    @property
    def changes_url(self):
        return '/docs/waitevent/changes/{}/'.format(self.major)


class WaitEvent(models.Model):
    """一个等待事件的跨版本身份。

    逐版本快照、变化记录与图谱档案整份放 JSON：一个大版本才变一次，读多写少。
    `key` 是归一后的身份（`lwlock/buffermapping`），`name` 是最新出现版本的显示名。
    """

    key = models.CharField(max_length=96, primary_key=True)
    # 规范类型标签：BufferPin 归到 Buffer，LWLockNamed / LWLockTranche 归到 LWLock。
    type = models.CharField(max_length=16)
    type_slug = models.CharField(max_length=16)
    name = models.TextField()
    slug = models.TextField(blank=True, default='')
    # 其它版本用过的名字与类型标签，查找与检索都认。
    aliases = ArrayField(models.TextField(), default=list, blank=True)
    type_variants = ArrayField(models.TextField(), default=list, blank=True)
    summary = models.TextField(blank=True, default='')
    summary_zh = models.TextField(blank=True, default='')
    first_version = models.CharField(max_length=8, blank=True, default='')
    last_version = models.CharField(max_length=8, blank=True, default='')
    present_in = ArrayField(models.TextField(), default=list, blank=True)
    changed_in = ArrayField(models.TextField(), default=list, blank=True)
    versions = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=list, blank=True)
    # 图谱档案；不在图谱里的事件（9.6 – 12 独有、19 / 20 新增）为 {}。
    dossier = models.JSONField(default=dict, blank=True)
    has_dossier = models.BooleanField(default=False)
    # 类型序 × 1000 + 类型内按名。
    position = models.IntegerField(default=0)
    source_rev = models.TextField(blank=True, default='')
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wiki_waitevent'
        ordering = ('position',)
        indexes = [
            models.Index(fields=('type_slug', 'name'), name='wiki_waitevent_type'),
            models.Index(fields=('name',), name='wiki_waitevent_name'),
        ]

    def __str__(self):
        return '{}/{}'.format(self.type, self.name)

    @property
    def url(self):
        return '/docs/waitevent/{}/{}/'.format(self.type_slug, self.name)

    @property
    def type_label(self):
        return WAITEVENT_TYPE_LABEL.get(self.type, self.type)

    @property
    def eyebrow(self):
        return self.type.upper()

    @property
    def blurb(self):
        return WAITEVENT_TYPE_BLURB.get(self.type, '')

    @property
    def source_status(self):
        return (self.dossier or {}).get('source_status', '')

    @property
    def source_status_label(self):
        return WAITEVENT_SOURCE_STATUS_LABEL.get(self.source_status, self.source_status)
