# Release checklist

The roadmap's "definition of ready to release" (§8) with a command against each
item, so readiness is something you can run rather than something you believe.
Items with no command are human judgements; they say so.

Run from a clean checkout of the release tag.

---

## A. Gates that must be green

```bash
pytest -q                                   # backend unit + integration
node --test chrome-extension/navigation.test.mjs
python scripts/check_corpus_policy.py       # every chunk traces to an approved Ritaj URL
python scripts/check_navigation.py          # destinations reviewed; 18 URL attacks rejected
python scripts/check_extension.py           # minimal permissions; allowlist parity
python scripts/check_privacy.py             # disclosures match the code
python scripts/eval_release.py              # scope refusals, injection, URL rejection
python scripts/eval_release.py --gate       # release-set completeness
python scripts/secret_inventory.py          # secrets present; nothing committed
python scripts/sbom.py --check-pinned       # deployables reproducible
cd ritaj-student-portal && npm run build
```

`--gate` currently **fails**: the answerable / calendar / navigation categories
are empty because they cannot be written against a corpus that does not exist.
That is the honest blocker, not a formality to waive.

---

## B. Service

- [ ] Production `/live` returns 200 and `/ready` returns 200.
- [ ] Three consecutive cold starts succeed inside the host timeout.
      `/ready` reports `timings_ms.listening` — it should be seconds, not minutes.
- [ ] `python scripts/sbom.py` produced no unresolved critical/high finding.
- [ ] Base image pinned by digest — currently pinned by tag:
      ```bash
      docker pull python:3.11-slim
      docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
      # put the resulting python@sha256:… in the Dockerfile FROM line
      ```
- [ ] `/admin/usage` shows budget, concurrency and circuit state, and someone
      is watching it.
- [ ] **Rollback rehearsed, not just documented**: point
      `data/corpus/CURRENT` at the previous version, redeploy, confirm answers
      change, then roll forward again.

## C. Data and answers

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
- [ ] Zip built **from the release tag**, checksum recorded in
      `release/manifest.json`:
      ```bash
      python scripts/release_manifest.py --require-clean -o release/manifest.json
      ```
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
      procedures have **named owners**. Human step.

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
