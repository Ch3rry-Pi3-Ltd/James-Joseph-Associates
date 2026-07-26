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

## Campaign And Classification Signals

A read-only aggregate inspection of the newer backup found:

| Signal | Coverage |
| --- | ---: |
| Campaigns | 124 |
| Person-campaign history rows | 23,759 |
| Distinct people in campaign history | 9,336 of 10,862 (85.95%) |
| Action-target rows | 37,025 |
| Distinct action-target people | 10,264 of 10,862 (94.50%) |
| Tags / person-tag rows | 0 / 0 |
| Collections / current person memberships | 323 / 18 |

The populated campaign names overwhelmingly describe vacancy and candidate
sourcing searches, including role, client, technology, market, and `tw` vacancy
references. Examples include Rust, C++ trading-platform, DeFi engineering,
actuarial, pricing, and trust-officer searches. The only populated current
collection is an internal skipped-person list, so collections and tags do not
provide useful business classification.

Campaign membership is therefore useful evidence that a person was sourced for
a particular vacancy or talent search. The agreed import policy now treats all
native Linked Helper profiles as candidates, while retaining campaign, role,
skill, client, and vacancy signals as provenance for later graph edges. A
deterministic person match updates that person's existing candidate record; a
new person receives a new candidate record. Ambiguous identities remain
unwritten.

Job title and seniority remain useful for derived `likely_hiring_manager` and
`likely_recruitment_contact` classifications. These should carry confidence and
supporting evidence because a manager or director can also be a candidate.
Campaign labels containing managerial titles are not automatically
hiring-manager campaigns; many are searches for candidates to fill managerial
roles.

The next classification slice should:

1. Preserve campaign identity and person-campaign membership as provenance.
2. Parse role, technology, client, market, connection-degree, and `tw` vacancy
   signals from campaign labels.
3. Store derived classifications separately from confirmed candidate/contact
   roles.
4. Make confidence and evidence available to graph retrieval and operator
   review.
5. Keep chats and message bodies outside this pass.

## Implemented Read-Only Tooling

The native `.lhd2` mapper now:

- opens the ZIP-compatible backup and SQLite database in memory
- maps bounded person slices without extracting the database to local disk
- maps bounded organisation slices with stable LinkedIn organisation IDs,
  domains, websites, size, location, and source metadata
- preserves stable upstream IDs, LinkedIn identifiers, contact details, current
  role, employment history, skills, and connection metadata
- emits `candidate` payloads under the agreed native-backup import policy

The mandatory `--dry-run` command supports `people`, `companies`, or both.
People are reconciled against existing canonical source links, LinkedIn
profiles, unique emails, unique phones, and unique name-plus-company keys.
Companies are reconciled against source links, LinkedIn organisation identity,
domain, and unique normalised name.

Name uniqueness is calculated across the entire Linked Helper backup, not only
the bounded slice being inspected. This prevents a duplicate identity elsewhere
in the backup from being treated as an automatic match. The command reports
aggregate matched/new/ambiguous/skipped counts and performs zero canonical
writes.

Two bounded live samples were run against Supabase:

| Backup offset | Profiles | Matched | New | Ambiguous | Skipped |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 100 | 0 | 100 | 0 | 0 |
| 5,000 | 100 | 4 | 94 | 2 | 0 |

All four deterministic matches in the second sample were direct normalized
LinkedIn-profile matches. Both runs reported `canonical_writes: 0`.

Two bounded company samples were also run against Supabase after applying
full-backup name-uniqueness checks:

| Backup offset | Organisations | Matched | New | Ambiguous | Skipped |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 100 | 43 | 46 | 11 | 0 |
| 5,000 | 100 | 2 | 98 | 0 | 0 |

All 45 company matches used an exact, source-unique normalised company name.
No company or person dry run wrote canonical data.

## Next Engineering Step

Review the bounded person and company reports and agree the treatment of
ambiguous rows. Only then enable a bounded, auditable write path for profiles,
companies, roles, employment history, skills, and connection metadata. Chats
and messages remain explicitly out of scope until privacy, retention, and
visibility rules are agreed.
