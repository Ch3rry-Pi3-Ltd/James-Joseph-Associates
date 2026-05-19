# Dropbox Source-Shape Review

This document records what we currently know about Tom's Dropbox structure
from three sources:

- Tom's own explanation of the folder meanings
- the screenshots Tom shared earlier
- live folder inspection through the working local Dropbox helper path

It is a source-shape note, not yet a final ingestion design.

## 1. Why this document exists

The Dropbox workstream has moved past abstract planning.

We now have:

- a live OAuth connection for Tom's Dropbox account
- confirmed read access
- confirmed write-capable scopes for later Outlook-to-Dropbox staging
- enough live folder inspection to stop treating Dropbox as a generic unknown

What was missing was one place that joined:

- Tom's narrative explanation
- the screenshot-based structure hints
- the real API-observed folder structure

This document fills that gap.

## 2. Tom's explanation of the structure

Tom explained the Dropbox/email side broadly as follows:

- some advert responses will be Word/DOCX, not only PDF
- the `ADV-CVR` area means "advert CVs to review"
- `tw...` folder names are job or vacancy code references
- those `tw...` references are used consistently across other sources too
- when opening the relevant advert-response subfolders, the expectation is to
  find the response email plus attached CVs
- some CVs may already exist in JobAdder and/or elsewhere in Dropbox
- `### CVR GPT - upload to JAD` is expected to overlap heavily with
  `ACHTUNG! in RFL!`

Those points materially affect ingestion design:

- DOCX support is required
- vacancy/job code may become a real reconciliation signal
- duplication is expected, not accidental
- Dropbox is not one clean CV bucket; it is a mixed operational/archive source

## 3. Screenshot-derived structure hints

Tom's screenshots suggested two important things before live API inspection:

### A. A Dominique-oriented operational folder exists

The screenshot showed a folder headed roughly as:

- `### DOMINIQUE FOLDER`

with entries such as:

- `tw394`
- `tw396`
- `tw397`
- `tw398`
- `tw399`
- `tw384 - ADV-CVR`
- `tw385 - ADV-CVR`
- `tw386 - ADV-CVR`
- `tw387 - ADV-CVR`
- `tw390 - ADV-CVR`
- `tw391 - ADV-CVR`
- `tw392 - ADV-CVR`
- `tw383 - ADV-CVR`
- `tw378 - ADV-CVR`

The visible counts implied that some vacancy buckets are small while others are
very large, especially `tw387 - ADV-CVR`.

### B. The wider Dropbox estate is segmented by workflow/archive meaning

The screenshot also showed major areas such as:

- `### BIG BAD CV ARCHIVE inc. RFL`
- `### CVR GPT - upload to JAD`
- `#################----CV's- IN-JAD-JobAdder`
- `++++++##########!ACH! CV$in - Hiring Managers to Pitch and CV sellin too!!!`

This already suggested:

- operational staging areas
- bulk archive areas
- JobAdder-adjacent document areas
- likely duplication across folders

## 4. Live Dropbox inspection results

Using Tom's saved OAuth connection and the working local Dropbox helper path,
we inspected the real Dropbox structure.

### Root-level folders observed

We were able to see root-level folders including:

- `/tom owens`
- `/NEW Dropbox`
- `/Outlook`
- `/Vault`
- `/#################----CV's- IN-JAD-JobAdder`
- `/### BIG BAD CV ARCHIVE inc. RFL`
- `/What's shared workspace`
- `/Apps`
- `/++++++##########!ACH! CV$in - Hiring Managers to Pitch and CV sellin too!!!`
- `/tw394 = YES spec@`
- `/tw394 = to CVR`
- `/### CVR GPT - upload to JAD`

There are also root-level files, not only folders.

## 5. Key folder meanings and contents

The following sections record the most relevant currently inspected folders.

### A. `CV's- IN-JAD-JobAdder`

Path:

- `/#################----CV's- IN-JAD-JobAdder`

Observed shape:

- `0` subfolders
- `581` files

Sample filenames observed:

- `Isaiah Perumalla.docx`
- multiple UUID-named PDFs

Interpretation:

- this looks like a flat document store for CVs already tied to the JobAdder
  workflow
- it is likely not the best first ingestion target for discovery, because it
  may overlap heavily with data we already have from JobAdder directly

### B. `BIG BAD CV ARCHIVE inc. RFL`

Path:

- `/### BIG BAD CV ARCHIVE inc. RFL`

Observed child folders:

- `/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive`
- `/### BIG BAD CV ARCHIVE inc. RFL/#########################IN-VINCERE!!!`
- `/### BIG BAD CV ARCHIVE inc. RFL/######## ADV&JBS-CVR-bklg`
- `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!`
- `/### BIG BAD CV ARCHIVE inc. RFL/ARCHIVE - JBS - [to export to BH]`

Interpretation:

- this is a major archive zone
- it is structurally important, but likely messy and duplication-heavy

#### B1. `ADV&JBS-CVR-bklg`

Path:

- `/### BIG BAD CV ARCHIVE inc. RFL/######## ADV&JBS-CVR-bklg`

Observed shape:

- `12` subfolders
- `0` direct files

Notable subfolders:

- `### CV's TO IMPORT PRIOR TO 21-11-22`
- `efin 21-12-22 - TO UPLOAD`
- `tw216 - 080423`
- `tw294 - 080423`
- `tw332 - GSR SRE role`
- `tw337 adv-cvr upload`

Interpretation:

- this is the strongest live Dropbox match to Tom's advert/CVR backlog
  description
- the `tw...` naming confirms the vacancy-code pattern he described
- this looks like a realistic later ingestion/reconciliation target

##### B1a. `tw337 adv-cvr upload`

Path:

- `/### BIG BAD CV ARCHIVE inc. RFL/######## ADV&JBS-CVR-bklg/tw337 adv-cvr upload`

Observed shape:

- `0` subfolders
- `4` files

Observed file types:

- `doc: 1`
- `docx: 2`
- `pdf: 1`

Sample filenames:

- `Shamsul Abdin (... - Totaljobs).docx`
- `Kevin Chan CV4.docx`
- `John Kennedy CVJK23PB_U.doc`
- `Sapna Hazel Batra CV - September 2023.pdf`

Interpretation:

- this is a compact, mixed-format advert-CVR sample
- it is a strong candidate for a narrow first file-read/download test

#### B2. `ACHTUNG! in RFL!`

Path:

- `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!`

Observed shape:

- `1` subfolder
- `5558` files

Observed characteristics:

- large flat archive
- many `.pdf` and `.docx` CV files
- many `*_cv-library.*` style names

Interpretation:

- this is a large duplication-heavy archive source
- Tom's earlier warning about overlap with `CVR GPT - upload to JAD` appears
  directionally correct
- this should not be the first bulk ingest target

### C. `CVR GPT - upload to JAD`

Path:

- `/### CVR GPT - upload to JAD`

Observed shape:

- `3` subfolders
- `1` direct file

Observed subfolders:

- `/### CVR GPT - upload to JAD/tw396`
- `/### CVR GPT - upload to JAD/tw397 - upload JAD and add to JAD dbx`
- `/### CVR GPT - upload to JAD/# powershell solution folders`

Interpretation:

- this looks like an operational staging area, not a neutral archive
- Tom's earlier warning that this area overlaps with `ACHTUNG! in RFL!` is
  plausible and should be taken seriously

#### C1. `tw396`

Path:

- `/### CVR GPT - upload to JAD/tw396`

Observed subfolders:

- `Uploa to jad and ] spec@`
- `GPT says yes check & test`
- `WIP in GPT`

Interpretation:

- this appears to represent stages in a manual or semi-manual workflow rather
  than a simple source bucket

##### C1a. `WIP in GPT`

Path:

- `/### CVR GPT - upload to JAD/tw396/WIP in GPT`

Observed shape:

- `0` subfolders
- `80` files

Observed extension breakdown:

- `pdf: 40`
- `docx: 38`
- `doc: 1`
- `txt: 1`

Interpretation:

- active staging bucket
- mixed but CV-heavy
- good place to test mixed-format extraction later
- not ideal as the first canonical source because workflow state and document
  duplication are likely mixed together

#### C2. `tw397 - upload JAD and add to JAD dbx`

Path:

- `/### CVR GPT - upload to JAD/tw397 - upload JAD and add to JAD dbx`

Observed child folder:

- `no phone or email`

##### C2a. `no phone or email`

Path:

- `/### CVR GPT - upload to JAD/tw397 - upload JAD and add to JAD dbx/no phone or email`

Observed shape:

- `0` subfolders
- `3` files

Observed file types:

- `pdf: 3`

Sample filenames:

- `DavidPollitt_2023_11a.pdf`
- `LinkedIn Resume.pdf`
- `LinkedIn Resume (1).pdf`

Interpretation:

- this is a tiny special-case queue
- likely useful later for sparse-profile/no-contact edge cases

### D. `tw394 = to CVR`

Path:

- `/tw394 = to CVR`

Observed shape:

- `0` subfolders
- `32` files

Observed extension breakdown:

- `pdf: 19`
- `docx: 13`

Sample filenames:

- `Aman-Raja_cv-library.docx`
- `Ben Greenhouse (... - Totaljobs).docx`
- `Harry James (... - Totaljobs).docx`

Interpretation:

- this is one of the cleanest narrow first targets
- flat, small enough to reason about, and already mixed-format
- strong candidate for the first real Dropbox file-read/download slice

## 6. What the folder meanings now seem to be

The current working interpretation is:

- `ADV-CVR` / `ADV&JBS-CVR-bklg`:
  advert-response / vacancy-linked CV backlog

- `tw...` folders:
  job or vacancy-code buckets that may become a useful reconciliation signal

- `CVR GPT - upload to JAD`:
  manual or semi-manual operational staging area with likely duplication

- `ACHTUNG! in RFL!`:
  large archive and likely duplication source

- `CV's- IN-JAD-JobAdder`:
  flat CV store already associated with the JobAdder process

## 7. Implications for ingestion design

The live structure supports several conclusions.

### A. Dropbox is not one homogeneous source

It contains:

- archive zones
- staging/workflow zones
- vacancy-linked CV review zones
- JobAdder-adjacent document zones

So the ingestion policy should be folder-aware, not one global rule.

### B. DOCX support matters

Tom's earlier warning was correct. Some meaningful buckets are heavily mixed
between PDF and DOCX, with some `.doc` as well.

### C. Vacancy-code linkage may become important

The `tw...` pattern appears real in both Tom's explanation and the live
structure. That should be preserved as metadata during Dropbox ingestion.

### D. Duplication should be assumed

The overlap risk between:

- `CVR GPT - upload to JAD`
- `ACHTUNG! in RFL!`
- existing JobAdder candidates/documents

is high enough that Dropbox should not be treated as a naive create-everything
source.

### E. Legacy `.doc` should not be in the first automated extraction path

The current evidence supports a conservative first-pass policy:

- the existing extraction layer supports PDF and DOCX, but not legacy `.doc`
- there is no obvious local `.doc` conversion tool installed on the current
  machine
- `.doc` appears only lightly in the first inspected target folders:
  - `0` files in `/tw394 = to CVR`
  - `1` file in `tw337 adv-cvr upload`
  - `1` file in `tw396/WIP in GPT`
- one real Dropbox `.doc` file was downloaded and failed with the expected
  unsupported-format error:
  - `The resume file format is not supported for text extraction.`

Current policy:

- PDF: automate
- DOCX: automate
- DOC: do not automate in the first pass

For now, `.doc` should be treated as:

- a staged/manual-conversion case
- or a later tooling enhancement if the volume turns out to justify it

## 8. Recommended first Dropbox ingestion targets

If we want a narrow first Dropbox file-read/download slice, the best targets
are:

1. `/tw394 = to CVR`
2. `/### BIG BAD CV ARCHIVE inc. RFL/######## ADV&JBS-CVR-bklg/tw337 adv-cvr upload`

Reasons:

- both are small enough to inspect safely
- both contain real mixed-format CV files
- both are closer to genuine advert/CVR workflow than the big flat archives

## 9. File-read proof status for the first target folders

We now have direct proof that the current Dropbox download path can feed the
existing extraction layer for the two main first-target areas.

### A. `tw394 = to CVR`

Confirmed:

- PDF download and extraction: works
- DOCX download and extraction: works
- one real DOCX file is malformed and fails cleanly as a document-quality
  issue, not a transport issue

### B. `tw337 adv-cvr upload`

Confirmed:

- PDF download and extraction: works
- DOCX download and extraction: works
- one `.doc` file exists, but `.doc` is outside the first automated path

Interpretation:

- the advert-response folder is not blocked on PDF/DOCX capability
- the remaining design question is about modelling and provenance, not basic
  file access

## 10. Recommended non-first targets

The following areas should not be the first bulk source:

- `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!`
- `/#################----CV's- IN-JAD-JobAdder`

Reasons:

- size
- duplication risk
- likely overlap with already-known systems

## 11. Current bottom line

We now have a coherent picture:

- Tom's narrative explanation was directionally accurate
- the screenshot-based hints were useful and largely borne out by live reads
- the live Dropbox structure contains both archive and operational workflow
  layers
- the best first Dropbox ingestion slice is likely a small vacancy-linked CVR
  folder, not the largest archive area

## 12. Cross-Source Check: `tw398`

We inspected one live JobAdder application cohort for:

- `jobTitle = tw398 - KDB Developer`
- `job.jobId = 936462`
- workflow stage: `"INBOX"= New-CV's - [So CVR them!]`

### A. JobAdder application layer

Confirmed:

- active applications exist for `tw398`
- sample application IDs:
  - `12204918`
  - `12201902`
  - `12201901`
  - `12201900`
  - `12201899`
- sample candidate IDs:
  - `17071060`
  - `17068569`
  - `17068570`
  - `17068571`
  - `17068572`

Important finding:

- the application records exist
- the `tw...` coding exists on the application/job
- but the sample application attachment lists were empty

### B. JobAdder candidate attachment layer

For the same `tw398` candidates, each sampled candidate record had one resume
attachment on the **candidate**, not on the **application**.

Examples:

- candidate `17071060`
  - `sanjeev sadha.docx`
- candidate `17068569`
  - `Zafar_Lead_Finance.docx`
- candidate `17068570`
  - `tw239&tw275_Vega+Murden+-+CV.pdf`
- candidate `17068571`
  - `tw239&tw275_Pk_CV_. (1).docx`
- candidate `17068572`
  - `tw239&tw275_Nav+CV+DLT.pdf`

### C. Dropbox layer

Searching Dropbox for `tw398` showed three distinct shapes:

1. Job-spec folder:
   - `/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - KDB Developer x2`
   - contains the job spec PDF, not candidate CVs

2. Archive email copies:
   - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/`
   - contains multiple `tw398` application `.eml` files

3. CV document copies:
   - the JobAdder candidate attachment filenames also exist in Dropbox
   - sample locations:
     - `/#################----CV's- IN-JAD-JobAdder/sanjeev sadha.docx`
     - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/Zafar_Lead_Finance.docx`
     - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/tw239&tw275_Vega+Murden+-+CV.pdf`
     - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/tw239&tw275_Pk_CV_. (1).docx`
     - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/tw239&tw275_Nav+CV+DLT.pdf`

### D. Current interpretation

For advert-response workflows like `tw398`, the structure currently looks like:

- JobAdder **application** = vacancy/application context
- JobAdder **candidate attachment** = current resume attached to the candidate
- Dropbox **job-spec folder** = vacancy specification context
- Dropbox **archive folders** = email/source-document history and duplicate CV copies

That suggests the likely source-of-truth model is:

- use JobAdder applications for vacancy/application context
- use JobAdder candidate attachments as the first structured CV attachment source
- use Dropbox as a supporting archive/source-history layer, not the primary application attachment layer

## 13. Parsed `.eml` Proof: `tw398`

To move beyond filename guesses, we parsed one real advert-response `.eml`
file from Dropbox:

- `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/shan.lingeswaran@hotmail.co.uk - Totaljobs - Suitable application for KDB Developer tw398.eml`

Parsed result:

- Subject:
  - `shan.lingeswaran@hotmail.co.uk - Totaljobs - Suitable application for KDB Developer tw398`
- Date:
  - `Tue, 28 Apr 2026 09:27:12 +0000`
- From:
  - `Totaljobs.com <totaljobs@totaljobsmail.com>`
- To:
  - `tom.owens@jamesjosephassociates.co.uk`
- Detected vacancy code:
  - `tw398`
- Attachment count:
  - `1`
- Attachment name:
  - `Shivadharshan (Shan) Lingeswaran (0168c899-bf00-4fc7-8259-bfac0312bdb7 - Totaljobs).pdf`

Important interpretation:

- the `.eml` file is a real advert-response email archive, not just a renamed
  CV file
- it preserves sender/channel provenance:
  - source job board (`Totaljobs`)
  - delivery target (`tom.owens@...`)
  - received timestamp
- it also preserves a candidate-specific attachment filename
- that means Dropbox `.eml` files are valuable as provenance/history even when
  JobAdder already holds the structured candidate/application record

Current working model after the `.eml` proof:

- JobAdder application:
  - structured vacancy/application context
- JobAdder candidate attachment:
  - structured CV/document source
- Dropbox `.eml`:
  - source-email provenance and attachment-history layer
- Dropbox duplicate CV files:
  - archive/mirror layer that may or may not differ from JobAdder

## 14. First Byte-Level CV Comparison Proof

To test whether Dropbox CV copies are merely mirrors of JobAdder candidate
attachments or materially different files, we compared one real pair:

- JobAdder candidate:
  - `17071060`
- JobAdder attachment:
  - `21562882`
- JobAdder file name:
  - `sanjeev sadha.docx`
- Dropbox path:
  - `/#################----CV's- IN-JAD-JobAdder/sanjeev sadha.docx`

Comparison result:

- file name match:
  - `true`
- byte count match:
  - `true`
- SHA-256 hash match:
  - `true`

Shared SHA-256:

- `8c105d129f4b338b5efaee68df859eeb73ad38b584d5178073953c50c9669a9a`

Interpretation:

- for this sample, the Dropbox CV copy is byte-identical to the JobAdder
  candidate attachment
- that materially strengthens the current working assumption that at least some
  Dropbox CV files are archive/mirror copies of the structured JobAdder
  candidate attachment source rather than independent versions
- this does not prove every Dropbox CV file is always identical, but it is the
  first direct file-level confirmation in that direction

## 15. Second Byte-Level CV Comparison Proof: `ACHTUNG! in RFL!`

To test whether the duplication-heavy archive area behaves differently from the
`IN-JAD-JobAdder` mirror, we compared a second real pair:

- JobAdder candidate:
  - `17068569`
- JobAdder attachment:
  - `21558363`
- JobAdder file name:
  - `Zafar_Lead_Finance.docx`
- Dropbox path:
  - `/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/Zafar_Lead_Finance.docx`

Comparison result:

- file name match:
  - `true`
- byte count match:
  - `true`
- SHA-256 hash match:
  - `true`

Shared SHA-256:

- `5e86b914695a3496cb506d4b6f333853a97f9c3ec1f587cff8aa2e7b8cc7bb0c`

Interpretation:

- the `ACHTUNG! in RFL!` copy is also byte-identical to the JobAdder
  candidate attachment for this sample
- the duplication-heavy archive area therefore looks less like an independent
  alternative CV source and more like a document-history mirror, at least for
  the tested files
- after two direct hash matches across two different Dropbox areas, the
  default working assumption should now be:
  - JobAdder candidate attachment = structured source of truth
  - Dropbox CV copies = archive/mirror copies unless a later comparison proves
    otherwise

## 16. Live JobAdder Job Detail for `tw398`

We then fetched the live JobAdder job record for:

- `jobId = 936462`

Key live fields:

- `jobTitle = tw398 - KDB Developer`
- `company.name = B2C2`
- `status.name = Open`
- `workType.name = Permanent`
- `salary.rateLow = 125000`
- `salary.rateHigh = 125000`
- `salary.currency = GBP`
- `owner.email = tom.owens@jamesjosephassociates.co.uk`
- `statistics.applications.total = 88`

Most importantly, the JobAdder job record includes a full HTML
`jobDescription` whose content materially overlaps the Dropbox job-spec PDF:

- Dropbox PDF:
  `B2C2 - Snr. KDB Developer - London - 2026.pdf`
- JobAdder job:
  `tw398 - KDB Developer`

Interpretation:

- `tw398` is now confirmed as a real vacancy/job anchor across:
  - JobAdder job/opportunity
  - JobAdder applications
  - Dropbox job-spec folders
  - Dropbox advert-response `.eml` files
  - Dropbox duplicate CV files
- the Dropbox job-spec PDF is not isolated context; it aligns with a real live
  JobAdder opportunity record
- that means job specs should likely be treated as first-class retrieval and
  matching inputs, not just reference documents sitting in Dropbox

## 17. First Live Job + Job-Spec Persistence Proof

We then implemented and ran the first narrow persistence slice for the same
`tw398` job/job-spec pair.

Operator script:

- `scripts/persist_tw398_job_spec.py`

Live persisted result:

- canonical `jobs` row created/updated
- canonical `documents` row created/updated with:
  - `document_type = job_spec`
- provenance-bearing `source_records` created/updated for:
  - JobAdder job
  - Dropbox job-spec document
- `source_record_links` created/updated so the source records point at the
  canonical company/job/document rows
- `document_links` created/updated with:
  - `relationship_type = job_spec`

The confirmed live canonical IDs for the first run were:

- `company_id = 624e92fb-2b08-4820-844d-cc0e866e7f31`
- `job_id = dba716b6-710c-427c-a866-50cc5425854f`
- `document_id = 1ea4341e-8421-4ee8-8dd1-e8bf889bd077`

The direct DB sanity check confirmed:

- job title:
  - `tw398 - KDB Developer`
- job source:
  - `jobadder`
- linked company ID present on the job row
- document type:
  - `job_spec`
- document title:
  - `B2C2 - Snr. KDB Developer - London - 2026.pdf`
- document source URI:
  - `/new dropbox/# DLV/LIVE JOBS - [Job Specs]/tw398 - B2C2 - KDB Developer x2/B2C2 - Snr. KDB Developer - London - 2026.pdf`
- `document_links` contains:
  - `relationship_type = job_spec`
  - `job_id = dba716b6-710c-427c-a866-50cc5425854f`

Interpretation:

- the project now has a real, not theoretical, persistence path for:
  - JobAdder opportunity context
  - Dropbox job-spec documents
- the job-spec PDF is now persistable as a first-class canonical document
  linked to the canonical job
- the next retrieval/matching work can use persisted job-spec text instead of
  relying on ad hoc local parsing
