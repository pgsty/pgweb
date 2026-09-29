"""Reviewed scope descriptions; inventories and strategies are discovered from source."""
# Internal plan tags remain identities; text EXPLAIN strategies/modifiers do not
# create duplicate nodes. Values: category, role, inputs, output.
NODES = {
    'Result': ('Control', 'Evaluates a projection and an optional one-time condition, with or without an input plan.', 'Optional child plan', 'Projected tuples'),
    'ProjectSet': ('Control', 'Evaluates set-returning expressions in the target list for rows from its child.', 'One child plan', 'Expanded result tuples'),
    'ModifyTable': ('Modification', 'Performs the data-modification operation selected by the plan and produces RETURNING rows when requested.', 'Modification input plan or plans', 'RETURNING tuples when requested'),
    'Append': ('Combination', 'Visits its child plans and combines their rows.', 'Multiple child plans', 'Combined tuples'),
    'MergeAppend': ('Combination', 'Merges sorted child streams while preserving the required ordering.', 'Multiple sorted child plans', 'Merged ordered tuples'),
    'RecursiveUnion': ('Combination', 'Executes the non-recursive and recursive terms of a recursive union using working and intermediate tables.', 'Non-recursive and recursive child plans', 'Recursive query tuples'),
    'BitmapAnd': ('Bitmap', 'Intersects bitmaps produced by its child plans.', 'Bitmap-producing child plans', 'Tuple-location bitmap, not a tuple stream'),
    'BitmapOr': ('Bitmap', 'Unions bitmaps produced by its child plans.', 'Bitmap-producing child plans', 'Tuple-location bitmap, not a tuple stream'),
    'NestLoop': ('Join', 'Rescans the inner plan for outer rows and evaluates the join qualifications.', 'Outer and inner child plans', 'Joined tuples according to the selected join type'),
    'MergeJoin': ('Join', 'Joins ordered input streams using merge clauses.', 'Ordered outer and inner child plans', 'Joined tuples according to the selected join type'),
    'HashJoin': ('Join', 'Probes a hash table built from its inner input while reading its outer input.', 'Outer child and inner Hash plan', 'Joined tuples according to the selected join type'),
    'SeqScan': ('Scan', 'Reads a relation through a sequential scan and applies its scan qualifications.', 'A relation', 'Qualified relation tuples'),
    'SampleScan': ('Scan', 'Reads a relation using the selected table-sampling method.', 'A relation and sampling method', 'Sampled tuples'),
    'IndexScan': ('Scan', 'Uses an index to identify table tuples and fetches them from the relation.', 'An index and its relation', 'Qualified table tuples'),
    'IndexOnlyScan': ('Scan', 'Uses index values for the result and checks tuple visibility, visiting the heap when the visibility map does not suffice.', 'An index, relation and visibility information', 'Qualified tuples from index values'),
    'BitmapIndexScan': ('Bitmap', 'Scans an index and produces a bitmap of matching tuple locations.', 'An index', 'Tuple-location bitmap, not a tuple stream'),
    'BitmapHeapScan': ('Scan', 'Visits heap pages selected by a bitmap and performs required rechecks.', 'A tuple-location bitmap and relation', 'Qualified heap tuples'),
    'TidScan': ('Scan', 'Fetches table tuples using tuple identifiers.', 'A relation and tuple identifiers', 'Selected table tuples'),
    'TidRangeScan': ('Scan', 'Scans a relation over a range of tuple identifiers.', 'A relation and tuple-identifier bounds', 'Selected table tuples'),
    'SubqueryScan': ('Scan', 'Scans the output of a subquery plan.', 'A subquery child plan', 'Subquery result tuples'),
    'FunctionScan': ('Scan', 'Scans table-function results from a FROM clause.', 'One or more table functions', 'Function result tuples'),
    'TableFuncScan': ('Scan', 'Scans the rows produced by a table function such as XMLTABLE.', 'A table-function expression', 'Table-function result tuples'),
    'ValuesScan': ('Scan', 'Evaluates and scans a VALUES row list.', 'A list of row expressions', 'VALUES tuples'),
    'CteScan': ('Scan', 'Reads the shared tuplestore of a common-table-expression plan, asking that plan for more rows when needed.', 'A CTE plan and shared tuplestore', 'CTE result tuples'),
    'NamedTuplestoreScan': ('Scan', 'Scans a named tuplestore registered in the query environment.', 'A named tuplestore', 'Stored tuples'),
    'WorkTableScan': ('Scan', 'Reads the current working table of a recursive union.', 'The recursive query working table', 'Working-table tuples'),
    'ForeignScan': ('Extensibility', 'Delegates a foreign scan or supported direct modification to the foreign-data wrapper.', 'Foreign-data wrapper plan and callbacks', 'Provider-defined scan or RETURNING tuples'),
    'CustomScan': ('Extensibility', 'Executes a plan supplied by a custom-scan provider.', 'Provider-defined plan, possibly with children', 'Provider-defined tuples'),
    'Material': ('Materialization', 'Stores its child output so the rows can be read again.', 'One child plan', 'Materialized tuples'),
    'Memoize': ('Materialization', 'Caches results from a parameterized child and reuses them when the same parameter values recur.', 'One parameterized child plan', 'Cached or newly produced child tuples'),
    'Sort': ('Ordering', 'Sorts rows from its child according to the plan sort keys.', 'One child plan', 'Sorted tuples'),
    'IncrementalSort': ('Ordering', 'Extends an existing ordering by sorting groups that share the presorted key prefix.', 'One partly ordered child plan', 'Tuples ordered by the full sort key'),
    'Group': ('Aggregation', 'Groups an ordered input stream by its grouping columns.', 'One ordered child plan', 'One tuple per group'),
    'Agg': ('Aggregation', 'Computes aggregate results using the selected grouping strategy and aggregation stage.', 'One child plan', 'Aggregate result tuples'),
    'WindowAgg': ('Aggregation', 'Evaluates window functions over ordered partitions of its child output.', 'One suitably ordered child plan', 'Tuples with window-function results'),
    'Unique': ('Combination', 'Removes adjacent duplicates from a sorted input stream.', 'One sorted child plan', 'Distinct tuples'),
    'SetOp': ('Combination', 'Implements the selected INTERSECT or EXCEPT operation using a sorted or hashed strategy.', 'Set-operation input plans', 'Set-operation result tuples'),
    'LockRows': ('Control', 'Locks rows selected by its child for row-locking clauses.', 'One child plan with row identity information', 'Locked qualifying tuples'),
    'Limit': ('Control', 'Applies the plan row-count and offset bounds to its child output.', 'One child plan', 'The selected slice of tuples'),
    'Hash': ('Join', 'Builds the hash table consumed by a hash join.', 'The hash join inner child plan', 'Hash table, not a normal tuple stream'),
    'Gather': ('Parallelism', 'Combines tuples from parallel workers and any participating leader execution.', 'One parallel child plan', 'Combined tuples without a merge-order guarantee'),
    'GatherMerge': ('Parallelism', 'Merges ordered tuple streams from parallel workers and any participating leader execution.', 'One ordered parallel child plan', 'Merged ordered tuples'),
}
GUC_HINTS = {
    'SeqScan': ['enable_seqscan'], 'IndexScan': ['enable_indexscan', 'random_page_cost'],
    'IndexOnlyScan': ['enable_indexonlyscan', 'random_page_cost'],
    'BitmapHeapScan': ['enable_bitmapscan'], 'BitmapIndexScan': ['enable_bitmapscan'],
    'TidScan': ['enable_tidscan'], 'TidRangeScan': ['enable_tidscan'],
    'NestLoop': ['enable_nestloop'], 'MergeJoin': ['enable_mergejoin'],
    'HashJoin': ['enable_hashjoin'], 'Hash': ['enable_hashjoin'],
    'Sort': ['enable_sort'], 'IncrementalSort': ['enable_incremental_sort'],
    'Memoize': ['enable_memoize'], 'Material': ['enable_material'],
    'Agg': ['enable_hashagg'], 'Gather': ['max_parallel_workers_per_gather', 'parallel_leader_participation'],
    'GatherMerge': ['enable_gathermerge', 'max_parallel_workers_per_gather'],
    'Append': ['enable_parallel_append', 'enable_async_append'],
}
COVERAGE_NOTES = [
    'Core plan-node identities come from the EXPLAIN node-name switch and are checked against executor initialization dispatch in the same source archive.',
    'Aggregate and SetOp strategies, modification operations, join types, partial/final stages, parallel and async prefixes are attributes, not separate nodes.',
    'SubPlan, InitPlan and expression nodes are relationships or expressions outside this core Plan inventory. Foreign/custom provider internals are outside the core inventory.',
    'Source descriptions and manual examples are not runtime measurements. Exact behavior depends on the plan, expressions, parameters and source build.',
]


def validate(data):
    """Check the domain-specific evidence boundary before common-topic import."""
    import re
    expected = {str(n) for n in range(10, 21)}
    inventories = data.get('inventories', {})
    if set(inventories) != expected:
        raise ValueError('Plan nodes require a complete PG10–20 inventory')
    observed = {major: set() for major in expected}
    for row in data.get('items', []):
        tags = set()
        for major, snapshot in row.get('versions', {}).items():
            tag = snapshot.get('node_tag', '').removeprefix('T_')
            tags.add(tag)
            if major not in observed or tag not in NODES or tag in observed[major]:
                raise ValueError('Unknown or duplicate plan identity')
            observed[major].add(tag)
            if snapshot.get('runtime_verified') is not False or snapshot.get('evidence_kind') != 'source and documentation':
                raise ValueError('Plan source evidence must not be marked as runtime measurement')
            release = snapshot.get('release', {})
            archive_hash = release.get('revision', '')
            if not re.fullmatch('[a-f0-9]{64}', archive_hash):
                raise ValueError('Missing plan-node source archive fingerprint')
            paths = set()
            for source in snapshot.get('sources', []):
                path = source.get('path', '')
                if not isinstance(path, str) or not re.fullmatch('[a-f0-9]{64}', source.get('sha256', '')):
                    raise ValueError('Plan sources require source-file hashes')
                paths.add(path)
                if path.startswith('src/'):
                    if source.get('archive_sha256') != archive_hash or source.get('url') != release.get('source_url'):
                        raise ValueError('Plan implementation evidence disagrees with its source build')
                else:
                    prefix = '/docs/' + ('devel' if major == '20' else major) + '/'
                    if not source.get('url', '').startswith((prefix, 'https://pg.center' + prefix)):
                        raise ValueError('Plan manual evidence must use the same version')
            required = snapshot.get('source_inventory', {})
            if set(required) != {'explain', 'executor', 'implementation'} or not set(required.values()).issubset(paths):
                raise ValueError('Plan node lacks complete EXPLAIN/executor/implementation evidence')
            for field in ('explain_names', 'strategies', 'partial_modes', 'parallel_callbacks'):
                values = snapshot.get(field)
                if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                    raise ValueError('Malformed plan attributes: ' + field)
        if len(tags) != 1:
            raise ValueError('Plan identity changed across versions')
    if any(set(inventories[major]) != tags for major, tags in observed.items()):
        raise ValueError('Plan entity coverage disagrees with the source inventory')
    return True
