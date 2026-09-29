"""Chinese editorial descriptions of PostgreSQL core hooks.

Signatures, membership, definitions and call sites are extracted from upstream
sources by build_hooks.py.  This module only supplies the Chinese explanations;
it is deliberately not the inventory used to discover hooks.
"""

# name: (Chinese short name, category, summary, description)
HOOKS = {
    'post_parse_analyze_hook': (
        '语义分析后处理', '解析与命令处理',
        '在查询完成语义分析后取得查询树。',
        '解析器把原始语法树转换为 Query 后调用此钩子，传入解析状态与已分析的查询。'
        '扩展可在此检查或记录查询，后续仍会经过重写、规划和执行；这里不是原始 SQL 文本的词法分析入口。'),
    'ProcessUtility_hook': (
        '实用命令处理', '解析与命令处理',
        '介入 DDL、事务控制等实用命令的分派。',
        'ProcessUtility 处理不走普通查询执行器的实用命令时，若此钩子已安装便把命令交给它。'
        '扩展可检查命令或增加前后处理；要继续 PostgreSQL 原有行为，需要转交先前安装的钩子或 standard_ProcessUtility。'),
    'planner_hook': (
        '查询规划入口', '查询规划',
        '接管查询规划入口，返回可执行的计划。',
        '查询即将生成 PlannedStmt 时调用此钩子。它接收分析和重写后的查询以及规划参数，返回计划语句。'
        '扩展可包装 standard_planner 来观测或调整规划过程，也可以提供自己的规划实现。'),
    'planner_setup_hook': (
        '规划器初始化', '查询规划',
        '在标准规划器开始规划子查询之前介入初始化。',
        '标准规划器建立全局规划状态后、进入子查询规划之前调用此钩子。'
        '它提供 PlannerGlobal、查询树和游标选项，便于扩展为这次规划准备状态。'),
    'planner_shutdown_hook': (
        '规划器收尾', '查询规划',
        '在标准规划器生成计划后执行收尾处理。',
        '标准规划器完成 PlannedStmt 构建后调用此钩子，并传入全局规划状态、原查询与生成的结果。'
        '扩展可利用仍可访问的规划上下文整理此次规划的附加信息。'),
    'build_simple_rel_hook': (
        '基础关系初始化', '查询规划',
        '在基础关系的规划数据结构建立后介入。',
        '规划器构建简单关系的 RelOptInfo 时调用此钩子，并提供所属 PlannerInfo 与范围表条目。'
        '扩展可以在后续路径生成前检查或补充该关系的规划信息。'),
    'get_relation_info_hook': (
        '关系规划信息', '查询规划',
        '在关系的目录与索引信息装入规划器后介入。',
        'get_relation_info 从系统目录收集表及其索引的规划信息后调用此钩子。'
        '扩展拿到关系 OID、继承标志和 RelOptInfo，可调整规划器看到的关系信息。'),
    'set_rel_pathlist_hook': (
        '关系访问路径', '查询规划',
        '在单个关系的访问路径生成阶段增补或调整路径。',
        '规划器为关系准备访问路径时调用此钩子，传入关系、范围表下标及范围表条目。'
        '扩展可在普通扫描路径之外增加自己的访问路径；路径随后仍参加代价比较和计划选择。'),
    'set_join_pathlist_hook': (
        '连接访问路径', '查询规划',
        '在一对关系的连接路径生成阶段增补路径。',
        '规划器为指定的外侧关系、内侧关系及连接类型建立连接路径时调用此钩子。'
        '它同时提供目标连接关系和 JoinPathExtraData，适合扩展连接路径，而不是直接执行连接。'),
    'join_search_hook': (
        '连接顺序搜索', '查询规划',
        '替换标准的多关系连接顺序搜索。',
        '规划器选择连接顺序搜索方法时优先使用此钩子，输入是初始关系列表及需要完成的连接层数，'
        '返回连接结果的 RelOptInfo。需要保持标准搜索行为的扩展可调用 standard_join_search。'),
    'joinrel_setup_hook': (
        '连接关系初始化', '查询规划',
        '在连接关系的数据结构初始化阶段介入。',
        '规划器准备连接关系时调用此钩子，提供连接双方、特殊连接约束及限制条件列表。'
        '扩展可在连接路径计算前补充 joinrel 的规划信息。'),
    'join_path_setup_hook': (
        '连接路径准备', '查询规划',
        '在具体连接路径生成前调整连接准备信息。',
        'add_paths_to_joinrel 准备计算连接路径时调用此钩子，提供连接类型、两侧关系和 JoinPathExtraData。'
        '它位于连接路径的准备阶段，与生成阶段末尾的 set_join_pathlist_hook 是不同入口。'),
    'create_upper_paths_hook': (
        '上层查询路径', '查询规划',
        '在分组、排序等上层查询阶段增补路径。',
        '规划器建立上层关系的路径时调用此钩子，通过 UpperRelationKind 区分当前规划阶段。'
        '它提供输入关系和输出关系，扩展可向输出关系加入候选路径。PostgreSQL 11 起还传入该阶段的附加信息。'),
    'get_relation_stats_hook': (
        '表列统计信息', '统计信息与估算',
        '为选择率估算提供表列统计信息。',
        '选择率估算器读取关系属性的统计信息时可调用此钩子。'
        '钩子接收规划上下文、范围表条目、属性号和 VariableStatData；返回值说明扩展是否接管了此次统计信息获取。'),
    'get_index_stats_hook': (
        '索引表达式统计信息', '统计信息与估算',
        '为选择率估算提供索引列或表达式的统计信息。',
        '估算表达式的选择率需要读取索引统计信息时调用此钩子。'
        '扩展可以根据索引 OID 和索引属性号填充 VariableStatData，并用返回值指明是否接管此次获取。'),
    'get_attavgwidth_hook': (
        '平均属性宽度', '统计信息与估算',
        '覆盖规划器使用的属性平均宽度估算。',
        'get_attavgwidth 查询给定关系属性的平均宽度时先调用此钩子。'
        '返回正数时采用扩展提供的字节宽度；没有可用结果时继续读取 PostgreSQL 的统计信息。'),
    'ExecutorStart_hook': (
        '执行器启动', '查询执行',
        '介入执行器初始化，准备执行查询计划。',
        'ExecutorStart 在查询执行开始前调用此钩子，传入 QueryDesc 与执行标志。'
        '包装型扩展通常在此建立查询级状态，并转交先前的钩子或 standard_ExecutorStart 完成执行器初始化。'),
    'ExecutorRun_hook': (
        '执行器运行', '查询执行',
        '介入执行器取行和运行查询计划的阶段。',
        'ExecutorRun 运行已初始化的查询计划时调用此钩子。方向与行数参数影响本次执行请求；'
        '同一 QueryDesc 可能被多次运行，因此一次调用不一定代表整条查询已经结束。'),
    'ExecutorFinish_hook': (
        '执行器完成', '查询执行',
        '介入查询执行结束前的完成阶段。',
        'ExecutorFinish 在计划主体的运行完成后处理尚需完成的执行工作，例如完成写入和触发器相关工作。'
        '安装此钩子的包装型扩展应继续调用原钩子或 standard_ExecutorFinish，不能把它当作单纯的资源释放回调。'),
    'ExecutorEnd_hook': (
        '执行器结束', '查询执行',
        '介入执行器结束及查询资源释放。',
        'ExecutorEnd 负责结束一次查询并释放执行器资源。此钩子可在资源释放前读取执行状态或完成扩展自己的清理，'
        '随后转交原钩子或 standard_ExecutorEnd。'),
    'ExecutorCheckPerms_hook': (
        '执行权限检查', '权限与对象访问',
        '在核心关系权限检查之外实施附加检查。',
        '执行器进行关系权限检查时调用此钩子。返回布尔值表示附加检查是否通过，report 或 ereport_on_violation '
        '参数决定失败是否应直接报错。此入口用于额外的权限规则，不能假定它会取消核心已经执行的权限检查。'),
    'object_access_hook': (
        '对象访问事件', '权限与对象访问',
        '按对象 OID 接收创建、删除或访问等对象事件。',
        '核心在对象创建、删除、修改和访问等指定位置调用此钩子。access 表示事件种类，classId、objectId '
        '和 subId 标识对象，arg 的含义随事件变化；扩展需要按 ObjectAccessType 解读事件专有参数。'),
    'object_access_hook_str': (
        '按名称访问对象', '权限与对象访问',
        '按对象名称接收对象访问事件。',
        '这套对象访问入口以字符串名称标识对象，适用于没有普通对象 OID 的检查路径，例如配置参数的权限检查。'
        '它与按 OID 传参的 object_access_hook 类型不同，应分别安装并按事件类型处理参数。'),
    'row_security_policy_hook_permissive': (
        '宽松行安全策略', '权限与对象访问',
        '向关系补充宽松模式的行安全策略。',
        '重写器为当前命令与关系收集行安全策略时调用此钩子。返回的策略加入宽松策略集合；'
        '宽松策略之间采用 OR 组合，与限制策略一起决定哪些行可见或可写。'),
    'row_security_policy_hook_restrictive': (
        '限制行安全策略', '权限与对象访问',
        '向关系补充限制模式的行安全策略。',
        '重写器收集当前命令的行安全策略时调用此钩子，将返回结果加入限制策略集合。'
        '限制策略之间采用 AND 组合，并约束宽松策略允许的行；仅有限制策略并不会自动授予行访问权。'),
    'ClientAuthentication_hook': (
        '客户端认证结果', '认证与连接',
        '在客户端认证完成后检查认证结果。',
        '客户端认证过程结束时调用此钩子，传入连接 Port 和认证状态。'
        '扩展可据此执行附加的连接准入检查或记录认证事件；具体可访问的连接信息以对应版本的 Port 结构为准。'),
    'check_password_hook': (
        '角色密码检查', '认证与连接',
        '在创建或修改角色密码时施加密码策略。',
        '角色创建或修改命令设置密码时调用此钩子，提供用户名、密码内容、密码类型和有效期。'
        '密码可能是明文，也可能已经是散列表示；检查逻辑必须先看 PasswordType，不能一律按明文密码处理。'),
    'ldap_password_hook': (
        'LDAP 绑定密码转换', '认证与连接',
        '在 LDAP 搜索绑定之前转换配置的绑定密码。',
        'LDAP 认证需要执行搜索绑定时，把配置的 ldapbindpasswd 交给此钩子，再使用返回的字符串执行绑定。'
        '默认实现原样返回密码，扩展可提供自己的转换逻辑；它处理的是目录服务绑定密码，不是客户端登录密码。'),
    'openssl_tls_init_hook': (
        'OpenSSL 上下文初始化', '认证与连接',
        '在服务器初始化 TLS 上下文时调整 OpenSSL 设置。',
        '服务器建立 OpenSSL SSL_CTX 时调用此钩子，并通过 isServerStart 区分服务器启动和之后的重载。'
        '默认实现执行 PostgreSQL 的 TLS 初始化工作；自定义实现需要核对默认实现承担的职责，避免遗漏必要设置。'),
    'ExplainOneQuery_hook': (
        '单条查询的 EXPLAIN', '执行计划说明',
        '接管单条查询的 EXPLAIN 处理入口。',
        'EXPLAIN 准备解释一条查询时，若此钩子已安装便交由扩展处理。'
        '参数包含查询树、ExplainState 和查询上下文，扩展可据此包装或替换该条查询的计划说明过程。'),
    'explain_get_index_name_hook': (
        'EXPLAIN 索引名称', '执行计划说明',
        '为执行计划中的索引提供显示名称。',
        'EXPLAIN 输出索引名称前调用此钩子，以索引 OID 查询扩展提供的名称。'
        '返回空指针时继续使用核心的名称查找路径；这为规划阶段构造的特殊索引对象提供显示入口。'),
    'explain_per_plan_hook': (
        'EXPLAIN 计划附加信息', '执行计划说明',
        '向每份执行计划补充 EXPLAIN 输出。',
        'EXPLAIN 输出一份计划时调用此钩子，提供计划语句、ExplainState 和相关查询上下文。'
        '扩展可为整份计划加入附加信息，无需接管整个 ExplainOneQuery 流程。'),
    'explain_per_node_hook': (
        'EXPLAIN 节点附加信息', '执行计划说明',
        '向单个执行计划节点补充 EXPLAIN 输出。',
        'EXPLAIN 展示单个计划节点时调用此钩子，传入 PlanState、祖先节点和节点所在关系的显示信息。'
        '扩展可在当前节点的输出分组中增加属性。'),
    'explain_validate_options_hook': (
        'EXPLAIN 选项校验', '执行计划说明',
        '在 EXPLAIN 的选项解析后校验扩展选项。',
        'EXPLAIN 完成选项处理后调用此钩子，让扩展检查当前 ExplainState、原始选项列表和解析上下文。'
        '它用于跨选项约束或扩展自己的校验规则，不是查询计划的执行入口。'),
    'shmem_request_hook': (
        '共享内存需求申报', '启动与共享内存',
        '在共享内存分配前申报扩展的内存与锁需求。',
        '服务器处理预加载模块的共享内存需求时调用此钩子。'
        '扩展可在这里调用 RequestAddinShmemSpace 和 RequestNamedLWLockTranche，申报后续初始化所需的空间和轻量锁。'),
    'shmem_startup_hook': (
        '共享内存初始化', '启动与共享内存',
        '在核心共享内存完成初始化后初始化扩展状态。',
        '服务器建立共享内存并完成核心结构初始化后调用此钩子。'
        '预加载扩展可在这里创建或连接自己的共享内存结构；这与分配前申报空间需求的阶段不同。'),
    'emit_log_hook': (
        '服务器日志输出', '日志与函数调用',
        '在错误或日志消息写入服务器日志之前介入。',
        '消息准备发送到服务器日志时调用此钩子，传入 ErrorData。'
        '扩展可检查消息或调整服务器日志输出标志；该入口并不等同于客户端消息输出接口。'),
    'needs_fmgr_hook': (
        '函数调用追踪筛选', '日志与函数调用',
        '决定给定函数是否需要进入 fmgr 调用追踪。',
        '函数管理器准备函数调用信息时，用此钩子根据函数 OID 判断是否启用 fmgr_hook。'
        '它负责选择需要追踪的函数，实际的进入、退出与异常事件由 fmgr_hook 接收。'),
    'fmgr_hook': (
        '函数调用事件', '日志与函数调用',
        '接收被选中函数的调用开始、正常结束和异常事件。',
        '对 needs_fmgr_hook 选中的函数，函数管理器通过此钩子报告调用事件。'
        'FmgrHookEventType 区分进入、正常返回和异常退出，FmgrInfo 标识被调用函数，private 指针可保存扩展状态。'),
}


def notes_for(name, major):
    """Small version-specific caveats; the actual interface is always extracted."""
    notes = []
    if name in {'planner_hook', 'ExecutorStart_hook', 'ExecutorRun_hook',
                'ExecutorFinish_hook', 'ExecutorEnd_hook', 'ProcessUtility_hook'}:
        notes.append(dict(title='串接已有钩子', paragraphs=[
            '钩子变量只保存一个函数指针。扩展安装时应保存旧值；需要保留原行为时先调用旧钩子，'
            '旧值为空则调用相应的 standard_ 实现。直接再次调用同名公共入口可能重新进入自己的钩子。']))
    if name == 'post_parse_analyze_hook':
        notes.append(dict(title='版本差异', paragraphs=[
            'PostgreSQL 14 起的接口包含 JumbleState 参数；较早版本只传入 ParseState 和 Query。'
            '请以所选构建的接口签名为准。']))
    if name == 'ExecutorRun_hook':
        notes.append(dict(title='版本差异', paragraphs=[
            'PostgreSQL 18 起的接口不再包含 execute_once 参数；跨版本扩展需要按目标版本适配。']))
    if name == 'ExecutorCheckPerms_hook':
        notes.append(dict(title='版本差异', paragraphs=[
            'PostgreSQL 16 起，权限信息通过单独的 RTEPermissionInfo 列表传递；'
            '较早版本由范围表条目承载。不要只按参数个数移植权限检查。']))
    if name == 'shmem_request_hook':
        notes.append(dict(title='加载阶段', paragraphs=[
            '这类初始化需要在服务器启动时生效，通常由 shared_preload_libraries 加载的模块安装。'
            '申报资源与初始化资源是两个阶段，应与 shmem_startup_hook 配合。']))
    if name == 'shmem_startup_hook':
        notes.append(dict(title='共享状态的并发保护', paragraphs=[
            '多个后端连接同一共享结构时必须按该结构的设计使用合适的锁，并检查 ShmemInitStruct '
            '返回的 found 标志，避免把已存在的共享状态重新初始化。']))
    return notes


def related_for(name, major):
    links = []
    manual = 'devel' if major == '20' else major
    if name.startswith('Executor'):
        links.append(dict(label='执行器', url=f'/docs/{manual}/executor.html'))
    elif HOOKS[name][1] in {'查询规划', '统计信息与估算'}:
        links.append(dict(label='规划器与优化器', url=f'/docs/{manual}/planner-optimizer.html'))
    elif HOOKS[name][1] == '执行计划说明':
        links.append(dict(label='EXPLAIN', url=f'/wiki/sql/explain/?v={major}'))
    elif name.startswith('row_security_'):
        links.append(dict(label='行安全策略', url=f'/docs/{manual}/ddl-rowsecurity.html'))
        links.append(dict(label='CREATE POLICY', url=f'/wiki/sql/create-policy/?v={major}'))
    elif name.startswith('shmem_'):
        links.append(dict(label='shared_preload_libraries',
                          url=f'/wiki/guc/shared_preload_libraries/?v={major}'))
    elif name == 'check_password_hook':
        links.append(dict(label='CREATE ROLE', url=f'/wiki/sql/create-role/?v={major}'))
        links.append(dict(label='ALTER ROLE', url=f'/wiki/sql/alter-role/?v={major}'))
    elif name in {'fmgr_hook', 'needs_fmgr_hook'}:
        links.append(dict(label='C 语言函数', url=f'/docs/{manual}/xfunc-c.html'))
    paired = {'needs_fmgr_hook': 'fmgr_hook', 'fmgr_hook': 'needs_fmgr_hook',
              'row_security_policy_hook_permissive': 'row_security_policy_hook_restrictive',
              'row_security_policy_hook_restrictive': 'row_security_policy_hook_permissive'}
    if int(major) >= 15:
        paired.update(shmem_request_hook='shmem_startup_hook', shmem_startup_hook='shmem_request_hook')
    if name in paired:
        other = paired[name]
        links.append(dict(label=other, url=f'/wiki/hook/{other.lower()}/?v={major}'))
    return links
