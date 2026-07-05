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
1. Zip the folder contents (not the parent folder):
   `cd chrome-extension && zip -r ../ritaj-assistant.zip . -x '*.DS_Store' 'icons/icon.svg' 'README.md'`
2. Create a developer account at https://chrome.google.com/webstore/devconsole
   (one-time $5 registration fee — the only non-free part of the whole stack).
3. New item → upload the zip → fill the listing (screenshots of the popup,
   category "Education", both `ar` and `en` descriptions recommended).
4. Privacy tab: declare that the extension sends the user's typed question to
   the project's own backend for answering, stores no personal data beyond the
   local chat history, and uses no remote code. Justify `storage`
   (keep chat history) and the single host permission (the backend API).
5. Submit for review (usually 1–3 days for a popup-only extension).

## Moving to a custom domain later
Change `BASE_URL` in `config.js` **and** `host_permissions` in
`manifest.json`, bump `version`, re-zip, and upload the new version.
