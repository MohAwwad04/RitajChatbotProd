# Chrome Web Store submission — everything pre-filled

Every field the developer console asks for, ready to copy-paste. The only two
things this folder can't contain are your Google account and the $5 fee.

## 0. What's already done (nothing to prepare)

| Requirement | Where it is |
|---|---|
| Upload package | `../../ritaj-assistant-extension.zip` (repo root, matches source) |
| Store icon 128×128 | inside the zip (`icons/icon128.png`) |
| Screenshots ×3 (1280×800) | `assets/shot1_en.png`, `assets/shot2_ar.png`, `assets/shot3_welcome.png` |
| Small promo tile 440×280 (optional) | `assets/promo_tile.png` |
| Privacy policy — **live public URL** | https://gist.github.com/MohAwwad04/beff035eade5e6c34f766c0ec07c3ff5 |
| Privacy policy — on our own domain | https://mohawwad04-ritaj-rag.hf.space/privacy (live after the next backend redeploy: `HF_TOKEN=… .venv/bin/python scripts/deploy_space.py "deploy: privacy page"`) |
| Summary (≤132 chars) | auto-taken from `manifest.json` `description` (131 chars ✓) |

## 1. Register (one time)

https://chrome.google.com/webstore/devconsole → sign in → pay the **$5**
one-time registration fee → verify the account email
(**moh.awwad243@gmail.com** — the store displays it publicly on the listing).

## 2. New item → upload

Upload `ritaj-assistant-extension.zip`. The name, version (1.0.0), icon, and
summary are read from the manifest automatically.

## 3. Store listing tab

- **Description** (paste both languages in one box):

```
Instant, grounded answers about Birzeit University and the Ritaj portal — right from your Chrome toolbar.

Ritaj Assistant is a bilingual (Arabic / English) chatbot for Birzeit students. Ask about course registration, tuition and fees, grades, the academic calendar, deadlines, IT support, and anything Ritaj — and get a concise answer that is:

✓ GROUNDED — every answer is generated from a knowledge base of university information and automatically verified against it before you see it.
✓ LINKED — answers include a button to the official page (e.g. Tuition Fees), so you can confirm the source yourself.
✓ CONVERSATIONAL — follow-up questions work ("and for the MBA program?"), and your chat survives closing the popup.
✓ PRIVATE — no account, no sign-in, no tracking. Your conversation is stored only on your device; see the privacy policy.

Toggle Arabic ⇄ English with one tap (ع / EN). Start a fresh conversation anytime with ↺.

Note: this is an independent student project, not an official Birzeit University product.

—————

مساعد ريتاج — إجابات فورية وموثّقة عن جامعة بيرزيت وبوابة ريتاج، من شريط أدوات كروم مباشرة.

اسأل بالعربية أو الإنجليزية عن تسجيل المساقات، الرسوم والأقساط، العلامات، التقويم الأكاديمي، المواعيد، والدعم الفني:

✓ إجابات مبنية على قاعدة معرفية من معلومات الجامعة ويجري التحقق منها تلقائياً قبل عرضها.
✓ مع كل إجابة رابط إلى الصفحة الرسمية للتأكد من المصدر بنفسك.
✓ يفهم أسئلة المتابعة، ويحفظ المحادثة حتى بعد إغلاق النافذة.
✓ خصوصية كاملة: بلا حساب، بلا تسجيل دخول، بلا تتبع — محادثتك تبقى على جهازك فقط.

بدّل بين العربية والإنجليزية بلمسة واحدة (ع / EN)، وابدأ محادثة جديدة بزر ↺.

ملاحظة: هذا مشروع طلابي مستقل وليس منتجاً رسمياً لجامعة بيرزيت.
```

- **Category:** Education
- **Language:** English (Arabic text is included in the description above)
- **Screenshots:** upload the three PNGs from `assets/` in this order:
  `shot1_en.png`, `shot2_ar.png`, `shot3_welcome.png`
- **Small promo tile:** `assets/promo_tile.png`
- **Homepage URL (optional):** https://mohawwad04-ritaj-rag.hf.space

## 4. Privacy tab

- **Single purpose description:**

```
Answers user-typed questions about Birzeit University and its Ritaj student portal by sending the question to the project's own question-answering backend and displaying the cited answer.
```

- **Permission justifications:**

```
storage — Persists the user's chat history and language preference locally (chrome.storage.local) so the conversation survives closing the popup. This data never leaves the device except as recent conversation turns sent with the user's next question.

Host permission (https://mohawwad04-ritaj-rag.hf.space/*) — This is the extension's own backend. Each typed question (plus recent turns of the same conversation) is sent to it to generate the grounded, cited answer. No other host is contacted.
```

- **Remote code:** No, I am not using remote code. (All JS is packaged; MV3.)
- **Data usage → what is collected:** tick **Personal communications** only
  (the chat messages the user types). Everything else: not collected.
- **Certifications:** tick all three (no sale of data; no use/transfer
  unrelated to the single purpose; no use for creditworthiness/lending).
- **Privacy policy URL:**

```
https://gist.github.com/MohAwwad04/beff035eade5e6c34f766c0ec07c3ff5
```

  (After redeploying the backend you can switch it to
  `https://mohawwad04-ritaj-rag.hf.space/privacy` — same text, own domain.
  Keep the gist up if you ever change it, or update both.)

## 5. Distribution tab

- **Visibility:** Public
- **Distribution:** all regions (or at minimum Palestine + wherever students are)
- **Pricing:** Free

## 6. Submit for review

Popup-only extensions with one host permission typically clear review in 1–3
days. You'll get an email at moh.awwad243@gmail.com either way. Once published,
share the store link — any Chrome user can install it; no developer mode needed.

## Updating later (new version)

1. Edit the code, bump `"version"` in `manifest.json` (e.g. 1.0.1).
2. Re-zip: `cd chrome-extension && zip -r ../ritaj-assistant-extension.zip . -x '*.DS_Store' 'icons/icon.svg' 'README.md' 'store/*'`
3. Dev console → the item → Package → upload new zip → submit.

If the backend URL ever changes: update `config.js` **and** `host_permissions`
in `manifest.json`, plus the justifications above.
