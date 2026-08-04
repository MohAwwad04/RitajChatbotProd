# Release process

Roadmap Phase 0 (release control) and Phase 9 (CI/CD gates), written down so a
release is reproducible by someone who did not perform the last one.

## Branch model

| Branch | Purpose | Deploys to |
|---|---|---|
| `main` | integration; every change arrives by pull request | nothing automatically |
| `roadmap/*`, `feat/*`, `fix/*` | working branches | nothing |
| `preserve/*` | frozen snapshots kept for provenance; never rebased | nothing |
| `release` | what production is allowed to be built from | production Space, by hand |

Tags: `v<major>.<minor>.<patch>` on `release`. The tag is the rollback unit —
an artifact is only "a release" if `git tag --points-at HEAD` is non-empty.

Protect `main` and `release` with pull-request review + passing CI. This repo
currently has no branch protection configured; that is a GitHub setting, not a
code change, and is listed in "external inputs" below.

## Gates

**Every pull request** (`.github/workflows/ci.yml`):

1. Python lint + the model-free test suite.
2. Corpus source policy — every indexed record traces to an approved
   `ritaj.birzeit.edu` URL (`scripts/check_corpus_policy.py`).
3. Navigation registry validation — every destination is https, exactly
   `ritaj.birzeit.edu`, and registered.
4. Extension manifest validation + prohibited-permission check
   (`scripts/check_extension.py`).
5. Committed-secret scan (`scripts/secret_inventory.py --scan-only`).
6. Portal build (`npm run build`).

**Release candidate**, in this order:

1. `git tag -a vX.Y.Z` on a reviewed `release` commit.
2. `python scripts/build_index.py --publish` → immutable corpus artifact +
   `data/corpus/<version>/manifest.json` + checksum.
3. `python scripts/release_manifest.py --require-clean -o release/manifest.json`.
4. Deploy staging: `python scripts/deploy_space.py --space staging`.
5. Smoke + golden + red-team + navigation suites against staging.
6. Content-owner sign-off on the corpus (Arabic and English) — a human step.
7. Promote **the same** artifacts to production:
   `python scripts/deploy_space.py` (refuses a dirty tree; there is no override
   for production).
8. Package the extension from the tag; record the zip's sha256 in the manifest.

No rebuild between staging and production. If the artifact changes, the staging
run is void.

## Rollback

Keep the last two of each: app image (Space commit), corpus artifact
(`data/corpus/<version>/`), extension zip.

| Failure | Action | Needs store review? |
|---|---|---|
| Bad answers from new corpus | point `data/corpus/CURRENT` at the previous version, redeploy | no |
| Bad backend build | redeploy the previous tag | no |
| Wrong navigation destination | set `enabled: false` on the action in `data/navigation.yaml`, redeploy | no |
| Broken extension UI | previous zip must be re-submitted | **yes** — hours to days |

Server-side rollback must never depend on a Chrome Web Store review, which is
why navigation actions are disabled by a server-side registry flag rather than a
client update. Keep the previous API version alive until the published
extension's adoption is high enough that the old client no longer matters.

## Release manifest

`scripts/release_manifest.py` records what determines behaviour: commit SHA and
cleanliness, corpus version, LLM provider + model, extension version and zip
checksum. `deploy_space.py` writes it into the deployed tree, so the running
service can state what it is (`/ready` reports the corpus version).

## Secrets

`scripts/secret_inventory.py` prints which secrets are configured and their
fingerprints — never their values — and scans tracked files for committed
credentials. Run it before every release.

Rotate a secret if it was ever pasted into a chat, printed to a log, committed,
or packaged into an extension zip. Rotation: issue new → update the host secret
→ confirm the fingerprint changed → revoke the old one.

## External inputs this process cannot supply

- Branch protection / required-reviewer rules on GitHub.
- `HF_TOKEN` with write access, to deploy or repair the Space.
- Cloudflare account id + scoped Workers AI token.
- Birzeit authorization or an approved export for the corpus (Phase 2).
- The Chrome Web Store developer account and final extension ID.
- Human sign-off on bilingual content, privacy wording and the navigation registry.
