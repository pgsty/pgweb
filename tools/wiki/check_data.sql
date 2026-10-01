\set ON_ERROR_STOP on

-- Read-only acceptance for all eleven reference domains and their derived search.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';

DO $check$
DECLARE
    item record;
    total bigint;
    inconsistent bigint;
    missing text[];
    expected_urls text[];
    indexed_urls text[];
BEGIN
    SELECT count(*) INTO total FROM sqlstate;
    IF total = 0 THEN RAISE EXCEPTION 'SQLSTATE 主表为空'; END IF;
    SELECT count(*) INTO inconsistent FROM sqlstate s
        WHERE s.name_zh IS DISTINCT FROM coalesce(s.texts #>> '{zh,name}', '')
           OR s.summary_zh IS DISTINCT FROM coalesce(s.texts #>> '{zh,summary}', '')
           OR s.case_count <> jsonb_array_length(s.evidence->'cases')
           OR s.snippet_count <> (SELECT count(*) FROM jsonb_array_elements(s.evidence->'cases') c
                                   WHERE (c->>'has_snippet')::boolean)
           OR s.content_hash !~ '^[0-9a-f]{64}$'
           OR EXISTS (SELECT 1 FROM unnest(s.present_in) v
                      WHERE NOT EXISTS (SELECT 1 FROM sqlstate_version WHERE major=v));
    IF inconsistent <> 0 THEN RAISE EXCEPTION 'SQLSTATE % 条派生字段或版本身份不一致', inconsistent; END IF;
    SELECT array_agg('/wiki/sqlstate/' || sqlstate || '/' ORDER BY sqlstate) INTO expected_urls FROM sqlstate;
    SELECT array_agg(url ORDER BY url) INTO indexed_urls FROM search_searchentry WHERE source='errcode';
    IF expected_urls IS DISTINCT FROM indexed_urls THEN RAISE EXCEPTION 'SQLSTATE 检索条目不一致'; END IF;
    SELECT count(*) INTO inconsistent FROM sqlstate_class c
        WHERE c.sqlstate_count <> (SELECT count(*) FROM sqlstate s WHERE s.class_code=c.code);
    IF inconsistent <> 0 THEN RAISE EXCEPTION 'SQLSTATE 类别计数不一致'; END IF;
    SELECT count(*) INTO inconsistent FROM sqlstate_version v
        WHERE v.code_count <> (SELECT count(*) FROM sqlstate s WHERE v.major=ANY(s.present_in));
    IF inconsistent <> 0 THEN RAISE EXCEPTION 'SQLSTATE 已采样版本计数不一致'; END IF;
    RAISE NOTICE 'SQLSTATE：% 条；正文摘要、证据计数、已采样版本、类别与检索通过。', total;

    FOR item IN
        SELECT * FROM (VALUES
            ('SQL 命令', 'sqlcmd', NULL, NULL, 'sqlcmd',
             $url$'/wiki/sql/' || slug || '/'$url$),
            ('系统目录', 'catalog', 'catalog_version', 'relation_count', 'catalog',
             $url$'/wiki/catalog/' || name || '/'$url$),
            ('等待事件', 'waitevent', 'waitevent_version', 'event_count', 'wait',
             $url$'/wiki/waitevent/' || type_slug || '/' || name || '/'$url$),
            ('函数百科', 'func', 'func_version', 'function_count', 'func',
             $url$'/wiki/func/' || slug || '/'$url$),
            ('配置参数', 'guc', 'guc_version', 'parameter_count', 'guc',
             $url$'/wiki/guc/' || name || '/'$url$)
        ) AS columns(label, data_table, version_table, count_field, source_name, url_expr)
    LOOP
        EXECUTE format('SELECT count(*), array_agg(%s ORDER BY %s) FROM %I',
                       item.url_expr, item.url_expr, item.data_table)
            INTO total, expected_urls;
        IF total = 0 THEN
            RAISE EXCEPTION '%：数据表 % 为空；建表迁移不等于数据导入完成。',
                item.label, item.data_table;
        END IF;

        EXECUTE format('SELECT count(*) FROM %I WHERE content_hash !~ ''^[0-9a-f]{64}$''', item.data_table) INTO inconsistent;
        IF inconsistent <> 0 THEN RAISE EXCEPTION '%：缺少有效内容指纹', item.label; END IF;

        EXECUTE format(
            'SELECT array_agg(v::text ORDER BY v) FROM generate_series(10, 20) AS v
             WHERE NOT EXISTS (SELECT 1 FROM %I WHERE versions ? v::text)',
            item.data_table)
            INTO missing;
        IF missing IS NOT NULL THEN
            RAISE EXCEPTION '%：缺少 PG % 的数据。', item.label, missing;
        END IF;

        EXECUTE format(
            'SELECT count(*) FROM %I
             WHERE (SELECT array_agg(v ORDER BY v) FROM jsonb_object_keys(versions) AS v)
                IS DISTINCT FROM
                   (SELECT array_agg(v ORDER BY v) FROM unnest(present_in) AS v)',
            item.data_table)
            INTO inconsistent;
        IF inconsistent <> 0 THEN
            RAISE EXCEPTION '%：% 条记录的版本筛选与快照不一致。', item.label, inconsistent;
        END IF;

        IF item.version_table IS NOT NULL THEN
            EXECUTE format(
                'SELECT array_agg(v::text ORDER BY v) FROM generate_series(10, 20) AS v
                 WHERE NOT EXISTS (
                     SELECT 1 FROM %I WHERE major = v::text
                     AND %I = (SELECT count(*) FROM %I WHERE versions ? v::text))',
                item.version_table, item.count_field, item.data_table)
                INTO missing;
            IF missing IS NOT NULL THEN
                RAISE EXCEPTION '%：PG % 的版本汇总缺失或计数不一致。', item.label, missing;
            END IF;
        END IF;

        SELECT array_agg(url ORDER BY url) INTO indexed_urls
            FROM search_searchentry WHERE source = item.source_name;
        IF indexed_urls IS DISTINCT FROM expected_urls THEN
            RAISE EXCEPTION '%：检索条目与数据不一致，请重建对应 index_docs 索引。',
                item.label;
        END IF;
        RAISE NOTICE '%：% 条；PG 10–20 数据、版本汇总与检索条目均通过。',
            item.label, total;
    END LOOP;

    -- Lock modes keep version metadata in each row instead of a version table.
    SELECT count(*) INTO total FROM lock_mode;
    IF total <> 12 OR (SELECT count(*) FROM lock_mode WHERE scope='table') <> 8
                   OR (SELECT count(*) FROM lock_mode WHERE scope='row') <> 4 THEN
        RAISE EXCEPTION '锁百科：必须是八种表级锁与四种行级锁，共十二条。';
    END IF;
    SELECT count(*) INTO inconsistent FROM lock_mode
        WHERE content_hash !~ '^[0-9a-f]{64}$'
           OR (SELECT array_agg(v ORDER BY v) FROM jsonb_object_keys(versions) AS v)
              IS DISTINCT FROM
              (SELECT array_agg(v::text ORDER BY v::text) FROM generate_series(10, 20) AS v);
    IF inconsistent <> 0 THEN
        RAISE EXCEPTION '锁百科：% 条记录缺少有效指纹或 PG 10–20 完整版本快照。', inconsistent;
    END IF;
    SELECT array_agg(v::text ORDER BY v) INTO missing FROM generate_series(10, 20) AS v
        WHERE (SELECT count(*) FROM lock_mode WHERE versions ? v::text) <> 12;
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION '锁百科：PG % 的模式数不等于十二。', missing;
    END IF;
    SELECT count(*) INTO inconsistent FROM lock_mode mode
        CROSS JOIN LATERAL jsonb_each(mode.versions) version
        WHERE jsonb_typeof(version.value->'conflicts') IS DISTINCT FROM 'array'
           OR jsonb_typeof(version.value->'commands') IS DISTINCT FROM 'array'
           OR jsonb_typeof(version.value->'provenance') IS DISTINCT FROM 'object';
    IF inconsistent <> 0 THEN RAISE EXCEPTION '锁百科：快照缺少矩阵、命令或来源元数据。'; END IF;
    SELECT count(*) INTO inconsistent FROM lock_mode mode
        CROSS JOIN LATERAL jsonb_each(mode.versions) version
        WHERE jsonb_array_length(version.value->'conflicts') = 0
           OR jsonb_array_length(version.value->'commands') = 0
           OR jsonb_array_length(version.value->'conflicts') <>
              (SELECT count(DISTINCT edge) FROM jsonb_array_elements_text(version.value->'conflicts') edge);
    IF inconsistent <> 0 THEN RAISE EXCEPTION '锁百科：矩阵或命令为空，或冲突边重复。'; END IF;
    SELECT count(*) INTO inconsistent FROM lock_mode mode
        CROSS JOIN LATERAL jsonb_each(mode.versions) version
        CROSS JOIN LATERAL jsonb_array_elements_text(version.value->'conflicts') edge
        LEFT JOIN lock_mode other ON other.slug=edge
        WHERE other.slug IS NULL OR other.scope <> mode.scope
           OR ((other.versions->version.key->'conflicts') ? mode.slug) IS DISTINCT FROM true;
    IF inconsistent <> 0 THEN
        RAISE EXCEPTION '锁百科：% 条冲突边未知、跨作用域或不对称。', inconsistent;
    END IF;
    SELECT count(*) INTO inconsistent FROM lock_mode mode
        CROSS JOIN LATERAL jsonb_each(mode.versions) version
        CROSS JOIN LATERAL jsonb_array_elements(version.value->'commands') command
        LEFT JOIN sqlcmd reference ON reference.slug=command->>'slug'
        WHERE reference.slug IS NULL OR NOT (reference.versions ? version.key);
    IF inconsistent <> 0 THEN
        RAISE EXCEPTION '锁百科：% 个命令引用在对应版本的 SQL 命令百科中不存在。', inconsistent;
    END IF;
    SELECT array_agg('/wiki/lock/' || slug || '/' ORDER BY '/wiki/lock/' || slug || '/')
        INTO expected_urls FROM lock_mode;
    SELECT array_agg(url ORDER BY url) INTO indexed_urls FROM search_searchentry WHERE source='lock';
    IF indexed_urls IS DISTINCT FROM expected_urls THEN
        RAISE EXCEPTION '锁百科：十二个详情页与检索条目不一致，请运行 index_docs --locks。';
    END IF;
    RAISE NOTICE '锁百科：12 条；PG 10–20、8+4 模式、冲突矩阵、命令引用与检索通过。';

    -- These four domains embed source builds in each version snapshot.
    FOR item IN SELECT * FROM (VALUES
        ('扩展钩子', 'hook', 'hook'),
        ('存储参数', 'relopt', 'relopts'),
        ('预定义角色', 'predefined_role', 'role'),
        ('对象标识符类型', 'oid_type', 'oid')
    ) AS topics(label, data_table, source_name)
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', item.data_table) INTO total;
        IF total = 0 THEN RAISE EXCEPTION '%：尚未导入数据。', item.label; END IF;
        EXECUTE format(
            'SELECT count(*) FROM %I WHERE content_hash !~ ''^[0-9a-f]{64}$''
               OR jsonb_typeof(versions) IS DISTINCT FROM ''object'' OR versions = ''{}''::jsonb',
            item.data_table) INTO inconsistent;
        IF inconsistent <> 0 THEN RAISE EXCEPTION '%：指纹或版本快照无效。', item.label; END IF;
        EXECUTE format(
            'SELECT array_agg(v::text ORDER BY v) FROM generate_series(10,20) v
             WHERE NOT EXISTS (SELECT 1 FROM %I WHERE versions ? v::text)',
            item.data_table) INTO missing;
        IF missing IS NOT NULL THEN RAISE EXCEPTION '%：缺少 PG % 的数据。', item.label, missing; END IF;
        EXECUTE format(
            'SELECT count(*) FROM %I t CROSS JOIN LATERAL jsonb_each(t.versions) v
             WHERE v.value->''release''->>''major'' IS DISTINCT FROM v.key
                OR coalesce(v.value->''release''->>''revision'', '''') = ''''
                OR jsonb_typeof(v.value->''sources'') IS DISTINCT FROM ''array''
                OR v.value->''sources'' = ''[]''::jsonb',
            item.data_table) INTO inconsistent;
        IF inconsistent <> 0 THEN RAISE EXCEPTION '%：来源或构建身份无效。', item.label; END IF;
        EXECUTE format('SELECT array_agg(%L || slug || ''/'' ORDER BY %L || slug || ''/'') FROM %I',
            '/wiki/' || item.source_name || '/', '/wiki/' || item.source_name || '/', item.data_table)
            INTO expected_urls;
        SELECT array_agg(url ORDER BY url) INTO indexed_urls
            FROM search_searchentry WHERE source=item.source_name;
        IF indexed_urls IS DISTINCT FROM expected_urls THEN
            RAISE EXCEPTION '%：检索条目与数据不一致，请运行 index_docs --topics。', item.label;
        END IF;
        RAISE NOTICE '%：% 条；PG 10–20、来源身份与检索通过。', item.label, total;
    END LOOP;
END
$check$;

-- The eighteen expansion tables share ReferenceTopic's storage contract.
-- Compare full URL sets so matching totals cannot hide missing/duplicate rows.
DO $expansion$
DECLARE
    item record;
    total bigint;
    inconsistent bigint;
    expected_urls text[];
    indexed_urls text[];
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('type','data_type','type'), ('indexam','index_am','am'),
        ('plan','plan_node','plan'), ('operator','pg_operator_entry','operator'),
        ('opclass','operator_class','opclass'), ('fdw','foreign_data_wrapper','fdw'),
        ('tableam','table_am','tableam'), ('psql','psql_command','psql'),
        ('tool','command_tool','tool'), ('conn','connection_parameter','conn'),
        ('metric','statistics_metric','metric'), ('storage','storage_structure','storage'),
        ('protocol','protocol_message','protocol'), ('language','procedural_language','language'),
        ('fts','text_search_component','fts'), ('auth','authentication_method','auth'),
        ('locale','collation_encoding','locale'), ('decode','logical_decoding_plugin','decode')
    ) AS topics(source_name,data_table,search_kind)
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', item.data_table) INTO total;
        IF total = 0 THEN RAISE EXCEPTION '%: empty expansion collection', item.source_name; END IF;
        EXECUTE format('SELECT count(*) FROM %I
            WHERE content_hash !~ ''^[0-9a-f]{64}$'' OR name='''' OR category='''' OR summary=''''
               OR jsonb_typeof(versions) IS DISTINCT FROM ''object'' OR versions=''{}''::jsonb',
            item.data_table) INTO inconsistent;
        IF inconsistent <> 0 THEN
            RAISE EXCEPTION '%: invalid fingerprint, definition or version object', item.source_name;
        END IF;
        EXECUTE format('SELECT count(*) FROM %I t CROSS JOIN LATERAL jsonb_each(t.versions) v
            WHERE v.key !~ ''^[0-9]+(\.[0-9]+)?$'' OR jsonb_typeof(v.value) IS DISTINCT FROM ''object''
               OR v.value=''{}''::jsonb', item.data_table) INTO inconsistent;
        IF inconsistent <> 0 THEN RAISE EXCEPTION '%: invalid version snapshot', item.source_name; END IF;
        EXECUTE format('SELECT array_agg(%L || slug || ''/'' ORDER BY %L || slug || ''/'') FROM %I',
            '/wiki/' || item.source_name || '/', '/wiki/' || item.source_name || '/', item.data_table)
            INTO expected_urls;
        SELECT array_agg(url ORDER BY url) INTO indexed_urls FROM search_searchentry WHERE source=item.source_name;
        IF expected_urls IS DISTINCT FROM indexed_urls THEN
            RAISE EXCEPTION '%: expansion search coverage mismatch', item.source_name;
        END IF;
        EXECUTE format('SELECT count(*) FROM %I t JOIN search_searchentry s ON s.url=%L || t.slug || ''/''
            WHERE s.source=%L AND (s.name IS DISTINCT FROM t.name OR s.kind<>%L
                OR s.entity_key='''' OR s.vector IS NULL OR s.document_id IS NOT NULL OR s.version IS NOT NULL)',
            item.data_table, '/wiki/' || item.source_name || '/', item.source_name, item.search_kind)
            INTO inconsistent;
        IF inconsistent <> 0 THEN RAISE EXCEPTION '%: expansion search projection mismatch', item.source_name; END IF;
        RAISE NOTICE '%: % entities; version objects and complete search coverage passed.', item.source_name, total;
    END LOOP;

    -- core_version uses decimal 9.x trees and zero for the current devel tree.
    -- The development major follows the highest numbered branch in this inventory.
    IF (SELECT count(*) FROM core_version WHERE tree=0) <> 1 THEN
        RAISE EXCEPTION 'Versions: expected one development tree';
    END IF;
    WITH branches AS (
        SELECT CASE WHEN tree=0 THEN (SELECT max(tree)::integer + 1 FROM core_version)
                    ELSE tree END AS branch FROM core_version
    )
    SELECT array_agg('/wiki/versions/' || CASE WHEN branch>=10 THEN branch::integer::text
                     ELSE branch::numeric(3,1)::text END || '/' ORDER BY
                     '/wiki/versions/' || CASE WHEN branch>=10 THEN branch::integer::text
                     ELSE branch::numeric(3,1)::text END || '/') INTO expected_urls FROM branches;
    SELECT array_agg(url ORDER BY url) INTO indexed_urls FROM search_searchentry WHERE source='versions';
    IF expected_urls IS DISTINCT FROM indexed_urls THEN RAISE EXCEPTION 'Versions: search coverage mismatch'; END IF;
    IF EXISTS (SELECT 1 FROM search_searchentry WHERE source='versions' AND
        (kind <> 'version' OR entity_key IS DISTINCT FROM 'version:' || split_part(url,'/',4)
         OR name IS DISTINCT FROM 'PostgreSQL ' || split_part(url,'/',4)
         OR vector IS NULL OR document_id IS NOT NULL OR version IS NOT NULL)) THEN
        RAISE EXCEPTION 'Versions: search identity/vector mismatch';
    END IF;
    RAISE NOTICE 'Versions: % branches; complete search coverage passed.', cardinality(expected_urls);
END
$expansion$;

ROLLBACK;
