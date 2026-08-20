# Store screenshots — capture checklist (T5.2)

**This cannot be automated, and the shortcuts are policy violations.** Chrome's
side panel cannot be opened programmatically, and Playwright cannot drive one.
A human loads the extension, clicks the toolbar icon, and captures the real
panel.

**Do not** substitute any of these:

- a screenshot of `sidepanel.html` opened as an ordinary browser tab — it is the
  same page, but it is not the product, and the framing is what the reviewer is
  being shown;
- a composite or mock-up assembled from pieces;
- the existing images in `chrome-extension/store/assets/` — they show the
  384×560 popup that was removed in v1.1.0, with an "open full portal" button
  and no source rows. `SUBMISSION.md` §0 already says submitting them would
  misrepresent the product.

Misrepresenting the product to the Chrome Web Store is a policy violation, not a
cosmetic problem. If the real panel cannot yet produce a given shot (see
"Blocked" below), the submission waits.

---

## Before you start

1. Build and load the extension **from the release tag**, unpacked:
   `chrome://extensions` → Developer mode → Load unpacked → the unzipped package
   directory (not the source tree).
2. Point it at a backend that is **ready** — `/ready` returns 200 with a
   non-zero chunk count. A screenshot of the abstention state is honest but
   useless as a listing image, and faking an answer to avoid it is not an option.
3. Browser window at a size that yields a **1280×800** capture. Use a clean
   profile: no unrelated extensions, no personal bookmarks, no signed-in account
   name visible.
4. Open a neutral Ritaj page in the active tab. Nothing in the tab may show
   another person's data, a real student id, or an inbox.

## The three required captures

All **1280×800 PNG**, showing the side panel docked in a real browser window.

### 1 · `shot1_en.png` — an English answer with its source row

- UI language English, one question asked and answered.
- The **source row must be visible** — a cited answer is the product's whole
  claim, and a screenshot without it advertises a chatbot instead.
- Use a question whose answer is stable prose, not a date. Suggested:
  *"How do I register for courses?"*

### 2 · `shot2_ar.png` — an Arabic answer

- UI language Arabic, RTL layout correct, Arabic answer text.
- Same requirement: the source row visible.
- Suggested: *«كيف أسجل المساقات؟»*

### 3 · `shot3_navigation.png` — an answer offering an **Open …** button

- A question that resolves to an **approved, enabled** navigation action, so the
  panel shows the confirmation button (e.g. *"Open the academic calendar"*).
- Capture the state **before** clicking: the point of the image is that the
  product asks first and never navigates on its own.
- Rename it in `assets/`; `shot3_welcome.png` describes a screen that no longer
  exists.

## Blocked until Stream 5 completes

Shot 3 **cannot be captured today**: all five actions in `data/navigation.yaml`
are `enabled: false` with an empty `approved_by`, so no navigation button will
render. Enabling one to take a picture would be the exact act T5.1 reserves for
a named approver. Capture shots 1–2 whenever a corpus exists; shot 3 waits for
approval.

## After capturing

- [ ] Three PNGs in `chrome-extension/store/assets/`, each exactly 1280×800.
- [ ] No personal data, no real student id, no other person's name anywhere in
      frame — including the browser tab strip and any page behind the panel.
- [ ] The panel is visibly a **side panel**, not a popup and not the web portal.
- [ ] Remove the warning block in `chrome-extension/store/SUBMISSION.md` §0 and
      the "must be recaptured" row in its table — only once it is no longer
      true.
- [ ] Verify the sizes:
      ```bash
      python - <<'PY'
      from pathlib import Path
      import struct
      for p in sorted(Path('chrome-extension/store/assets').glob('shot*.png')):
          head = p.read_bytes()[16:24]
          w, h = struct.unpack('>II', head)
          print(f"{p.name}: {w}x{h}", "OK" if (w, h) == (1280, 800) else "WRONG SIZE")
      PY
      ```
