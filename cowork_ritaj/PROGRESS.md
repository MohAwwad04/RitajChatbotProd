# Progress log

Handoff format from `COWORK_PLAN.md` §1: task ID, what changed, the acceptance
command and its exit code, and anything that could **not** be verified.

Measurements were taken in a Linux sandbox with the model-free dependency set
(FastAPI, PyYAML, httpx, pydantic, bcrypt, pytest, qdrant-client, rank-bm25).
Anything needing Docker, node E2E in Chromium, a live provider, or network
access to Ritaj is marked **unverified** rather than assumed.

---

## 2026-08-15 — portal honesty, Stream 1, and Stream 2/5 preparation

### P0 — The student dashboard described a product that does not exist

Not a numbered task in the plan; found while reading the portal, and the reason
the portal work happened first.

`App.tsx` mounted `ChatbotPage` alone. Every dashboard and layout component —
`WelcomeHero`, `StatsGrid`, `CoursesPanel`, `QuickActions`, `SemesterPath`,
`UpcomingEvents`, `Header`, `Sidebar`, `MobileNav`, `NotificationsPanel` — was
unreachable code, and all of it was populated with an invented student record: a
named student, three courses with instructors and rooms, GPA 3.42, 108/132
credit hours, a 240 JD outstanding balance, four exam dates, and three
notifications about an account. `ChatThread` also rendered a hand-written
"answer" card (a registration window, a suggested course load, that same
balance) whenever a message carried `type: 'registration'`, and `chatData.ts`
exported `answerFor()`, a keyword-matching fake responder — a second, ungrounded
answer path sitting beside the cited one.

Meanwhile `src/ritaj/guardrails.py` declines every personal-record question and
states the limitation is permanent: *"I have no access to your student account
and I can't sign in on your behalf."* The chat status line said "Connected to
your academic record", the thinking indicator said "Reviewing your academic
record", and the first suggestion chip was "Summarize my academic status" — a
guaranteed refusal on the first tap.

**Changed**

- `src/ritaj/api.py`: new public `GET /capabilities` — approved sources,
  enabled navigation destinations, corpus summary, readiness, and the limits
  block. Only `approved: true` records and `enabled: true` actions are named;
  the review queue and unapproved destinations are counted, never described.
- `src/ritaj/navigation.py`: `declared_count()`, so "awaiting approval" and
  "does not exist" stay distinguishable (`load_registry()` drops an action with
  no approver, so its length cannot answer that).
- `ritaj-student-portal/`: `App.tsx` now mounts the full shell with a view
  router (home · ask · topics · open · status · privacy). New
  `api/capabilities.ts`, `DashboardPage`, `TopicsPanel`, `AskPanel`,
  `LimitsPanel`, `NavigationPanel`, `StatusPanel`; `WelcomeHero`, `StatsGrid`,
  `Header`, `Sidebar`, `MobileNav` rebuilt around real data; `i18n.ts` rewritten
  with honest bilingual copy; `chatData.ts` reduced to real session
  conversations; the fake `RegistrationAnswer`, `answerFor()`, the hard-coded
  "recent chats", the fabricated profile chip and the dead attach/microphone
  buttons removed.
- `styles/global.css`: physical properties replaced with logical ones, so the
  English (LTR) layout is not rendered underneath the RTL sidebar.
- `vite.config.ts`: the dev proxy forwarded `/chat/stream` while the client
  calls `/v2/chat/stream` — **every dev conversation was hitting Vite's 404**.
  Added `/v2/chat`, `/capabilities`, `/ready`, `/privacy`.
- `scripts/check_privacy.py`: new `check_portal_claims_only_what_it_does()` —
  fails the build if portal source claims record access or hard-codes a course
  code, currency balance or GPA. Comment lines are exempt, so the tombstones can
  record what they used to contain.
- `tests/test_capabilities.py`: six tests, including one asserting the limits
  block still agrees with `guardrails.check_scope`.

**Acceptance**

```
pytest -q                                            361 passed        exit 0
python scripts/check_privacy.py                      OK                exit 0
  negative test: reverting one string to "Connected to your academic
  record" → FAILED: 1 disclosure problem                               exit 1
cd ritaj-student-portal && npm run lint              clean             exit 0
npx tsc -b && npx vite build                         built, 1602 modules
```

**Not verified**

- No screenshot or browser run: the sandbox has no display, and the backend
  cannot be exercised end-to-end without a provider. The build and type checks
  pass; the rendering has not been looked at by a human.
- `vite build` into the repo's own `dist/` fails in this sandbox (`EPERM` on
  unlink); it was built to a temporary directory instead. `dist/` is unchanged.
- The five orphaned components could not be deleted (deletion refused in this
  environment). They are **tombstones**: comment-only files with `export {}`,
  each naming its replacement. **They should simply be `git rm`-ed** by whoever
  picks this up — nothing imports them.

### T1.1 — Stale SBOM and the checklist ordering trap · done

`scripts/sbom.py --check-current` added: regenerates in memory, compares to the
committed file ignoring `metadata.timestamp`, and names each drifted component.
Wired into CI's `security` job as **blocking, before** the regenerating step
(running `sbom.py` first would overwrite the file under test).
`docs/RELEASE_CHECKLIST.md` §A reordered so SBOM generation precedes packaging,
with a note that generation dirties the tree.

**Acceptance**

```
python scripts/sbom.py --check-current    # before regenerating
  ~ library pypdf:      SBOM says 6.13.3, tree has 6.14.2
  ~ library setuptools: SBOM says 81.0.0, tree has 83.0.0             exit 1
python scripts/sbom.py                    Wrote release/sbom.json (292 components)
python scripts/sbom.py --check-current    matches the tree            exit 0
python scripts/sbom.py --check-pinned     all deployables pinned      exit 0
```

The gate reproduced exactly the drift the plan documented, then cleared it.

**Not verified** — `package_extension.py --verify` was not run: the tree is
legitimately dirty with this work, and it refuses a dirty tree by design. Run it
from a clean checkout after these changes are committed.

**Worth a decision:** `.gitignore` ignores `release/` with the comment *"a stale
copy is what a reviewer reads"* — but `release/sbom.json` is **tracked**, so the
ignore does not apply to it, and T1.1 asks for it to be committed. Those two
intentions disagree. `--check-current` resolves it in favour of committing (a
tracked file that must match the tree cannot go stale silently); if the team
would rather not ship the file at all, untrack it and make the CI artifact the
only copy — but then delete `--check-current` in the same change rather than
leaving a gate with nothing to check.

### T1.2 — Enforceable ownership register · done

`scripts/check_operations.py` parses `docs/OPERATIONS.md` §1 and §4. Exit 1 while
any Primary/Backup cell is blank or any drill lacks a date and a recovery time.
Placeholders are rejected too — "TBD", "the team", "maintainers" are not owners,
because when everybody is responsible nobody is paged. Advisory in CI (it fails
on missing *people*, and blocking every PR on that teaches the team to ignore a
red job), blocking in `RELEASE_CHECKLIST.md` §E. OPERATIONS §1 notes it is
machine-checked.

**Acceptance**

```
python scripts/check_operations.py        13 problems, each row named   exit 1
  (9 duties with no primary and no backup; 4 drills never rehearsed)
python scripts/check_operations.py --path /tmp/ops_ok.md               exit 0
python scripts/check_operations.py --path /tmp/ops_bad.md              exit 1
  ("the team" rejected as a primary; "soon" rejected as a recovery time)
```

Exit 1 today is the intended state; it turns green when Stream 6 fills the
register in.

### T1.3 — Stale deployment doc retired · done

`DEPLOYMENT.md` reduced to a superseded pointer page. It had named Groq as the
provider, the popup as the UI, and — worst — a `user` field on `POST /chat` that
the privacy work removed, i.e. it documented sending exactly the data the policy
says is not collected. Still-true Hugging Face Space specifics (non-root UID
1000, `/tmp/qdrant`, the on-disk two-process index build, `/privacy` served by
the app) were folded into `docs/DEPLOY_GEMMA4.md` §5.
`SELF_HOSTED_LLM_PLAN.md` got a HISTORICAL banner — its environment tables still
read "Today (Groq)".

Deletion was preferred by the plan but is not possible in this environment.
Note that `DEPLOYMENT.md` and `CLAUDE.md` are **gitignored** (`.gitignore` §
"Local-only docs & ops notes"), so `DEPLOYMENT.md` is a local file, not a
published one — which lowers the stakes of the fix but not its value: the person
most likely to read it during an incident is the maintainer whose machine it is
on. Delete it locally if preferred; nothing links to it that this change did not
already redirect.

**Acceptance**

```
grep -rin 'groq\|popup' --include='*.md' --include='*.py' --include='*.js' .
  → remaining hits are all intentional: code that *detects* them
    (check_extension.py, secret_inventory.py, release_manifest.py), historical
    plan documents, and "superseded"/"was a popup" notes.
python scripts/check_privacy.py                                        exit 0
```

### T1.6 — Status blocks refreshed · done

`CLAUDE.md` (4 Aug → 15 Aug, 361 tests, PR #2 open, `release` unprotected),
`README.md` (adds `/capabilities`, explains that an empty home view is the
product working), `READY_TO_RELEASE_EXECUTION_PLAN.md` §2.2 (re-measured table;
portal lint and reproducibility had been green since 5 Aug and were still being
quoted as failures; blocker 5 corrected — the branch is pushed).

### T2.1 — Acquisition request drafted · done

`cowork_ritaj/outreach/acquisition-request-{en,ar}.md` plus
`appendix-what-it-does.md`. Both name all seven candidates with their URLs,
state that this is an independent unofficial project, that no student data is
requested, that the Cloudflare challenge has not been bypassed, offer the three
authorized paths, and define approval concretely as a named person confirming
the content is correct and public. The appendix is a one-page capability +
refusal summary, each claim naming the file that enforces it.

**Acceptance** — every `canonical_url` in `data/sources.yaml` appears in both
drafts (checked programmatically). **Not sent** — bracketed fields (names,
sender, date) need a human, and the send date and recipient must be logged here.

### T2.3 — Snapshot intake path · done

`cowork_ritaj/INTAKE.md`: where a snapshot goes, the content review checklist,
which `sources.yaml` fields to fill, how approval works per language, and the
publish and rollback commands.

**Acceptance — the negative test, demonstrated**

```
# one deliberately off-domain record added, approved: true
python scripts/check_corpus_policy.py
  ERROR [negative-test-off-domain] canonical_url: host must be exactly
        ritaj.birzeit.edu, got 'www.birzeit.edu'
  ERROR ... fetched_at / sha256 / content_path required once approved
  FAILED: 4 problem(s)                                                 exit 1
# reverted
python scripts/check_corpus_policy.py    OK                            exit 0
git status --porcelain data/sources.yaml → empty
```

**Not verified** — `build_index.py --dev` was not run end to end: it loads a
~2 GB embedder and needs a Qdrant instance, neither available here. The policy
gate either side of it was exercised.

### T5.2 / T1.5 / T2.2 — human-only work prepared · done

- `cowork_ritaj/screenshot-checklist.md` — the three required 1280×800 captures,
  why no substitute is acceptable, and the fact that **shot 3 cannot be captured
  at all today**: it needs an enabled navigation action, and enabling one to
  take a picture is exactly the act T5.1 reserves for a named approver.
- `cowork_ritaj/human-actions.md` — the branch-protection command (H1), the
  password rotation sequence with the reason it must be interactive (H2), the
  URL confirmation instruction (H3), navigation approval (H4), and the
  credential table (H5).
- `cowork_ritaj/url-confirmation.md` — the empty log T2.2 fills, with per-column
  instructions and the sign-out warning that makes the check meaningful.

---

## Still blocked, unchanged

Nothing here moves the three external blockers. There is still no approved
corpus, no provider credentials, and nothing deployed; `eval_release.py --gate`
still exits 1 on `answerable 0/100` and `calendar 0/25`, which is the gate
working. See `human-actions.md` §H5 for who must supply what.

## Next

1. Commit this work (`cowork_ritaj/` is untracked; `package_extension.py` and a
   production `deploy_space.py` both refuse a dirty tree, untracked files
   included).
2. `git rm` the five portal tombstones and, if agreed, `DEPLOYMENT.md`.
3. Send the outreach drafts (T2.1) and fill `url-confirmation.md` (T2.2) — the
   critical path runs through them and nothing else shortens it.
