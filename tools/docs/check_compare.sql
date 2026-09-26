-- Read-only checks for the four comparison storage tables.
SELECT key, language, revision, release_count, entry_count, content_hash, imported_at
FROM release_dataset ORDER BY key;

SELECT 'releases' AS entity, count(*) FROM release
UNION ALL SELECT 'entries', count(*) FROM release_entry
UNION ALL SELECT 'patch_groups', count(*) FROM release_patch
UNION ALL SELECT 'relations', coalesce(sum(jsonb_array_length(relations)), 0) FROM release_entry;

SELECT r.major, r.status, count(DISTINCT r.version) AS releases,
       count(e.id) AS entries
FROM release r LEFT JOIN release_entry e ON e.release_id = r.version
GROUP BY r.major, r.status ORDER BY min(r.sort_num), r.status;

-- Every violation below must be zero.
SELECT 'missing_patch' AS violation, count(*) AS count
FROM release_entry e CROSS JOIN LATERAL unnest(e.patch_ids) p(id)
LEFT JOIN release_patch target ON target.id = p.id WHERE target.id IS NULL
UNION ALL
SELECT 'missing_relation_target', count(*)
FROM release_entry e CROSS JOIN LATERAL jsonb_array_elements(e.relations) rel
LEFT JOIN release_entry target ON target.id = rel->>'target' WHERE target.id IS NULL
UNION ALL
SELECT 'same_branch_equivalent', count(*)
FROM release_entry e JOIN release source ON source.version = e.release_id
CROSS JOIN LATERAL jsonb_array_elements(e.relations) rel
JOIN release_entry other ON other.id = rel->>'target'
JOIN release target ON target.version = other.release_id
WHERE rel->>'type' = 'equivalent' AND source.major = target.major
UNION ALL
SELECT 'missing_manifest_release', count(*)
FROM release_dataset d CROSS JOIN LATERAL jsonb_array_elements(d.members) member
LEFT JOIN release r ON r.version = member->>'version'
WHERE d.kind = 'releases' AND (r.version IS NULL OR NOT d.language = ANY(r.active_languages))
UNION ALL
SELECT 'missing_manifest_entry', count(*)
FROM release_dataset d CROSS JOIN LATERAL jsonb_array_elements(d.members) member
CROSS JOIN LATERAL jsonb_array_elements_text(member->'entries') identity(id)
LEFT JOIN release_entry e ON e.id = identity.id
WHERE d.kind = 'releases' AND (e.id IS NULL OR e.release_id != member->>'version'
                              OR NOT d.language = ANY(e.active_languages))
UNION ALL
SELECT 'manifest_count_mismatch', count(*)
FROM release_dataset d WHERE d.kind = 'releases' AND (
  d.release_count != jsonb_array_length(d.members) OR
  d.entry_count != (SELECT coalesce(sum(jsonb_array_length(m->'entries')), 0)
                   FROM jsonb_array_elements(d.members) m));
