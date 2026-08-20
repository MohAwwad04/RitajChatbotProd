# Candidate URL confirmation log (T2.2)

Every entry in `data/sources.yaml` is a **question** — "is this the right
page?" — not an assertion. This log is where a human answers it.

**A row may only be filled by a person who opened the page in a normal browser.**
Automated confirmation is impossible and must not be attempted: Ritaj returns a
Cloudflare managed challenge (HTTP 403) to automated requests, and bypassing it
is forbidden (`data/quarantine/README.md`).

Sign out first. A page that looks public while you are signed in, and 302s to a
login when you are not, is **not** public — that distinction is the entire point
of the check.

## How to fill a row

| Column | What goes in it |
|---|---|
| Exists | yes / no / redirects |
| Public | yes / **needs sign-in** — checked while signed out |
| Right page | does the content match what the record claims it is |
| True canonical URL | the URL in the address bar *after* any redirect |
| Checked by | a person's name |
| Date | YYYY-MM-DD |

Any candidate whose "Public" is **needs sign-in** is out of scope for the public
corpus: mark it, remove the record from `data/sources.yaml`, and note why here.

## Log

| # | Record id | Candidate URL | Exists | Public | Right page | True canonical URL | Checked by | Date | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `registration-instructions-ar` | `https://ritaj.birzeit.edu/reg/instructions` | | | | | | | Highest-value record: backs the most common question and the primary navigation action |
| 2 | `registration-instructions-en` | `https://ritaj.birzeit.edu/reg/instructions` | | | | | | | Same URL as #1. If Ritaj serves both languages from one URL, either split the snapshot and give each variant a distinct canonical URL, or drop this record — two records may not claim the same URL |
| 3 | `academic-calendar-ar` | `https://ritaj.birzeit.edu/academic-calendar` | | | | | | | Also note the term it covers, for `effective_from`/`effective_to` |
| 4 | `academic-calendar-en` | `https://ritaj.birzeit.edu/academic-calendar/en` | | | | | | | **Route unconfirmed** — find the real English path if there is one |
| 5 | `course-browser` | `https://ritaj.birzeit.edu/hemis/courses` | | | | | | | Expected to need sign-in. If so, prefer the navigation action over indexing it |
| 6 | `public-directory` | `https://ritaj.birzeit.edu/register/` | | | | | | | Contains names. Even if public, check the PII rules before approving — "public on Ritaj" and "appropriate to index" are different questions |
| 7 | `message-boards` | `https://ritaj.birzeit.edu/bzu-msgs/boards` | | | | | | | User-authored and fast-ageing: the stalest and the most likely injection vector. Only with a content owner's explicit approval |

## Outcome

- Candidates confirmed public and correct: _(none yet)_
- Candidates removed as sign-in-only: _(none yet)_
- Candidates whose URL was corrected: _(none yet)_

Until this table has verdicts, `data/sources.yaml` remains a review queue and
`check_corpus_policy.py` passes **vacuously** — it is validating an empty set.
