# Chrome Web Store submission — everything pre-filled

Every field the developer console asks for, ready to copy-paste. The only two
things this folder can't contain are your Google account and the $5 fee.

**Updated 4 Aug 2026 for v1.1.0** — the popup became a side panel, navigation
actions were added, and the listing copy was corrected. See "What changed" at
the end before reusing anything from an older submission.

## 0. What's already prepared

| Requirement | Where it is |
|---|---|
| Upload package | build from the release tag (see §7), not from the working tree |
| Store icon 128×128 | inside the zip (`icons/icon128.png`) |
| Screenshots ×3 (1280×800) | **must be recaptured** — the old ones show the popup |
| Small promo tile 440×280 (optional) | `assets/promo_tile.png` |
| Privacy policy — public URL | https://mohawwad04-ritaj-rag.hf.space/privacy |
| Summary (≤132 chars) | from `manifest.json` `description` |

> The three screenshots in `assets/` show the 384×560 popup with an "open full
> portal" button and no source rows. That UI no longer exists. Submitting them
> would misrepresent the product, which is itself a policy problem — recapture
> the side panel at 1280×800 (English, Arabic, and one showing an **Open …**
> navigation button with its source row).

## 1. Register (one time)

https://chrome.google.com/webstore/devconsole → sign in → pay the **$5**
one-time registration fee → verify the account email.

Use a **project address**, not a personal one: the store displays it publicly on
the listing. `ritaj.assistant.project@gmail.com` is used in the privacy policy;
keep them the same.

## 2. New item → upload

Upload the zip built from the release tag. The name, version, icon and summary
are read from the manifest automatically.

## 3. Store listing tab

- **Description** (paste both languages in one box):

```
Ask about the Ritaj portal in Arabic or English, and open the right Ritaj page — from Chrome's side panel.

Ritaj Assistant is an independent, student-built helper for Birzeit University's Ritaj portal. It is not an official Birzeit service and is not endorsed by the university.

Ask about course registration, the academic calendar, deadlines, or how to find something on Ritaj, and get a short answer that is:

✓ SOURCED — every answer shows which Ritaj page it came from and when that page was captured. If a source may be out of date, the answer says so.
✓ CHECKED — answers are verified against their sources before you see them. When no approved source covers your question, the assistant says it doesn't know instead of guessing.
✓ NAVIGABLE — some answers offer a button such as "Open course registration", which opens a reviewed ritaj.birzeit.edu page in a tab. Only after you press it.
✓ ALONGSIDE YOUR WORK — the chat lives in Chrome's side panel and stays open while you use Ritaj.

What it cannot do: it cannot see your account, grades, schedule or balance, and it cannot register, drop, pay or submit anything for you. It never reads the page you are on.

Switch Arabic ⇄ English with one tap (ع / EN). Clear your stored history anytime with 🗑.

Information may change — the linked Ritaj page is authoritative.

—————

مساعد ريتاج — اسأل عن بوابة ريتاج بالعربية أو الإنجليزية، وافتح الصفحة المناسبة، من اللوحة الجانبية في كروم.

مساعد ريتاج مشروع طلابي مستقل، وليس خدمة رسمية من جامعة بيرزيت ولا معتمداً منها.

اسأل عن تسجيل المساقات أو التقويم الأكاديمي أو المواعيد أو كيفية الوصول إلى صفحة في ريتاج، واحصل على إجابة قصيرة:

✓ مع مصدرها: تعرض كل إجابة الصفحة التي جاءت منها وتاريخ التقاطها، وتنبّهك إن كان المصدر قد يكون قديماً.
✓ متحقَّق منها قبل عرضها. وإن لم يوجد مصدر معتمد يغطي سؤالك، يقول المساعد إنه لا يعرف بدل التخمين.
✓ مع زر لفتح صفحة ريتاج المناسبة (مثل "فتح تسجيل المساقات") — ولا تُفتح إلا بضغطك.
✓ في اللوحة الجانبية، تبقى مفتوحة أثناء استخدامك لريتاج.

ما لا يستطيعه: لا يرى حسابك ولا علاماتك ولا جدولك ولا رصيدك، ولا يستطيع التسجيل أو الحذف أو الدفع أو إرسال أي طلب نيابةً عنك، ولا يقرأ الصفحة التي تتصفحها.

بدّل بين العربية والإنجليزية بلمسة (ع / EN)، وامسح محادثاتك المحفوظة بزر 🗑.

قد تتغير المعلومات — صفحة ريتاج المرتبطة هي المرجع.
```

- **Category:** Education
- **Language:** English (Arabic text is included in the description above)
- **Screenshots:** recapture — see §0.
- **Homepage URL (optional):** https://mohawwad04-ritaj-rag.hf.space

### Claims deliberately removed from the old listing

| Old copy | Why it's gone |
|---|---|
| "✓ PRIVATE — no account, no sign-in, no tracking" | The server keeps aggregate records and the message goes to a third-party model host. "No tracking" overstates it. |
| "خصوصية كاملة" ("complete privacy") | Same, and stronger in Arabic. |
| "survives closing the popup" | There is no popup. |
| "button to the official page" | The linked page is a reviewed Ritaj page; "official" implied university endorsement. |
| "anything Birzeit" / fees, grades topics | The approved corpus is Ritaj-only. Promising fee and grade answers promises something the corpus does not contain. |

## 4. Privacy tab

- **Single purpose description:**

```
Answers user-typed questions about Birzeit University's Ritaj student portal by sending the question to the project's own backend, displaying a cited answer, and — when the user presses a button — opening a reviewed ritaj.birzeit.edu page in a tab.
```

- **Permission justifications:**

```
storage — Stores the user's chat history and language preference locally (chrome.storage.local), capped at 40 turns, so the conversation survives closing and reopening the side panel. It is never synced and never sent anywhere except as recent conversation turns accompanying the user's next question. The user can erase it with the in-panel Clear history button.

sidePanel — The extension's entire interface is a side panel that opens when the toolbar icon is clicked. It is used for nothing else.

Host permission (https://mohawwad04-ritaj-rag.hf.space/*) — This is the extension's own backend, and the only host it contacts. Each typed question, plus up to the last 8 turns of the same conversation, a random session id and the chosen language, is sent to it to generate the cited answer. No page data of any kind is sent.
```

- **Why no `tabs` permission:** the extension opens tabs with `chrome.tabs.create`
  / `chrome.tabs.update`, which Chrome does not gate behind the `tabs`
  permission. `tabs` would additionally expose tab URLs and titles, which the
  extension does not use and the privacy policy says it does not collect.
- **Why no host permission on ritaj.birzeit.edu:** the extension *navigates* to
  Ritaj pages but never reads them. Host access would grant reading.
- **Remote code:** No. All JS is packaged (MV3, ES modules, no CDN).
- **Data usage → what is collected:** tick **Personal communications** only
  (the chat messages the user types). Not: location, health, financial,
  authentication, personal identifiers, web history, user activity.
- **Certifications:** tick all three (no sale of data; no use or transfer
  unrelated to the single purpose; no use for creditworthiness/lending).
- **Privacy policy URL:**

```
https://mohawwad04-ritaj-rag.hf.space/privacy
```

  Must be live before submitting — the reviewer will open it. It is served by
  the backend, so it requires a successful deploy first.

## 5. Distribution tab

- **Visibility:** start with **Unlisted** for the closed pilot (roadmap Phase 10
  stages 1–2), then Public for the limited rollout.
- **Distribution:** all regions.
- **Pricing:** Free.

## 6. Before you submit — check these

- [ ] `python scripts/check_extension.py` passes (minimal permissions, allowlist parity)
- [ ] `python scripts/check_privacy.py` passes (disclosures match the code)
- [ ] `python scripts/check_navigation.py` passes
- [ ] The privacy policy URL loads publicly
- [ ] Screenshots show the side panel, not the popup
- [ ] The listing does not claim the product is official, private, or always correct
- [ ] Backend is deployed and `/ready` is healthy — a reviewer who types a
      question and gets an error will reject the listing

## 7. Building the package (from a tag, not the working tree)

```bash
git checkout vX.Y.Z
python scripts/package_extension.py --verify      # refuses a dirty tree
python scripts/release_manifest.py -o release/manifest.json   # records the checksum
```

A `zip -r` one-liner produces a *different archive every run* — zip records
mtimes — so the checksum in the release manifest would mean nothing, and two
people building the same tag could not compare results. The script sorts
entries, fixes timestamps and permissions, and `--verify` builds twice to prove
the output is byte-identical.

It uses an **allowlist** of runtime files rather than an exclusion list, so a
test file or store draft added later is excluded by default instead of shipping
because nobody updated a pattern.

Verify the package before submitting — the artifact, not the source directory:

```bash
python scripts/secret_inventory.py --scan-only    # scans the built ZIP too
unzip -q ritaj-assistant-extension.zip -d /tmp/pkg
node scripts/e2e_extension.mjs /tmp/pkg           # 16 checks in real Chromium
```

## 8. Updating later

1. Bump `"version"` in `manifest.json`.
2. Tag, rebuild the zip from the tag, re-run the checks in §6.
3. Dev console → the item → Package → upload → submit.

If the backend URL changes: update `config.js`, `host_permissions` in
`manifest.json`, the justification above, **and** both privacy documents.

## What changed in v1.1.0

- Popup → side panel (`sidePanel` permission added, `default_popup` removed).
- Navigation actions to reviewed `ritaj.birzeit.edu` pages, user-confirmed.
- Model host changed from Groq to Cloudflare Workers AI (disclosed in §2 of the
  privacy policy).
- The web portal no longer asks for the student's name.
- Listing copy corrected: no "complete privacy", no "official", no promise of
  fee/grade answers the approved corpus does not contain.
