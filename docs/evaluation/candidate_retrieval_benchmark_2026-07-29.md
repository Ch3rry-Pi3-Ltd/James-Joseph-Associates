# Candidate Retrieval Benchmark - 29 July 2026

## Purpose

This benchmark checks the completed semantic index against four supplied
recruitment briefs and measures whether recently indexed Linked Helper
profiles are entering retrieval and final shortlist results.

The four benchmark briefs were reconstructed from the job-specification
content supplied during UAT. They are versioned in
`docs/evaluation/recruiter_role_briefs.json`. They are representative briefs,
not byte-for-byte copies of the original PDF files.

## Configuration

- Hybrid retrieval: full-text plus semantic candidate blocks
- Fusion: reciprocal-rank-style merge
- Candidate pool: top 25 per role
- Final shortlist: top 5 per role
- Semantic model: `text-embedding-3-large`, 1536 dimensions
- Final ranking: configured OpenAI reasoning model with structured output
- Corpus coverage: 25,820 of 25,820 canonical candidates indexed
- Personal data retained in this report: candidate name and professional title
- Excluded from the artifact: resume text, email, telephone and other contact details

The machine-readable output is in
`docs/evaluation/candidate_retrieval_benchmark_2026-07-29.json`.

## Aggregate Results

| Measure | Result |
| --- | ---: |
| Role briefs | 4 |
| Retrieved candidates inspected | 100 |
| Final shortlisted candidates | 20 |
| Linked Helper-only profiles in top-25 pools | 16 |
| Cross-source Linked Helper profiles in top-25 pools | 8 |
| Linked Helper-only profiles in final top-five lists | 0 |
| Cross-source Linked Helper profiles in final top-five lists | 3 |
| Earlier shortlist names retained in new final lists | 4 |
| Earlier shortlist names present anywhere in new top-25 pools | 8 |

## Results By Role

### Starr Insurance - Financial Systems Analyst

Final shortlist:

1. Thays Abdou August - 95
2. Chetan Kharatmal - 90
3. Nunya Lotsu - 85
4. Iquw Infor Sunsystems Administrator - 80
5. Paul Chorley - 75

Linked Helper representation:

- 4 Linked Helper-only profiles entered the top 25.
- No Linked Helper-linked profile reached the final five.
- None of the five earlier UAT shortlist names appeared in the new top 25.

Interpretation:

- Several finalists have relevant finance-system or analyst evidence.
- The weak-looking parsed name `Nunya Lotsu` requires manual inspection.
- The complete change from the earlier shortlist means this role should be
  recruiter-reviewed before being used as a regression baseline.

### B2C2 - Senior Quant Developer, OTC Pricing

Final shortlist:

1. Zahid Hossain - 95
2. Yogesh Mehta - 93
3. Daniel Yuen - 90
4. Arif Jaffer - 88
5. Plamen Stilyianov - 85

Linked Helper representation:

- 9 Linked Helper-only profiles entered the top 25.
- One cross-source Linked Helper/CV candidate reached the final five.
- No Linked Helper-only profile reached the final five.
- None of the five earlier UAT shortlist names appeared in the new top 25.

Notable profile-only retrieval:

- Jamil Rzayev ranked first in retrieval with a title indicating senior FX
  options volatility quant development.
- Alan Chan ranked seventh with centralised-pricing development evidence.
- Riaz Khanmohamed ranked twenty-first with senior Java/Python development evidence.

Interpretation:

- The new profile-only index is materially broadening first-pass recall.
- The absence of those plausible profiles from the final five indicates that
  the reranker currently favours fuller CV evidence over concise profile-only
  evidence. This is the clearest next tuning target.

### B2C2 - Rust Developer, Electronic Trading

Final shortlist:

1. Jad Salfiti - 95
2. Bohdan Zhuravel - 90
3. Renze (Oscar) Sun - 85
4. Ronnie Chowdhury - 80
5. Moussa Oumarou - 75

Linked Helper representation:

- 1 Linked Helper-only profile entered the top 25.
- 5 cross-source Linked Helper/CV profiles entered the top 25.
- One cross-source candidate reached the final five.
- Four earlier UAT names remained in the top 25; Jad Salfiti remained in the
  final five.

Interpretation:

- Retrieval remains centred on Rust, low-latency and trading evidence.
- Cross-source refresh data is participating in the result set.
- The final ordering changed substantially and needs recruiter validation.

### GSR Markets - Quantitative Developer, Rust

Final shortlist:

1. Bohdan Zhuravel - 95
2. Christopher W - 90
3. Renze (Oscar) Sun - 88
4. Malko Bravi - 85
5. Ricardo Xu - 83

Linked Helper representation:

- 2 Linked Helper-only profiles entered the top 25.
- 2 cross-source Linked Helper profiles entered the top 25.
- One cross-source candidate reached the final five.
- Four earlier UAT names remained in the top 25 and three remained in the
  final five.

Interpretation:

- This is the most stable of the four tests.
- The top three have direct low-latency, Rust, market-microstructure or HFT evidence.
- Profile-only candidates are searchable but did not displace stronger
  document-backed evidence in the final five.

## Conclusions

1. **Coverage is working.** Linked Helper-only candidates are no longer absent
   from semantic retrieval. They occupied 16% of the inspected top-25 positions.
2. **Fresh cross-source context is working.** Eight retrieved candidates and
   three finalists were linked to both Linked Helper and another source.
3. **Final use of profile-only evidence needs improvement.** No Linked
   Helper-only candidate reached a final top five, even where the profile title
   and skills looked highly relevant.
4. **The earlier screenshots are not sufficient ground truth.** Only four of
   twenty earlier finalists remained in the new final lists. Some movement is
   expected after adding 9,697 profiles and using reconstructed briefs, but the
   difference is too large to label automatically as an improvement.
5. **Recruiter labels are the next quality gate.** For each role, mark the top
   25 as relevant, borderline or unsuitable. Those labels can then measure
   recall at 25, reciprocal rank and final-shortlist precision.

## Recommended Next Changes

1. Show the operator whether each candidate is CV-backed, Linked Helper-only
   or cross-source.
2. Expand the evidence supplied to the reranker for profile-only candidates:
   current role, recent employment history, skills and updated-at provenance.
3. Add deterministic must-have coverage for role-specific requirements before
   LLM ranking, without turning it into a brittle keyword-only filter.
4. Capture recruiter accept/reject feedback and promote validated examples
   into the benchmark fixture.
5. Re-run this exact benchmark after tuning and compare against the saved JSON
   artifact rather than relying on screenshots.
