from django.db import connection, transaction
from django.conf import settings

import json
import os
import glob
import yaml


@transaction.atomic
def load_security_json(*, overwrite_text=None, prune_missing=None, dry_run=False):
    if overwrite_text is None:
        overwrite_text = settings.SECURITY_CVE_OVERWRITE_TEXT
    if prune_missing is None:
        prune_missing = settings.SECURITY_CVE_PRUNE_MISSING

    combined_json = list(_load_all_cve_json())
    curs = connection.cursor()
    curs.execute("""WITH t AS (
SELECT (regexp_match(cveid, '^CVE-(\\d{4}-\\d{4,5})$'))[1] AS cve, title, description, vector, fixed, component
FROM JSON_TABLE(%(j)s::json, '$[*]' COLUMNS (
  cveid text PATH '$.cveMetadata.cveId' ERROR ON EMPTY ERROR ON ERROR,
  title text PATH '$._pgcenter.title' ERROR ON EMPTY ERROR ON ERROR,
  description text PATH '$._pgcenter.description' ERROR ON EMPTY ERROR ON ERROR,
  vector text PATH '$.containers.cna.metrics[*] ? (exists(@.cvssV3_1)).cvssV3_1.vectorString' ERROR ON EMPTY ERROR ON ERROR,
  fixed text[] PATH '$.containers.cna.affected.versions[*].lessThan.number()' WITH ARRAY WRAPPER ERROR ON EMPTY ERROR ON ERROR,
  component text PATH '$.containers.cna.x_postgresql.component' DEFAULT 'core server' ON EMPTY ERROR ON ERROR
)) jt
),
cveload AS (
  MERGE INTO security_securitypatch p
  USING t ON t.cve=p.cve
  WHEN NOT MATCHED THEN
    INSERT (cve, description, details, component, public, detailslink, legacyscore, vector)
    VALUES (cve, title, description, component, true, '', '', vector)
  WHEN MATCHED AND (
    p.component IS DISTINCT FROM t.component OR
    (%(overwrite_text)s AND (p.description IS DISTINCT FROM title OR p.details IS DISTINCT FROM t.description))
  ) THEN
    UPDATE SET
      description = CASE WHEN %(overwrite_text)s THEN t.title ELSE p.description END,
      details = CASE WHEN %(overwrite_text)s THEN t.description ELSE p.details END,
      component = t.component
  WHEN NOT MATCHED BY SOURCE AND %(prune_missing)s AND cvenumber > 202500000 THEN
    DELETE
  RETURNING p.cve, merge_action() AS action, id
),
allversions AS (
  SELECT t.cve, version, core_version.id AS versionid, tree, split_part(version, '.', 2)::int AS fixedminor, COALESCE(p.id, cveload.id) AS patchid
  FROM t
  INNER JOIN LATERAL unnest(fixed) version ON true
  INNER JOIN core_version ON core_version.tree=split_part(version, '.', 1)::int
  LEFT JOIN security_securitypatch p ON t.cve=p.cve
  LEFT JOIN cveload ON t.cve=cveload.cve
),
versionload AS (
  MERGE INTO security_securitypatchversion pv
  USING allversions ON patchid=patch_id AND versionid=version_id
  WHEN MATCHED AND (fixedminor != fixed_minor) THEN
    UPDATE SET fixed_minor=fixedminor
  WHEN NOT MATCHED THEN
    INSERT (patch_id, version_id, fixed_minor)
    VALUES (patchid, versionid, fixedminor)
  WHEN NOT MATCHED BY SOURCE AND %(prune_missing)s AND patch_id IN (
    SELECT id FROM security_securitypatch WHERE cvenumber > 202500000
  ) THEN
    DELETE
  RETURNING COALESCE(cve, (SELECT cve FROM security_securitypatch WHERE id=patch_id)) AS cve,
            merge_action() AS action,
            CASE WHEN merge_action() = 'DELETE' THEN (SELECT tree::int::text FROM core_version WHERE id=version_id) ELSE tree::int::text END AS tree,
            fixed_minor
),
varnishpurge AS (
  SELECT '/support/security/CVE-' || cve || '/' AS url FROM cveload
  UNION
  SELECT '/support/security/CVE-' || cve || '/' FROM versionload
  UNION
  SELECT '/support/security/' || tree::text || '/' FROM versionload
),
summary AS (
  SELECT cve, action || ' CVE' AS what FROM cveload
  UNION ALL
  SELECT cve, action || ' version ' || tree || '.' || fixed_minor FROM versionload
  UNION ALL
  SELECT 'Purged', n|| ' urls' FROM (SELECT count(*) AS n FROM (SELECT varnish_purge(url) FROM varnishpurge)) WHERE n > 0
)
SELECT cve, array_agg(what ORDER BY what)
FROM summary
GROUP BY cve
ORDER BY 1
""", {
        'j': json.dumps(combined_json),
        'overwrite_text': overwrite_text,
        'prune_missing': prune_missing,
    })
    for cve, what in curs.fetchall():
        print("CVE-{}".format(cve))
        for w in what:
            print("   {}".format(w))

    if dry_run:
        transaction.set_rollback(True)


def _load_all_cve_json():
    translation_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        '../../data/security/cve_zh.yaml',
    ))
    with open(translation_path) as f:
        translations = yaml.safe_load(f) or {}

    for fn in glob.glob(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/security/cve/CVE-*.json'))):
        with open(fn) as f:
            # We should only have PostgreSQL entries here, but filter to be sure
            j = json.load(f)
            if j['containers']['cna']['affected'][0]['product'] == 'PostgreSQL':
                cna = j['containers']['cna']
                cveid = j['cveMetadata']['cveId']
                localized = translations.get(cveid, {})
                english_description = next(
                    description['value']
                    for description in cna['descriptions']
                    if description['lang'] == 'en'
                )
                j['_pgcenter'] = {
                    'title': localized.get('title', cna['title']),
                    'description': localized.get('description', english_description),
                }
                yield j
            else:
                print("File {} is not for PostgreSQL, it's for {}".format(fn, j['containers']['cna']['affected'][0]['product']))
