BEGIN;

-- Fill the downloads_product "Procedural languages" category with
-- core PLs plus additional ecosystem language handlers that were missing.

INSERT INTO core_organisation (
    name,
    approved,
    address,
    url,
    lastconfirmed,
    orgtype_id,
    mailtemplate,
    fromnameoverride
)
VALUES
    ('PLV8 Project', true, '', 'https://plv8.github.io/', now(), 1, 'default', ''),
    ('PLLua Project', true, '', 'https://pllua.github.io/pllua/', now(), 1, 'default', ''),
    ('Kasper Marstal', true, '', 'https://github.com/kaspermarstal/plprql', now(), 2, 'default', ''),
    ('PgCentral Foundation, Inc.', true, '', 'https://plrust.io/', now(), 4, 'default', ''),
    ('PL/Proxy Project', true, '', 'https://plproxy.github.io/', now(), 1, 'default', ''),
    ('PL/Julia Project', true, '', 'https://github.com/pljulia/pljulia', now(), 1, 'default', ''),
    ('PL/SWI-Prolog Project', true, '', 'https://github.com/salva/plswipl', now(), 1, 'default', ''),
    ('PLSci Project', true, '', 'https://github.com/borkdude/plsci', now(), 1, 'default', ''),
    ('PL/Scheme Project', true, '', 'https://volkan.yazi.ci/plscheme/', now(), 1, 'default', ''),
    ('pgora Project', true, '', 'https://github.com/pgoracle/pgora-osql', now(), 1, 'default', ''),
    ('Brick Abode', true, '', 'https://pldotnet.brickabode.com', now(), 4, 'default', ''),
    ('pg_typescript Project', true, '', 'https://github.com/isaacd9/pg_typescript', now(), 1, 'default', ''),
    ('Dave Cramer', true, '', 'https://github.com/davecramer/pljvm', now(), 2, 'default', ''),
    ('PL/Nim Project', true, '', 'https://github.com/luisacosta828/plnim', now(), 1, 'default', ''),
    ('PL/Haskell', true, '', 'https://github.com/greydot/pghaskell', now(), 4, 'default', '')
ON CONFLICT (name) DO UPDATE
SET
    approved = EXCLUDED.approved,
    url = EXCLUDED.url,
    lastconfirmed = EXCLUDED.lastconfirmed,
    orgtype_id = core_organisation.orgtype_id;

WITH products(name, publisher_name, url, description) AS (
    VALUES
        (
            'PL/pgSQL',
            'PostgreSQL Global Development Group',
            'https://www.postgresql.org/docs/current/plpgsql.html',
            'PostgreSQL 内置的原生过程语言，支持控制流、异常处理、游标、触发器以及过程/函数开发，是最常用的数据库端编程语言。'
        ),
        (
            'PL/Tcl',
            'PostgreSQL Global Development Group',
            'https://www.postgresql.org/docs/current/pltcl.html',
            'PostgreSQL 内置的 Tcl 过程语言，支持以 Tcl 编写函数、触发器和数据库逻辑，并提供受信任与非受信任变体。'
        ),
        (
            'PL/Perl',
            'PostgreSQL Global Development Group',
            'https://www.postgresql.org/docs/current/plperl.html',
            'PostgreSQL 内置的 Perl 过程语言，支持使用 Perl 编写函数和触发器，并提供受信任与非受信任变体及类型转换支持。'
        ),
        (
            'PL/Python',
            'PostgreSQL Global Development Group',
            'https://www.postgresql.org/docs/current/plpython.html',
            'PostgreSQL 内置的 Python 过程语言，当前常见实现为 PL/Python3U，适合在数据库内编写函数、触发器和数据处理逻辑。'
        ),
        (
            'PL/V8',
            'PLV8 Project',
            'https://plv8.github.io/',
            '基于 Google V8 的 PostgreSQL JavaScript 过程语言，可用 JavaScript 编写函数、触发器和数据库内业务逻辑。'
        ),
        (
            'PL/JS',
            'PLV8 Project',
            'https://github.com/plv8/pljs',
            '轻量级可信 JavaScript 过程语言扩展，使用 QuickJS 运行时，为 PostgreSQL 提供紧凑而快速的 JS 存储过程支持。'
        ),
        (
            'PL/Lua',
            'PLLua Project',
            'https://pllua.github.io/pllua/',
            '将 Lua 嵌入 PostgreSQL 的过程语言模块，支持使用 Lua 或 LuaJIT 编写数据库函数与触发器，并提供 trusted/untrusted 变体。'
        ),
        (
            'PL/PRQL',
            'Kasper Marstal',
            'https://github.com/kaspermarstal/plprql',
            '允许在 PostgreSQL 中使用 PRQL 编写函数与存储过程，并将 PRQL 编译为 SQL 执行，适合复杂分析查询逻辑。'
        ),
        (
            'PL/TLE',
            'Amazon Web Services',
            'https://github.com/aws/pg_tle',
            'Trusted Language Extensions for PostgreSQL（pg_tle）框架，可让开发者在受限文件系统环境中以可信语言封装、安装和分发扩展。'
        ),
        (
            'PL/Rust',
            'PgCentral Foundation, Inc.',
            'https://plrust.io/',
            'Rust 过程语言处理器，可将 Rust 函数编译为原生机器码在 PostgreSQL 内执行，兼顾性能、安全性与 SPI 访问能力。'
        ),
        (
            'PL/Prolog',
            'PL/SWI-Prolog Project',
            'https://github.com/salva/plswipl',
            '基于 SWI-Prolog 的 PostgreSQL 过程语言，可在数据库中以 Prolog 谓词形式实现函数逻辑；当前仍偏实验性。'
        ),
        (
            'PL/Proxy',
            'PL/Proxy Project',
            'https://plproxy.github.io/',
            '面向 PostgreSQL 到 PostgreSQL 远程过程调用的语言处理器，支持集群路由、并行执行以及分片场景。'
        ),
        (
            'PL/XSLT',
            'Peter Eisentraut',
            'https://github.com/petere/plxslt',
            '允许直接使用 XSLT 编写 PostgreSQL 存储过程，适合 XML 文档转换与基于样式表的数据库处理逻辑。'
        ),
        (
            'PL/Scheme',
            'PL/Scheme Project',
            'https://volkan.yazi.ci/plscheme/',
            '基于 Guile 的 PostgreSQL Scheme 过程语言处理器，可用 Scheme 编写函数与数据库逻辑；项目目前已停止维护。'
        ),
        (
            'PL/Clojure',
            'PLSci Project',
            'https://github.com/borkdude/plsci',
            '基于 SCI 的实验性 Clojure 过程语言处理器，可在 PostgreSQL 内执行 Clojure 代码与函数逻辑。'
        ),
        (
            'PL/.NET',
            'Brick Abode',
            'https://pldotnet.brickabode.com',
            '为 PostgreSQL 引入 C# 与 F# 存储过程支持，覆盖函数、过程、触发器、SRF 以及 SPI 访问等常见 PL 能力。'
        ),
        (
            'PL/TypeScript',
            'pg_typescript Project',
            'https://github.com/isaacd9/pg_typescript',
            '基于 Deno API 与 V8 的 TypeScript 过程语言扩展，支持直接以 TypeScript、async/await 和 npm 生态编写 PostgreSQL 函数。'
        ),
        (
            'PL/Julia',
            'PL/Julia Project',
            'https://github.com/pljulia/pljulia',
            '为 PostgreSQL 提供 Julia 语言处理器，可用 Julia 编写数据库函数；当前仍处于持续开发阶段。'
        ),
        (
            'PL/Nim',
            'PL/Nim Project',
            'https://github.com/luisacosta828/plnim',
            '允许以 Nim 语言编写 PostgreSQL 函数与过程，强调静态类型、安全约束以及自动类型映射。'
        ),
        (
            'PL/SQL',
            'pgora Project',
            'https://github.com/pgoracle/pgora-osql',
            '提供 Oracle PL/SQL 兼容的 PostgreSQL 过程语言实现，便于兼容或迁移依赖 PL/SQL 的数据库逻辑。'
        ),
        (
            'PL/Haskell',
            'PL/Haskell',
            'https://github.com/greydot/pghaskell',
            '使用 Haskell 编写 PostgreSQL 过程函数的语言处理器项目，面向函数式数据库编程场景；项目仍偏实验性。'
        ),
        (
            'PL/JVM',
            'Dave Cramer',
            'https://github.com/davecramer/pljvm',
            '通过 RPC 机制将 PostgreSQL 函数调用转发到任意 JVM 语言运行时的可信语言执行引擎。'
        )
)
INSERT INTO downloads_product (
    name,
    approved,
    url,
    description,
    price,
    lastconfirmed,
    category_id,
    licencetype_id,
    publisher_id
)
SELECT
    p.name,
    true,
    p.url,
    p.description,
    '免费',
    now(),
    4,
    1,
    o.id
FROM products p
JOIN core_organisation o
  ON o.name = p.publisher_name
ON CONFLICT (name) DO UPDATE
SET
    approved = EXCLUDED.approved,
    url = EXCLUDED.url,
    description = EXCLUDED.description,
    price = EXCLUDED.price,
    lastconfirmed = EXCLUDED.lastconfirmed,
    category_id = EXCLUDED.category_id,
    licencetype_id = EXCLUDED.licencetype_id,
    publisher_id = EXCLUDED.publisher_id;

COMMIT;
