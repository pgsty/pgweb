\set ON_ERROR_STOP on

-- Read-only deployment acceptance for the PG10-20 encyclopedia data and search.
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
    FOR item IN
        SELECT * FROM (VALUES
            ('SQL 命令', 'wiki_sqlcmd', NULL, NULL, 'sqlcmd',
             $url$'/docs/sql/' || slug || '/'$url$),
            ('系统目录', 'wiki_catalog', 'wiki_catalog_version', 'relation_count', 'catalog',
             $url$'/docs/catalog/' || name || '/'$url$),
            ('等待事件', 'wiki_waitevent', 'wiki_waitevent_version', 'event_count', 'wait',
             $url$'/docs/waitevent/' || type_slug || '/' || name || '/'$url$),
            ('函数百科', 'wiki_func', 'wiki_func_version', 'function_count', 'func',
             $url$'/docs/func/' || slug || '/'$url$),
            ('配置参数', 'wiki_guc', 'wiki_guc_version', 'parameter_count', 'guc',
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

