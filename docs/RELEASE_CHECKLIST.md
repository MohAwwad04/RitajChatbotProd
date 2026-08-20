# Release checklist

The roadmap's "definition of ready to release" (§8) with a command against each
item, so readiness is something you can run rather than something you believe.
Items with no command are human judgements; they say so.

Run from a clean checkout of the release tag.

---

## A. Gates that must be green

```bash
pytest -q                                   # backend unit + integration
node --test chrome-extension/navigation.test.mjs \
            chrome-extension/links.test.mjs \
            chrome-extension/transport.test.mjs
python scripts/check_corpus_policy.py --release   # traces to an approved Ritaj URL,
                                                 # AND refuses to pass on an empty set
python scripts/check_navigation.py          # destinations reviewed; 18 URL attacks rejected
python scripts/check_extension.py           # minimal permissions; allowlist + limit parity
python scripts/check_privacy.py             # disclosures match the code; portal claims match the guardrail
python scripts/check_operations.py          # every duty and drill has a named owner and a date
python scripts/eval_release.py              # refusals, injection, URL + navigation precision
python scripts/eval_release.py --gate       # release-set completeness
python scripts/lock_deps.py --check         # dependency lock matches pyproject

# SBOM before packaging, in this order. `sbom.py` REWRITES release/sbom.json and
# therefore dirties the tree, and `package_extension.py --verify` refuses a dirty
# tree — running them the other way round (as this checklist used to) fails on a
# clean checkout. Commit the regenerated file before continuing.
python scripts/sbom.py --check-current      # committed SBOM still describes the tree
python scripts/sbom.py                      # regenerate; commit if it changed
python scripts/sbom.py --check-pinned       # deployables reproducible

python scripts/secret_inventory.py          # secrets present; nothing committed or packaged
python scripts/loadtest.py                  # concurrency, limits, budget, soak
python scripts/package_extension.py --verify   # deterministic ZIP, clean tree only
node scripts/e2e_extension.mjs              # real Chromium, unpacked extension
pip-audit -r requirements.lock.txt          # no known vulnerabilities in what ships
cd ritaj-student-portal && npm run lint && npm run build
```

`--gate` currently **fails**: the `answerable` and `calendar` categories are
empty because they cannot be written against a corpus that does not exist. That
is the honest blocker, not a formality to waive. (`navigation` is populated —
it resolves against the reviewed action registry, not the corpus.)

**Not automated, and must be checked by hand.** Chrome's side panel cannot be
opened programmatically and Playwright cannot drive one, so
`node scripts/e2e_extension.mjs` verifies everything behind the icon click but
not the click itself:

- [ ] Load the unpacked extension, click the toolbar icon, confirm the **side
      panel** opens (not a popup, not the portal).
- [ ] Navigate the active tab between pages; confirm the panel stays open and
      the conversation survives.

---

## B. Service

- [ ] Production `/live` returns 200 and `/ready` returns 200.
- [ ] Three consecutive cold starts succeed inside the host timeout.
      `/ready` reports `timings_ms.listening` — it should be seconds, not minutes.
- [ ] `pip-audit -r requirements.lock.txt` reports no unresolved finding.
      (Clean as of 2026-08-05: pypdf, torch and setuptools were bumped past
      PYSEC-2026-3610..3613, PYSEC-2025-194 and PYSEC-2026-3447.)
- [x] Base image pinned by digest, dependencies installed with
      `--require-hashes` from `requirements.lock.txt`. Refresh the digest
      deliberately:
      ```bash
      docker pull python:3.11-slim
      docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
      ```
- [ ] **The container has actually been built.** No Docker daemon was available
      when this was written, so the Dockerfile's hashed-install path is verified
      only by a `pip install --dry-run --require-hashes` against the same lock.
      The CI `container` job is the first real build — it must be green before
      release.
- [ ] Load and resilience numbers recorded (`python scripts/loadtest.py --json`).
      These are *application* numbers against a stub provider; real first-token
      and full-answer latency must be measured on staging against Cloudflare
      before any capacity claim.
- [ ] `/admin/usage` shows budget, concurrency and circuit state, and someone
      is watching it.
- [ ] **Rollback rehearsed, not just documented**: point
      `data/corpus/CURRENT` at the previous version, redeploy, confirm answers
      change, then roll forward again.

## C. Data and answers

- [ ] `check_corpus_policy.py --release` exits 0. The `--release` form is what
      makes this line mean anything: the plain form passes vacuously against an
      empty corpus, printing an OK that has never rejected a real document. A
      gate that cannot tell "everything passed" from "there was nothing to
      check" is worse than no gate, because it reassures.
- [ ] `check_corpus_policy.py` reports a published artifact with a non-zero
      chunk count. Today it reports "none published".
- [ ] No `www.birzeit.edu`, other domain, private student content or `SAMPLE`
      material in the artifact (the same script enforces this).
- [ ] Source freshness and effective dates visible in answers — ask a question
      whose source is past its refresh window and confirm the answer says so.
- [ ] Golden, refusal, grounding and navigation thresholds pass
      (`data/eval/release_set.yaml`).
- [ ] **Arabic and English content owners have approved the pilot corpus.**
      Human sign-off; record the ticket or name in `approved_by`.

## D. Extension

- [ ] Clicking the icon opens only the side-panel chat — no popup, no portal.
- [ ] Chat survives navigating between Ritaj pages.
- [ ] Every navigation action is allowlisted, confirmed and independently
      re-validated (`check_extension.py` + the node tests).
- [ ] No form submission or private-page reading — the extension holds no
      permission that would allow either.
- [ ] Permissions match the store disclosure (`check_privacy.py`).
- [ ] Zip built **from the release tag**, deterministically, checksum recorded:
      ```bash
      python scripts/package_extension.py --verify          # refuses a dirty tree
      python scripts/release_manifest.py --require-clean -o release/manifest.json
      ```
- [ ] `node scripts/e2e_extension.mjs /tmp/unzipped-package` passes against the
      **packaged** artifact, not the source directory.
- [ ] Screenshots show the side panel, not the removed popup.

## E. Privacy and operations

- [ ] Privacy policy names the actual provider, logs, retention and navigation
      behaviour (`check_privacy.py`).
- [ ] Product labelled independent everywhere: system prompt, panel header,
      store listing, privacy policy.
- [ ] Admin access fail-closed; secrets server-side only.
- [ ] **Operator passwords rotated.** The plaintext credential file on the
      maintainer's machine holds weak, username-derived passwords. Generate new
      ones and re-issue hashes:
      ```bash
      python -m ritaj.adminauth hash <username>
      python scripts/set_admins.py
      ```
- [ ] Support address, incident response, content correction and data-deletion
      procedures have **named owners** — fill in the register in
      [`docs/OPERATIONS.md`](OPERATIONS.md) §1. Every row is currently blank.
- [ ] Incident runbook read by the people on call
      ([`docs/OPERATIONS.md`](OPERATIONS.md) §3).
- [ ] Rollback drills rehearsed and timed (OPERATIONS §4). A rollback that has
      never been performed is a plan, not a capability.
- [ ] **`python scripts/check_operations.py` exits 0** — blocking here, advisory
      in CI. It is the machine check for the two items above: it fails while any
      duty lacks a primary or a backup, or any drill lacks a date and a recovery
      time, and rejects "TBD"/"the team" as owners.
- [ ] `TRUSTED_PROXY_COUNT` confirmed against the host. `/ready` reports
      `client_addressing.ok` — if false, the network rate limit is either global
      (every student in one bucket) or client-choosable (no limit at all).

## F. Staged rollout (roadmap Phase 10)

1. **Internal alpha** — maintainers only. Verify uptime and source correctness.
2. **Closed pilot** — 10–25 students, both languages, store visibility
   *Unlisted*, navigation confirmation always on, opt-in feedback only.
3. **Limited rollout** — one week of monitoring: error codes, quota, latency,
   refusal rate, navigation use, thumbs.
4. **General availability** — only after A–E are green.

Do not use raw conversation text as a product metric. The default aggregate log
mode already provides counts, latencies, error codes, source ids and grounding
verdicts, which is what these decisions need.

---

## Blocked today

These cannot be ticked from this repository, and nothing in it works around them:

| Blocker | Consequence |
|---|---|
| No authorized Ritaj corpus acquisition | Nothing to index. The service starts, reports `not-ready`, and abstains from every question. |
| No Cloudflare account + scoped token | Production refuses to start (`LLM_API_KEY` check). |
| No Hugging Face write token | Nothing can be deployed; the current 503 cannot be repaired. |
| No Chrome Web Store account / extension id | No production CORS entry, no listing. |
| No content-owner sign-off | Corpus records cannot move to `approved: true`. |
