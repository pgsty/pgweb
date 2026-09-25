\set ON_ERROR_STOP on

-- Read-only acceptance for all six reference domains and their derived search.
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
    SELECT array_agg('/docs/sqlstate/' || sqlstate || '/' ORDER BY sqlstate) INTO expected_urls FROM sqlstate;
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
             $url$'/docs/sql/' || slug || '/'$url$),
            ('系统目录', 'catalog', 'catalog_version', 'relation_count', 'catalog',
             $url$'/docs/catalog/' || name || '/'$url$),
            ('等待事件', 'waitevent', 'waitevent_version', 'event_count', 'wait',
             $url$'/docs/waitevent/' || type_slug || '/' || name || '/'$url$),
            ('函数百科', 'func', 'func_version', 'function_count', 'func',
             $url$'/docs/func/' || slug || '/'$url$),
            ('配置参数', 'guc', 'guc_version', 'parameter_count', 'guc',
             $url$'/docs/guc/' || name || '/'$url$)
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
END
$check$;

ROLLBACK;

