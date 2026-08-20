# Snapshot intake — from an approved page to a published corpus

**Task T2.3.** This is the runbook for the moment approved content actually
arrives, written in advance so nobody improvises under time pressure. Nothing
here needs the content to exist; the path was exercised end to end against the
**dev** corpus on 2026-08-15, and the rejection path was demonstrated (§6).

**Read [`data/quarantine/README.md`](../data/quarantine/README.md) first, every
time.** It explains why all 22 previous documents were withdrawn, and the failure
modes below are the ones that put them there.

---

## 0. The rule this whole path exists to enforce

A record may be indexed only if **its canonical source is exactly
`https://ritaj.birzeit.edu`**, it is public, it was *acquired* through an
authorized path, and **a named person approved it**. Not a role. Not "team". A
person or a ticket.

If content arrives and any of those is missing, the intake **stops** at the step
that is missing. It does not continue with a placeholder — a "TBD" in a checksum
field is how a checksum stops meaning anything.

---

## 1. Where the file goes

```
data/snapshots/<corpus-version>/<source-id>.<ext>
```

- `<corpus-version>` is the version you are about to build, e.g. `2026-09-01`.
  Snapshots are grouped by the corpus that used them, so rolling back to an
  older corpus rolls back to the text that corpus actually cited.
- `<source-id>` is the `id` in `data/sources.yaml` — one file per record.
- `<ext>` matches `content_kind`: `.html`, `.pdf`, `.md`, `.txt`.

Never place acquired content in `data/raw/`. A stray file dropped there once
went straight into production; check 2 of `check_corpus_policy.py` exists
because of it, and will fail the build.

Never copy anything out of `data/quarantine/` into `data/snapshots/`. That does
not launder its provenance, it only hides it.

## 2. Review the content before it is a record

Do this while it is still just a file. Once it is approved it is citable.

- [ ] **It is the right page.** Compare against the candidate row in
      `data/sources.yaml`, and against the confirmation log
      (`cowork_ritaj/url-confirmation.md`, task T2.2).
- [ ] **It is reachable without signing in.** If a login was needed, the page is
      out of scope — remove the candidate rather than indexing it.
- [ ] **No personal data.** `source_policy.scan_pii` flags student/national id
      shapes, emails and phone numbers; a hit quarantines the record for a human
      to judge. The public directory candidate (`public-directory`) is the one
      most likely to trip this, and refusing it is a valid outcome.
- [ ] **No `SAMPLE`, placeholder or "TBD" text.** Three of the withdrawn
      documents were partly fabricated and cited anyway.
- [ ] **It carries an effective date** if it is time-bound (calendars, term
      deadlines) — set `effective_from` / `effective_to` so retrieval prefers the
      calendar currently in force.
- [ ] **A refresh window is realistic.** `daily` for calendars and boards,
      `weekly` for registration instructions, `monthly`/`yearly` for stable
      prose. Answers from a record past its window are flagged as possibly out of
      date, which is only useful if the window was honest.

## 3. Fill the record

```bash
python scripts/build_index.py --rehash     # prints the sha256 of each snapshot
```

In `data/sources.yaml`, on the record's existing candidate entry:

| Field | Value |
|---|---|
| `content_path` | `snapshots/<corpus-version>/<source-id>.<ext>` — relative to `data/` |
| `fetched_at` | the date the content was taken from Ritaj (not today's date, if they differ) |
| `sha256` | from `--rehash`; a mismatch against the stored file fails the build |
| `effective_from` / `effective_to` | for time-bound content |
| `approved` | **still `false` at this point** |

Commit this. It is a reviewable diff, and it is deliberately a separate step
from approval.

## 4. Approval — a separate, human, per-language act

Only after the owning office has confirmed the content:

```yaml
approved: true
approved_by: "Name Surname, <office>"      # or a ticket id — never "team"
```

Arabic and English are approved **separately, by their own owners**. One person
signing off text they cannot read is not an approval.

One record per commit. If approval for one page is later withdrawn, the revert
is one commit.

```bash
python scripts/check_corpus_policy.py --strict    # must exit 0, non-vacuously
grep -c 'approved: true' data/sources.yaml        # matches what was approved
```

Note that `check_corpus_policy.py` currently passes **vacuously** — it reports
"none published", i.e. it is validating an empty set. The first real approval is
the first time its exit code means anything.

## 5. Publish

```bash
python scripts/build_index.py --publish     # writes data/corpus/<version>/ + CURRENT
python scripts/check_corpus_policy.py       # must now report a non-zero chunk count
python scripts/ensure_index.py              # the artifact restores and answers
```

Then prove the rollback before you need it (T2.6): publish a second version,
point `data/corpus/CURRENT` at the previous one, restart, confirm the answers
change, and roll forward. Record the timing in `docs/OPERATIONS.md` §4.

## 6. The rejection path, demonstrated

The gate was verified on 2026-08-15 by adding one deliberately off-domain record
to `data/sources.yaml` — `https://www.birzeit.edu/en/study/academic-calendar`,
`approved: true` — which is exactly the mistake that put half the quarantined
corpus there:

```
$ python scripts/check_corpus_policy.py
  ERROR [negative-test-off-domain] canonical_url: host must be exactly
        ritaj.birzeit.edu, got 'www.birzeit.edu'
  ERROR [negative-test-off-domain] fetched_at: required once a record is approved
  ERROR [negative-test-off-domain] sha256: required once a record is approved
  ERROR [negative-test-off-domain] content_path: required once a record is approved
FAILED: 4 problem(s).                                            # exit 1

$ git checkout data/sources.yaml && python scripts/check_corpus_policy.py
OK — every indexable record traces to an approved ritaj.birzeit.edu source.   # exit 0
```

Note that approving a record without content is caught in the same pass: the
policy demands `fetched_at`, `sha256` and `content_path` the moment `approved`
becomes true, so "approved but never actually acquired" cannot pass either.

The record was reverted and `git status --porcelain data/sources.yaml` is empty.

## 7. Exercising the pipeline without approved content

```bash
python scripts/build_index.py --dev        # quarantined dev corpus — never --publish
```

`--dev` is refused when `ENVIRONMENT=production`, and `build_from_directory`
(the old folder scan) raises there too. Use it to check that ingestion, chunking
and retrieval still work; never to make the "no corpus" state look solved.

---

## What still cannot be done here

Nothing in this repository substitutes for an authorized acquisition path.
Ritaj returns a Cloudflare managed challenge to automated requests and that must
not be bypassed. Until the Computer Center, a content owner, or a reviewer with
a browser supplies the pages (`cowork_ritaj/outreach/`), this runbook has
nothing to run on — and the service correctly reports `not-ready` and abstains.
