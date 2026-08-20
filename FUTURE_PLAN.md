# Future plan — from live-and-empty to data-quality-assured

**Written:** 20 August 2026
**Status:** CURRENT. This is the forward plan; everything before it is now
either done, historical, or reference.

Every number here was produced by running the project's own gates on this date,
not asserted. Where something is unmeasured, it says so rather than estimating.

---

## 0. What this supersedes, and what still governs

The repository accumulated six live plan documents. That is how `DEPLOYMENT.md`
came to describe Groq and a popup that no longer existed, and it is worth not
repeating.

| Document | Status now |
|---|---|
| `SETUP_LIVE.md` | **Done.** All four human steps completed 20 Aug. Kept as the record of how the deployment was configured. |
| `PRODUCTION_FREE_LIVE_PLAN.md` | **Mostly executed.** §6 (free-tier hosting research) stays valuable reference; its P0 list is closed except the corpus. §10's advice to cut `max_tokens` to 350–500 is **withdrawn** — see §5 below. |
| `RELEASE_ROADMAP_2026.md` | **Complete on the code side.** Historical; the architecture invariants it established are restated in `CLAUDE.md` and enforced by gates. |
| `READY_TO_RELEASE_EXECUTION_PLAN.md` | Historical. Its measurements are from 15 Aug and are superseded by §1 here. |
| `cowork_ritaj/COWORK_PLAN.md` | **Done.** `PROGRESS.md` records what each task changed. |
| `cowork_ritaj/INTAKE.md` | **Still authoritative.** The corpus intake path is unchanged and is the critical path. |
| `docs/RELEASE_CHECKLIST.md` | **Still authoritative.** The runnable definition of ready. |

---

## 1. Verified baseline, 20 August 2026

Live, at $0, on free tiers:

| Component | State |
|---|---|
| Backend | `https://mohawwad04-ritaj-rag.hf.space` — RUNNING, HF Space, `cpu-basic` |
| Port bind | 1.2 s (the `Launch timed out` outage that killed this Space is gone) |
| LLM | Cloudflare Workers AI, `@cf/google/gemma-4-26b-a4b-it`, answering |
| Vector DB | Qdrant Cloud free, AWS `us-east-1` — same region as the Space |
| Navigation | 4 reviewed destinations live, 1 correctly disabled |
| Extension | v1.2.0, MV3 side panel, green/gold, offline page finder |

```
pytest -q                      406 passed
node --test chrome-extension/  29 passed  (3 suites)
node scripts/e2e_extension.mjs 20/20 in real Chromium
5 policy gates                 green
navigation eval                22 cases, 100% precision, 100% recall
verify_qdrant_remote.py        13/13 against the real cluster
```

**And zero approved documents.** The service starts, reports `NO_CORPUS`, and
abstains. That is the design working, and it is also the whole of the remaining
work.

---

## 2. The shape of what is left

Only one thing is on the critical path. Everything else is either downstream of
it or can run in parallel.

```
                    ┌─ P1 gates that bite ──── done (B1), one item left
                    │
   first approved ──┼─ P3 refresh loop ─────── built, needs a corpus to exercise
   document (P2)    │
                    ├─ P4 quality measurement ─ impossible before P2
                    │
                    └─ P6 Store release ─────── needs P2 + P4

   P5 operations ─── independent, blocked only on people
```

---

## 3. P1 — Make the gates mean something

**Why first:** a gate that passes for the wrong reason is worse than no gate,
because it reassures. This is cheap and it makes every later measurement
trustworthy.

- [x] **The corpus gate no longer passes vacuously.** It printed
      `OK — every indexable record traces to an approved ritaj.birzeit.edu source`
      against an empty set, having never rejected a real document. It now reports
      what it validated, prints `PASSED VACUOUSLY` when that is nothing, and
      `--release` exits 1. Exercised against a real record: it rejected an
      invalid `content_kind`, an off-domain host, and a post-approval content
      change.
- [ ] **Content-level deduplication.** The policy rejects duplicate ids and
      duplicate canonical URLs. Nothing compares the content itself, so two
      snapshots of one page — or an AR/EN pair that is actually the same text —
      would both index and both be citable. In a corpus this small, one
      duplicated passage measurably distorts retrieval.

```bash
python scripts/check_corpus_policy.py --release   # must exit 0 before a release
```

---

## 4. P2 — The first approved document *(critical path)*

Nothing downstream can start without this. One document is enough to begin.

**The constraint that shapes everything:** `ritaj.birzeit.edu` answers **403 to
every automated request** — verified across `/`, `/academic-calendar` and even
`/robots.txt`, with and without a browser User-Agent. Defeating that Cloudflare
challenge is out of scope and would falsify the project's central claim. So
acquisition is a human opening a page in a browser, and no amount of engineering
changes that.

1. Save `https://ritaj.birzeit.edu/academic-calendar` from a signed-out browser
   into `data/snapshots/<version>/`.
2. `python scripts/build_index.py --rehash` for the checksum.
3. Fill `content_path`, `fetched_at`, `sha256` in `data/sources.yaml`.
4. Read the snapshot: no personal data, no placeholder text, dates correct.
5. `approved: true` + `approved_by: <a named person>`, one record per commit.
6. `python scripts/check_corpus_policy.py --release`
7. `python scripts/build_index.py --publish`

**Drop `course-browser`** — `/hemis/courses` was confirmed not to load.
**Decide `public-directory` deliberately** — it is the record most likely to
contain personal data, and refusing it is a valid outcome.

**Also blocked here:** PII scanning has never processed a real document.
`source_policy.scan_pii` is written but unexercised on real Ritaj markup, and the
privacy policy already promises it works. Run it against a deliberately dirty
sample and confirm it fires **before** the first approval.

### The authorized-acquisition track, in parallel

`cowork_ritaj/outreach/` holds bilingual drafts asking the Computer Center or
Registration Office for one of: an export, an API, or written authorization to
snapshot. **Send them.** They are the only route to §5's automation, and nothing
else shortens the path.

---

## 5. P3 — Keeping data current

Built 20 Aug; needs a corpus before it can do anything.

`scripts/refresh_sources.py` automates both halves of a refresh that can be
automated:

```bash
python scripts/refresh_sources.py --report      # what is overdue, and by how long
python scripts/refresh_sources.py --update <id> <saved-file>
```

`--update` answers the question that matters more than "is it time to look
again": **did the content actually move?**

- **Unchanged** → `fetched_at` bumped, approval untouched, staleness cleared.
  Nobody re-reviews text they already reviewed.
- **Changed** → approval withdrawn, record leaves the index until a human reads
  the diff. Re-indexing changed text under an old sign-off is exactly what the
  `sha256` field exists to prevent — and for a calendar corpus, a confidently
  cited deadline from last year is the highest-harm failure this product has.

**Remaining work:**

- [ ] Run `--report` on a schedule so overdue sources surface without anyone
      remembering. It exits 1 when something is overdue, so any cron or CI
      schedule works.
- [ ] Exercise the staleness badge end to end once a record has a `fetched_at`:
      backdate one, confirm the badge reaches the student UI.
- [ ] **If authorization arrives**, `--update` is the only piece that changes —
      it takes a file path today and would take a URL instead. Everything around
      it already works.

### Withdrawn advice

`PRODUCTION_FREE_LIVE_PLAN.md` §10 recommends reducing `max_tokens` to 350–500
"after evaluation". **Do not.** Gemma 4 is a reasoning model: measured on a
RAG-shaped call, reasoning was ~70% of output tokens (200 of 285), and at 1,024
a real question spent the entire budget thinking and returned nothing. Every
documented way to cap reasoning — `reasoning_effort: low`/`none`,
`reasoning.effort`, `thinking.type: disabled` — was tested against the live
provider and silently ignored. The default is now 2,048 with a floor of 512.

---

## 6. P4 — Measuring quality *(impossible before P2)*

No accuracy number exists for this product. Not a low number — none.

```
answerable     0 / 100      required before factual chat is enabled
calendar       0 / 25
navigation    22 / 20       ✓ already met
unanswerable  15 / 15       ✓
personal_data 12 / 10       ✓
```

Thresholds to meet, from `PRODUCTION_FREE_LIVE_PLAN.md` §8, with **separate
Arabic and English tables**:

| Metric | Threshold |
|---|---|
| Retrieval recall@10 | ≥ 95% |
| Supported-answer accuracy | ≥ 90% |
| Citation precision | ≥ 95% |
| Unsupported factual claims | < 2% |
| Correct refusal | ≥ 95% |
| Navigation destination precision | 100% (already met) |

- [ ] **Re-run `eval_chunk_size.py` on real content.** It has only ever seen the
      withdrawn dev corpus — hand-assembled markdown, not Ritaj HTML. Chunk
      boundaries that work on clean prose fail on tables, and the academic
      calendar is a table. Treat the current chunk size as unvalidated.
- [ ] **Latency needs a real distribution.** Measured 9.7 s and 12.2 s for a
      complete answer against a p95 ≤ 12 s target. Two samples cannot establish
      a p95. Run `scripts/loadtest.py --scenario sequential` against the live
      backend.

---

## 7. P5 — Operations *(independent; blocked only on people)*

```bash
python scripts/check_operations.py    # exits 1: 13 unassigned duties/undrilled rollbacks
```

- [ ] Nine duties need a named **primary and backup**. Not "the team" — the
      checker rejects that string deliberately, because when everybody is
      responsible nobody is paged.
- [ ] Four rollback drills need rehearsing with a recorded date and recovery
      time: corpus, backend, navigation, secret rotation.
- [ ] Protect the `release` branch (`cowork_ritaj/human-actions.md` §H1).
- [ ] **Rotate three credentials.** Cloudflare, Hugging Face and Qdrant were all
      pasted into a chat transcript. The Qdrant key decodes to `"access":"m"` —
      full manage rights, able to delete every collection. Rotation notes are at
      the top of `.env.local`. Qdrant first.
- [ ] Delete `dev_unapproved_never_served` from the production cluster once real
      data exists. Safe today only because no alias points at it.
- [ ] `rm OPERATOR-PASSWORD.txt ritaj_rag_admins.rtf` after moving the password
      into a manager.
- [ ] Decide on **Upstash Redis**, or document that rate limits and the daily
      neuron budget reset on restart. Acceptable for a closed alpha, not for a
      wide pilot.

**Free-tier expiry to diarise:** a free Qdrant cluster is suspended after 1 week
idle and deleted after 4. A free HF Space sleeps after 48 h idle
(`gcTimeout: 172800`).

---

## 8. P6 — Chrome Web Store release

- [ ] **Recapture all screenshots.** The current ones are dated 6 July and
      predate the redesign entirely — they show the old red UI, no page finder,
      no status pill. `node scripts/screenshot_panel.mjs` regenerates them at
      real dock widths in both languages.
- [ ] Verify the extension against the **live backend**. The E2E suite passes
      20/20 but blackholes the host by design, so the extension talking to the
      real Space is still unproven.
- [ ] Package from a clean tag; record the ZIP SHA-256 in `release/manifest.json`.
- [ ] Manually confirm the toolbar click opens the side panel — Playwright
      cannot drive it (microsoft/playwright#26693), so this stays a human check.
- [ ] Start **Unlisted or limited** rollout even though the listing is approved.

The listing *copy* is already honest — it correctly disclaims grades, schedule,
balance and official status. Only the images lie.

---

## 9. Rollout, and the honest state at each step

1. **Maintainer alpha** — navigation only, chat abstaining. *This is today.*
2. **Closed pilot, 10–20 students** — after P2 and P4. Grounded chat with a daily
   budget; collect aggregate failures.
3. **Limited Store rollout, one week** — review errors, quota, latency, source
   freshness and corrections daily.
4. **General availability** — only after every gate in
   `docs/RELEASE_CHECKLIST.md` is green and free-tier risk is accepted by a
   named owner.

**Capacity reality:** ~20 neurons per answer measured, ~44 extrapolated to a
4,000-token prompt. At 10,000 neurons/day that is **roughly 200–500 answers per
day**. A closed pilot, not a student body. Plan the rollout around that number,
not around demand.

---

## 10. Not verified by anyone

Stated explicitly so it is not mistaken for tested:

- The extension against the live backend.
- Three consecutive cold starts of the Space.
- Any behaviour with a real corpus — none exists.
- Latency as a distribution (n=2 is not a p95).
- `scan_pii` against real Ritaj markup.
- Whether the free HF account can rebuild the Space indefinitely. HF now
  requires a paid plan to *create* a Docker Space; this one predates that rule,
  so **do not delete it**.
