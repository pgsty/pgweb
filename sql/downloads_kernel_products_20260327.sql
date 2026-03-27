BEGIN;

INSERT INTO core_organisation (
    name, approved, address, url, lastconfirmed, orgtype_id, mailtemplate, fromnameoverride
)
VALUES
    ('Amazon Web Services', TRUE, '', 'https://aws.amazon.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('Apache Cloudberry', TRUE, '', 'https://cloudberry.apache.org/', CURRENT_TIMESTAMP, 1, '', ''),
    ('Aliyun', TRUE, '', 'https://www.aliyun.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('Highgo Software', TRUE, '', 'https://www.highgo.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('Percona', TRUE, '', 'https://www.percona.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('SKAI Worldwide (formerly Bitnine)', TRUE, '', 'https://skaiworldwide.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('VMware', TRUE, '', 'https://www.vmware.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('pgEdge, Inc.', TRUE, '', 'https://www.pgedge.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('AliCloud (阿里云 Alibaba Cloud Computing)', TRUE, '', 'https://www.aliyun.com/', CURRENT_TIMESTAMP, 4, '', ''),
    ('OpenHalo', TRUE, '', 'https://www.openhalo.org/', CURRENT_TIMESTAMP, 1, '', ''),
    ('OrioleDB', TRUE, '', 'https://orioledb.com/', CURRENT_TIMESTAMP, 1, '', ''),
    ('Greenplum Database', TRUE, '', 'https://greenplum.org/', CURRENT_TIMESTAMP, 1, '', '')
ON CONFLICT (name) DO UPDATE
SET approved = EXCLUDED.approved,
    url = EXCLUDED.url,
    lastconfirmed = EXCLUDED.lastconfirmed,
    orgtype_id = EXCLUDED.orgtype_id;

INSERT INTO downloads_product (
    name, approved, url, description, price, lastconfirmed, category_id, licencetype_id, publisher_id
)
VALUES
    (
        'AgensGraph（PostgreSQL 图数据库）',
        TRUE,
        'https://www.skaiworldwide.com/product/dbms/agens_graph',
        '基于 PostgreSQL 的属性图数据库内核，支持 openCypher，并允许 SQL 与 Cypher 混合查询。它在保持 PostgreSQL 连接协议与运维方式的同时，引入图模型对象与 agtype 数据类型。适合知识图谱、关系分析、路径查询等场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'SKAI Worldwide (formerly Bitnine)')
    ),
    (
        'Babelfish（SQL Server 兼容版）',
        TRUE,
        'https://babelfishpg.org/',
        '基于 PostgreSQL 的 SQL Server 兼容内核，提供 TDS 线协议与 T-SQL 兼容能力。它允许应用继续使用 SQL Server 客户端、驱动和部分既有语句体系接入 PostgreSQL。适合 SQL Server 迁移与兼容改造场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'Amazon Web Services')
    ),
    (
        'Cloudberry（开源 MPP 数仓）',
        TRUE,
        'https://cloudberry.apache.org/',
        '源自 Greenplum 社区的开源 MPP 数据仓库内核，面向大规模并行分析场景。它继承 PostgreSQL 生态基础，并通过 MPP 架构扩展到海量数据分析与复杂查询处理。适合离线分析、数仓和 BI 负载。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'Apache Cloudberry')
    ),
    (
        'Greenplum（MPP 数据仓）',
        TRUE,
        'https://greenplum.org/',
        '面向大规模并行分析的 MPP 数据仓库，是 PostgreSQL 生态中成熟的并行数仓分支之一。它通过共享无架构将查询分发到多个节点并行执行，能够支撑大规模数据仓库与批量分析任务。适合企业级 OLAP、报表与数据集市场景。',
        '社区版免费，商业版详见官网',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '多种许可'),
        (SELECT id FROM core_organisation WHERE name = 'VMware')
    ),
    (
        'IvorySQL（Oracle 兼容版）',
        TRUE,
        'https://www.ivorysql.org/',
        '开源的 Oracle 兼容 PostgreSQL 内核，提供 Oracle 语法与 PL/SQL 兼容能力。它在 PostgreSQL 基础上增强了 Oracle 兼容特性，降低应用与数据库对象迁移成本。适合 Oracle 替代与国产化迁移场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'Highgo Software')
    ),
    (
        'openHalo（MySQL 兼容版）',
        TRUE,
        'https://www.openhalo.org/',
        '开源的 PostgreSQL 兼容分支，提供 MySQL 线协议兼容能力，便于 MySQL 应用迁移。它让部分 MySQL 应用能够在较少改造的前提下接入 PostgreSQL 内核能力，同时获得更完整的 PG 生态。适合 MySQL 向 PostgreSQL 的兼容迁移场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'OpenHalo')
    ),
    (
        'OrioleDB（云原生 OLTP 引擎）',
        TRUE,
        'https://orioledb.com/',
        '基于补丁版 PostgreSQL 的云原生存储引擎，主打更高 OLTP 性能、低膨胀与对象存储能力。它利用 PostgreSQL 可插拔存储机制重做底层数据结构，以减少写放大、表膨胀和维护成本。适合高吞吐事务型负载。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'OrioleDB')
    ),
    (
        'Percona Postgres（透明加密版）',
        TRUE,
        'https://www.percona.com/postgresql/software/postgresql-distribution',
        'Percona 提供的 PostgreSQL 增强发行版，内置 pg_tde 提供透明数据加密能力。它在尽量保持 PostgreSQL 使用习惯的前提下，补强了企业常见的数据静态加密需求。适合对合规、安全和密钥管理有明确要求的场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'Percona')
    ),
    (
        'pgEdge（多主复制版 PostgreSQL）',
        TRUE,
        'https://www.pgedge.com/',
        '面向边缘场景的分布式 PostgreSQL 发行版，基于 Spock 提供多主逻辑复制能力。它强调跨地域节点部署、低延迟就近访问与多活架构，适合边缘计算和多站点业务。常用于需要主动主动复制能力的分布式场景。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'pgEdge, Inc.')
    ),
    (
        'PolarDB for PostgreSQL（云原生分支）',
        TRUE,
        'https://www.aliyun.com/product/polardb',
        '阿里云推出的云原生 PostgreSQL 分支，提供共享存储、高可用与国产化适配能力。它围绕云上数据库场景强化了存储与计算分离、集群高可用和工程化运维能力。适合云原生数据库与企业级生产环境。',
        '免费',
        CURRENT_TIMESTAMP,
        (SELECT id FROM downloads_category WHERE catname = 'PostgreSQL 内核分支'),
        (SELECT id FROM downloads_licencetype WHERE typename = '开源软件'),
        (SELECT id FROM core_organisation WHERE name = 'Aliyun')
    )
ON CONFLICT (name) DO UPDATE
SET approved = EXCLUDED.approved,
    url = EXCLUDED.url,
    description = EXCLUDED.description,
    price = EXCLUDED.price,
    lastconfirmed = EXCLUDED.lastconfirmed,
    category_id = EXCLUDED.category_id,
    licencetype_id = EXCLUDED.licencetype_id,
    publisher_id = EXCLUDED.publisher_id;

DELETE FROM downloads_product
WHERE name = 'PolarDB for Oracle（Oracle 兼容版）';

COMMIT;
