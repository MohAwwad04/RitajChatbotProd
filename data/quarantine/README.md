# Quarantine — material excluded from the production index

Every file in this folder was in the production knowledge base and **fails the
Ritaj-only source policy** (`src/ritaj/source_policy.py`, roadmap Phase 2 §2.1).
Nothing here may be indexed into a production corpus artifact. The build code
does not read this directory at all; `scripts/build_index.py` reads only
`data/sources.yaml` and the snapshots it points at, and `deploy_space.py`
excludes this folder from the deployed tree.

It is kept for two legitimate uses:

1. **Development test data.** `python scripts/build_index.py --corpus quarantine`
   builds a local, clearly-labelled dev index so the pipeline can be exercised
   without waiting for Birzeit authorization. This is refused when
   `ENVIRONMENT=production`.
2. **Rewrite input.** When approved Ritaj exports arrive, these files show what
   questions the corpus was trying to answer.

## Why each file is here

Three disqualifying properties, from the policy:

- **off-domain** — the content's canonical source is not `ritaj.birzeit.edu`
  (usually `www.birzeit.edu`, plus `koha.birzeit.edu` and en.wikipedia.org).
- **unverified acquisition** — assembled from search-engine listings rather than
  fetched or exported from the source. §2.3 excludes search snippets outright.
- **SAMPLE** — sections explicitly marked as fabricated placeholder text.

| File | Reason |
|---|---|
| `about_birzeit_university.md` | off-domain (Wikipedia), unverified acquisition |
| `academic_calendar_fall_2025_2026.md` | off-domain (`www.birzeit.edu/en/study/academic-calendar`) |
| `admission_and_registration.md` | off-domain (`www.birzeit.edu/en/admissions/…`) |
| `admission_how_to_apply.md` | off-domain, unverified acquisition (search listings) |
| `contact_campus_and_transport.md` | off-domain, unverified acquisition (search listings) |
| `course_catalog_and_programs.md` | off-domain (4 `www` citations), 1 SAMPLE section |
| `course_registration.md` | Ritaj-described but never exported from Ritaj; no exact canonical URL, and its own header says the on-screen labels are unconfirmed |
| `english_placement_and_language.md` | off-domain (`www.birzeit.edu/en/admissions/…`) |
| `faculties_and_degree_programs.md` | off-domain, unverified acquisition (search listings) |
| `financial_account_and_payment.md` | off-domain (2), 3 SAMPLE sections |
| `grading_and_gpa.md` | off-domain (graduate-studies PDF on `www`), 3 SAMPLE sections |
| `graduation_and_advising.md` | off-domain (1), 4 SAMPLE sections |
| `library_services.md` | off-domain (5 `www` + `koha.birzeit.edu`), 1 SAMPLE section |
| `password_and_account_security.md` | off-domain (2), 2 SAMPLE sections |
| `ritaj_announcements_and_personal_info.md` | 3 SAMPLE sections — the menu paths are explicitly placeholders |
| `ritaj_portal_and_it.md` | off-domain (2), 3 SAMPLE sections |
| `ritaj_schedule_and_records.md` | off-domain (2), 4 SAMPLE sections |
| `sample_registration_guide.md` | entirely fabricated; its own header says so |
| `scholarships_and_financial_aid.md` | off-domain, unverified acquisition (search listings) |
| `student_life_and_affairs.md` | off-domain, unverified acquisition (search listings) |
| `tuition_and_fees.md` | off-domain (`www.birzeit.edu/en/admissions/tuition-fees-0`) |
| `webmail_and_student_email.md` | off-domain (2), 3 SAMPLE sections |
| `links_TODO.md` | tracks unverified links in the old hand-maintained `data/links.yaml`, itself superseded by the navigation registry |

**All 22 files fail. No file in the previous corpus qualifies for the production
index.** That is the finding, not a processing error: the corpus was assembled
from public Birzeit web pages and research, at a time when the product rule was
"Birzeit information", and the rule is now "content whose canonical source is
exactly `ritaj.birzeit.edu`".

## What has to happen next

The production corpus cannot be reconstructed from anything in this repository.
It needs an authorized acquisition path (roadmap §2.3, in priority order):

1. Birzeit Computer Center supplies an export/API, or allowlists the ingestion
   job's identity and rate.
2. A content owner exports approved public pages/PDFs to a signed snapshot.
3. A reviewer opens each page deliberately in a browser, saves it, and records
   the canonical Ritaj URL plus approval.

Direct automated fetches return a Cloudflare managed challenge (HTTP 403). That
protection must not be bypassed. Until one of the three paths is available, the
launch scope is whatever small set of public Ritaj documents can actually be
verified and approved — gaps are not filled with guesses.

`data/sources.yaml` holds the review queue: the candidate Ritaj URLs, all
`approved: false`, waiting on acquisition and a named approver.
