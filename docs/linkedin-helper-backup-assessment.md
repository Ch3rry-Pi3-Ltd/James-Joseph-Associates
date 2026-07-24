# Linked Helper Backup Assessment

## Decision

Use only the newer backup dated 10 July 2026.

The older backup adds no unique people, public profiles, organisations, chats,
or messages. It does not need to be extracted or retained locally for the
ingestion work.

The backups were inspected directly from Dropbox in memory. No archive or
expanded SQLite database was written to local disk, and no canonical Supabase
data was changed.

## Archive Shape

- Downloaded archive: `50.91 MiB`
- Expanded SQLite database: `180.46 MiB`
- Archive members: `1` (`lh.db`)
- SQLite tables: `128`

The custom `.lhd2` extension is a ZIP-compatible Linked Helper backup containing
an SQLite database.

## Newer Backup Coverage

| Data area | Rows |
| --- | ---: |
| People | 10,862 |
| Mini profiles | 10,682 |
| Current positions | 9,987 |
| Historical positions | 73,833 |
| Person-skill links | 48,386 |
| Skills | 5,568 |
| Connections | 3,527 |
| First-degree profiles | 3,717 |
| Organisations | 17,967 |
| Chats | 12,878 |
| Messages | 18,336 |
| Emails | 166 |
| Phone numbers | 22 |

Email and phone coverage is too sparse to use either field as the main identity
key. Stable LinkedIn identifiers, LinkedIn profile URLs, and unambiguous
name-plus-current-company matches must lead reconciliation.

## Old-versus-New Comparison

| Stable entity | Newer unique | Older unique | Shared | Newer only | Older only |
| --- | ---: | ---: | ---: | ---: | ---: |
| People | 10,855 | 10,380 | 10,380 | 475 | 0 |
| Public profiles | 12,561 | 11,933 | 11,933 | 628 | 0 |
| Organisations | 17,966 | 17,390 | 17,390 | 576 | 0 |
| Chats | 11,787 | 11,187 | 11,187 | 600 | 0 |
| Messages | 7,895 | 7,816 | 7,816 | 79 | 0 |

## Supabase Reconciliation Baseline

At assessment time:

- Supabase contained `16,109` canonical people.
- `3,830` distinct populated LinkedIn URL values were available for matching.
- Only `1` Linked Helper provenance row existed, confirming the backup had not
  already been bulk imported.

Privacy-safe aggregate matching found:

- `423` people with a direct LinkedIn profile-slug match.
- `33` email matches.
- `4` phone matches.
- `261` unambiguous exact name-plus-current-company matches.
- `888` unique name-only matches that are useful as review candidates but are
  not strong enough for automatic merging.

These match groups can overlap. A dry run must apply them in priority order and
report the distinct final totals before any write.

## Matching Strategy

Apply reconciliation in this order:

1. Existing Linked Helper source-record link.
2. Stable LinkedIn public/member identifier mapped to a normalised LinkedIn
   profile URL.
3. Exact normalised LinkedIn profile URL or profile slug.
4. Exact normalised email, where unique.
5. Exact normalised phone number, where unique.
6. Exact normalised full name plus current company, only where the key is unique
   in both source and canonical data.
7. Name-only and other fuzzy matches go to review and must not merge
   automatically.
8. Create a new canonical person only when no deterministic or review candidate
   exists.

Companies should follow a similar order:

1. Existing source-record link.
2. Stable LinkedIn organisation identifier or URL.
3. Exact company domain.
4. Exact normalised company name where unambiguous.
5. Ambiguous names go to review.

Every accepted source row must retain the raw source snapshot, source hash,
backup/run identity, stable upstream identifiers, and canonical links. Rerunning
the same backup must update provenance rather than create duplicates.

## Import Scope

### First pass

Import profile and relationship data that supports Tom's operational workflows:

- person identity and LinkedIn profile
- headline and summary
- current company and title
- employment history
- skills
- connection degree and connection date
- company identity and LinkedIn organisation reference

### Separate controlled pass

Chats and messages contain personal correspondence. They can support relationship
context, but should only be imported after agreeing:

- which message types are in scope
- retention period
- visibility in the UI and MCP tools
- whether full text or a minimised summary is stored
- deletion and audit expectations

## Next Engineering Step

Build a native in-memory `.lhd2` mapper and a mandatory `--dry-run` mode. The
dry run should output only aggregate matched/new/ambiguous/skipped counts and a
separate protected review artifact. Run a small bounded sample before enabling
the full profile import.
