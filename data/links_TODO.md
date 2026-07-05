# Link map — URLs to verify

Every entry below is marked `verified: false` in `data/links.yaml`. A human
should open each URL, confirm it resolves to the intended page, and flip
`verified: true` (or replace the URL with the correct one). Until then the API
still returns these links, but they should be treated as best-effort, not
confirmed.

Two kinds of unverified entries:

1. **Found via search index, not directly confirmed** — public `birzeit.edu`
   pages that appeared in search results but were not fetched end-to-end. Likely
   correct; just needs a click to confirm.
2. **Login-gated deep links** — most per-student Ritaj views (schedule, grades,
   financial account, personal info, webmail) have no public, deep-linkable URL.
   These are intentionally pointed at a safe public fallback (the portal home
   `https://ritaj.birzeit.edu/` or a relevant public page), which is itself
   marked `verified: true`. The TODO here is to confirm whether a stable deep
   link exists and, if so, add it.

## Unverified entries (from data/links.yaml)

| Doc (`source`) | Label | URL | Reason |
|----------------|-------|-----|--------|
| admission_and_registration.md | Register for a bachelor's program | https://www.birzeit.edu/en/admissions/new-students-admission/registration-bachelors-program | Search index only |
| english_placement_and_language.md | English Language Instruction Program | https://www.birzeit.edu/en/students/english-language-instruction-program-unlock | Cited in source doc, not confirmed |
| course_catalog_and_programs.md | Academic Departments A-Z | https://www.birzeit.edu/en/study/academic-departments | Search index only |
| library_services.md | BZU Library | https://www.birzeit.edu/en/study/bzu-library | Search index only |
| library_services.md | Main Library | https://www.birzeit.edu/en/content/main-library | Search index only |
| library_services.md | Library Catalog (Koha) | https://koha.birzeit.edu/ | Search index only |
| about_birzeit_university.md | About Birzeit University | https://www.birzeit.edu/en/about | Search index only |
| faculties_and_degree_programs.md | Faculties | https://www.birzeit.edu/en/study/faculties | Search index only |
| contact_campus_and_transport.md | Contact Birzeit University | https://www.birzeit.edu/en/contact | Search index only |
| contact_campus_and_transport.md | Campus | https://www.birzeit.edu/en/about/campus | Search index only |
| scholarships_and_financial_aid.md | Financial Aid | https://www.birzeit.edu/en/admissions/undergraduate/finanical-aid | Search index only (site's own typo'd path) |
| admission_how_to_apply.md | Admission Requirements | https://www.birzeit.edu/en/admissions/new-students-admission/admission-requirments | Search index only (site's own typo'd path) |
| student_life_and_affairs.md | Student Affairs | https://www.birzeit.edu/en/students/affairs | Search index only |

## Login-gated views still needing a stable deep link (optional)

These docs currently fall back to the portal home (`https://ritaj.birzeit.edu/`,
verified) because the per-student page is behind login:

- grading_and_gpa.md — grades / academic record
- ritaj_schedule_and_records.md — class & exam schedule
- financial_account_and_payment.md — financial account
- webmail_and_student_email.md — webmail
- ritaj_announcements_and_personal_info.md — messages / personal info
- graduation_and_advising.md — academic record / graduation request

If a stable, signed-in deep link is confirmed for any of these, add it as a new
entry in `data/links.yaml` with `verified: true`.
