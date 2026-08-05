# Ritaj Assistant — Chrome extension

A Manifest V3 **side panel** chat that talks to the hosted Ritaj RAG backend
(`https://mohawwad04-ritaj-rag.hf.space`). No build step — plain HTML/CSS/JS
ES modules, nothing loaded remotely.

It is an **independent student project**, not an official Birzeit service.

## What it does

- Opens in Chrome's **side panel** when you click the toolbar icon, and stays
  open while you use Ritaj. (It was a popup until v1.1.0 — a popup closes the
  moment you click back into the page it just gave you instructions for.)
- Streams grounded answers about the Ritaj portal, in Arabic or English.
- Shows each answer's **source**: page name, host, and the date that page was
  captured — with a badge when a source is past its refresh window.
- Offers a **navigation button** ("Open course registration") for reviewed
  `ritaj.birzeit.edu` destinations, opened only after you click it.
- Keeps the conversation in `chrome.storage.local`, capped at 40 turns / ~120 KB,
  and replays prior turns so follow-ups work. 🗑 erases it completely.
- ⏹ stops a streaming answer — which matters on a metered provider, where an
  abandoned stream still spends the day's quota.

## What it will not do

No content scripts, no `tabs`/`activeTab`/`scripting` permission, no host access
to `ritaj.birzeit.edu`. It cannot read the page you are on, its DOM, cookies,
form values or login session, and it cannot register, drop, pay or submit
anything. See [ADR-002](../docs/adr/ADR-002-navigation-only-automation.md).

## Files

| File | Role |
|---|---|
| `manifest.json` | MV3: `side_panel`, module service worker, permissions `storage` + `sidePanel` |
| `service-worker.js` | Opens the panel on icon click; the only code that touches `chrome.tabs` |
| `sidepanel.{html,css,js}` | The chat UI — fluid width, RTL-aware, dark-mode aware |
| `navigation.js` | **Independent** destination validation, re-run before any tab is opened |
| `navigation.test.mjs` | Tests for that validator (`node --test`) |
| `config.js` | Backend URL and the message-length limit, kept in step with the server by CI |

`navigation.js` deliberately duplicates the server's URL policy. An independent
check that read its allowlist from the response it is checking would not be
independent — the point is to survive a compromised or impersonated backend.
`scripts/check_extension.py` fails the build if the two drift.

## Test locally

```bash
node --test chrome-extension/navigation.test.mjs   # validator unit tests
python scripts/check_extension.py                  # permissions + parity gates
node scripts/e2e_extension.mjs                     # real Chromium, unpacked
```

Then, by hand:

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select this `chrome-extension/` folder.
3. Pin "Ritaj Assistant" and click its icon — the side panel should open.

Chrome's side panel cannot be opened programmatically by an extension, and
Playwright has no API for driving it ([playwright#26693]). The automated E2E
therefore drives the panel *page* directly at its `chrome-extension://` URL and
checks the service worker separately; the icon-click-opens-the-panel step is the
one thing that stays a manual check.

[playwright#26693]: https://github.com/microsoft/playwright/issues/26693

## Publish to the Chrome Web Store

Everything is prepared in **`store/SUBMISSION.md`**: listing copy in both
languages, permission justifications, data-usage answers, and the pre-submission
checklist.

Build the package from a release tag, never from the working tree:

```bash
python scripts/package_extension.py          # refuses a dirty tree
```

**The screenshots in `store/assets/` are stale** — they show the removed popup.
Recapture before submitting; `store/SUBMISSION.md` §0 explains what is needed.
