# Local center Chinese Wiki propagation

This adapter transfers the accepted Chinese reader of local Go `center` into
PGWeb's native Django Wiki snapshots. It does not connect to production or modify
the source database. The reviewed source dataset hash is explicitly pinned in
`freeze.py`; changing that pin requires a fresh audit.

The 2026-10-23 run's private evidence lives in ignored
`tmp/wiki-center-sync-20261023/`. Large source archives, generated snapshots,
database dumps and rendered pages must remain outside Git.

1. Record the worktree baseline and local database/cluster identity. Take a
   consistent custom-format `pg_dump`, restore into an unused
   `test_pgweb_wiki_center_*` database, and compare `fingerprint.py` output and
   schema dumps. Never restore with `--clean` into the live application database.
2. Use `freeze.py source` with the restricted `CENTER_DSN` and `freeze.py target`
   with the existing local Django settings. These exports are read-only. The
   source records the same definition/text precedence as the Go Chinese reader;
   choosing only the inherited pgweb archive would miss accepted corrections.
3. Call `catalogs.build`, `core.build`, and `topics.build` with the fixed source
   and target directories. These use files only and emit native snapshots. The
   topic adapter also requires its explicitly hashed Index AM replay evidence.
   `support.py` checks the already-correct related Chinese manual pages and
   freezes the two PG19 release label corrections through comparison snapshots.
4. Seal the 30 native inputs in `publication.json` with their relative paths,
   kinds and SHA256 hashes. `publish.py` validates every input before writing,
   verifies local database identity, locks publication tables, and rejects target
   drift against `--expected` fingerprints. It calls existing native importers
   inside one transaction. By default the transaction rolls back; `--write`
   commits. `--search` rebuilds only Wiki definition search sources.
5. Rehearse rollback on the isolated restore, publish there, compare all
   canonical Chinese bodies with `verify.py data`, and exercise the fixed HTTP
   plan with `verify.py http`. Verify the second native import is unchanged.
6. Optionally include a sealed `site-search` archive produced by the HTTP check.
   Its HTML is parsed and written by the existing site crawler within the same
   publication transaction; only `/wiki/` entries are included. No network crawl
   occurs during publication.
7. Publish the exact accepted snapshot to local `pgweb`, with a fresh drift
   check; rerun data, HTTP and unaffected-table checks. Preserve the complete
   backup and receipts. A local result does not imply deployment or a push.

Canonical text and its original content hash remain in `center_zh`. Verified
local URL mappings are applied separately at rendering. Measured Catalog/GUC
facts and SQLSTATE runtime records retain their actual source versions. Missing
same-version measurements are not manufactured from a neighboring version.
Historical `WAIT FOR` maps to PGWeb's established `wait` identity and redirect.
