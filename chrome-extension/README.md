# Ritaj Assistant — Chrome extension

A Manifest V3 popup chat that talks to the hosted Ritaj RAG backend
(`https://mohawwad04-ritaj-rag.hf.space`). No build step — plain HTML/CSS/JS.

## What it does
- Streams grounded, cited answers about Birzeit University / the Ritaj portal.
- Arabic ⇄ English toggle (auto-detects the browser language on first run).
- **Conversation memory**: the popup keeps the chat in `chrome.storage.local`
  and replays prior turns with each message, so follow-ups work and the chat
  survives closing the popup. "↺" starts a fresh conversation.
- Shows the verified page links the backend attaches to cited answers.

## Test locally (no store account needed)
1. Open `chrome://extensions`, enable **Developer mode** (top right).
2. **Load unpacked** → select this `chrome-extension/` folder.
3. Pin "Ritaj Assistant" and click its icon.

## Publish to the Chrome Web Store
Everything is prepared in **`store/SUBMISSION.md`** — the upload zip
(`../ritaj-assistant-extension.zip`), 1280×800 screenshots + promo tile
(`store/assets/`), bilingual listing copy, permission justifications,
data-usage answers, and a live privacy-policy URL. Follow it top to bottom;
the only inputs it can't provide are your Google account and the one-time $5
developer fee.

To rebuild the zip after a code change (bump `version` in the manifest first):
`cd chrome-extension && zip -r ../ritaj-assistant-extension.zip . -x '*.DS_Store' 'icons/icon.svg' 'README.md' 'store/*'`

## Moving to a custom domain later
Change `BASE_URL` in `config.js` **and** `host_permissions` in
`manifest.json`, bump `version`, re-zip, and upload the new version.
