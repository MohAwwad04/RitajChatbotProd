# ADR-002 — Navigation-only browser automation for v1

**Status:** accepted
**Date:** 2026-08-04

## Context

Students ask the assistant to *do* things ("register COMP233 for me", "pay my
fees"). Doing them requires authenticated writes to student records inside
Ritaj. The extension currently has `storage` permission only and no page access.

Anything beyond opening a page requires `scripting`/`tabs` host access, Chrome
Web Store browsing-data disclosures, and Birzeit authorization for automated
writes against student accounts. None of those exist today.

## Decision

Version 1 ships **navigation assistance only**:

1. The backend resolves an intent to an **action ID** from a reviewed registry
   (`data/navigation.yaml`), never to a model-produced URL.
2. The server maps the action ID to its exact canonical destination and
   validates it (scheme `https`, host exactly `ritaj.birzeit.edu`, registered
   path, registered query keys, no embedded credentials, no fragment).
3. The extension **independently re-validates** the URL before calling
   `chrome.tabs.create()`. Backend trust alone is not sufficient.
4. Navigation requires a user click. `requires_confirmation` defaults to true.

Explicitly out of scope for v1: form filling, DOM reading, clicking, submitting,
registration, drops, payments, credential handling, and reading cookies or
local storage.

## Consequences

- A hallucinated answer can never move the browser: generation and navigation
  resolution are separate code paths, and the LLM's only navigation output is an
  ID that must already exist in the registry.
- Permissions stay minimal (`storage`, `sidePanel`), which keeps the Chrome Web
  Store review narrow and the privacy disclosure short and honest.
- Some genuinely useful requests get refused with an offer to open the right
  page instead. That is the intended trade.
- Navigation precision is held to 100% on the release set — stricter than answer
  accuracy — because a wrong destination changes browser state rather than just
  telling the student something wrong.
- A server-side registry flag can disable navigation actions without a Chrome
  Web Store review, which is the rollback path if a bad destination ships.

## Revisit when

Birzeit provides an official API or written authorization for transactional
actions. That is a separate product with its own consent flow, transaction
previews, audit logs, idempotency and step-up confirmation — not an increment
on this one.
