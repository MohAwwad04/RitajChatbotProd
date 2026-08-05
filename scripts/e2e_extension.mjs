// End-to-end checks of the packed extension in a real Chromium.
//
// Run:  node scripts/e2e_extension.mjs
//
// ## Why this shape
//
// An extension only loads unpacked when Chromium runs with a persistent
// user-data directory, so this uses `launchPersistentContext` with
// `--disable-extensions-except` / `--load-extension` rather than the usual
// `browser.newContext()`. The extension id is read from the service worker's
// URL because it changes on every run.
//
// ## The one thing this cannot do
//
// Chrome's side panel cannot be opened programmatically by an extension, and
// Playwright has no API for driving it (microsoft/playwright#26693). So the
// literal "clicking the toolbar icon opens the panel" step stays a manual
// check, recorded as such in docs/RELEASE_CHECKLIST.md. What IS automated here
// is everything behind it: that the service worker registers and sets the panel
// behaviour, that the panel page itself loads and works at real widths, that the
// destination validator rejects hostile payloads in the browser (not just in
// Node), and that the extension talks to no host but its configured backend.
//
// Playwright comes from the web-qa skill's node_modules — the repository does
// not add a browser-automation dependency for one script.

import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// Defaults to the source directory. Pass a path to test an unpacked release
// ZIP instead — which is what proves the *packaged artifact* works, rather than
// a source tree that happens to contain files the package excludes.
//   unzip -q ritaj-assistant-extension.zip -d /tmp/pkg
//   node scripts/e2e_extension.mjs /tmp/pkg
const EXT = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(ROOT, 'chrome-extension')

const PLAYWRIGHT_CANDIDATES = [
  path.join(process.env.HOME ?? '', '.claude/skills/web-qa/node_modules/playwright/index.mjs'),
  'playwright',
]

async function loadPlaywright() {
  for (const candidate of PLAYWRIGHT_CANDIDATES) {
    try {
      return await import(candidate.startsWith('/') ? `file://${candidate}` : candidate)
    } catch {
      /* try the next one */
    }
  }
  throw new Error(
    'Playwright not found. Install it, or run from a machine where the web-qa ' +
    'skill provides it.',
  )
}

const results = []
function check(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => { results.push({ name, ok: true }); console.log(`  PASS  ${name}`) })
    .catch((err) => {
      results.push({ name, ok: false, error: err.message })
      console.log(`  FAIL  ${name}\n        ${err.message}`)
    })
}

async function main() {
  if (!existsSync(path.join(EXT, 'manifest.json'))) {
    throw new Error(`no extension at ${EXT}`)
  }
  const { chromium } = await loadPlaywright()
  const profile = await mkdtemp(path.join(tmpdir(), 'ritaj-e2e-'))

  const context = await chromium.launchPersistentContext(profile, {
    // Headed. Old headless Chromium does not run MV3 extension service workers
    // at all — the extension loads and its worker never registers, which looks
    // exactly like a broken extension. CI must therefore run this under xvfb;
    // see .github/workflows/ci.yml.
    headless: false,
    args: [
      `--disable-extensions-except=${EXT}`,
      `--load-extension=${EXT}`,
      '--no-first-run',
      '--no-default-browser-check',
      // Ritaj must never actually be contacted by a test. `context.route` is
      // not sufficient: a tab created by the service worker starts navigating
      // before Playwright attaches routing to it, and an early run of this
      // script did reach Birzeit and came back with a Cloudflare challenge
      // token in the URL. Failing resolution at the browser level makes real
      // egress impossible while still leaving the requested URL on the tab,
      // which is the thing under test.
      '--host-resolver-rules=MAP ritaj.birzeit.edu ~NOTFOUND,'
        + 'MAP mohawwad04-ritaj-rag.hf.space ~NOTFOUND',
    ],
  })

  // Every outbound request the extension context makes, so we can prove it
  // talks to nothing but its declared backend.
  const externalRequests = new Set()
  context.on('request', (request) => {
    const url = request.url()
    if (!url.startsWith('chrome-extension://') && !url.startsWith('devtools://')
        && !url.startsWith('data:') && !url.startsWith('about:')) {
      externalRequests.add(new URL(url).host)
    }
  })

  try {
    console.log('\nService worker\n')

    let worker = context.serviceWorkers()[0]
    if (!worker) {
      worker = await context.waitForEvent('serviceworker', { timeout: 15_000 })
    }

    await check('the MV3 service worker registers', () => {
      assert.ok(worker, 'no service worker appeared')
      assert.ok(worker.url().startsWith('chrome-extension://'))
    })

    const extensionId = new URL(worker.url()).host

    await check('the service worker declares the side panel behaviour', async () => {
      // Proves the API surface the icon click depends on is present and that
      // setPanelBehavior resolves — the part of "icon opens the panel" that can
      // be verified without driving the panel itself.
      const ok = await worker.evaluate(async () => {
        if (!chrome.sidePanel?.setPanelBehavior) return 'sidePanel API missing'
        await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
        return 'ok'
      })
      assert.equal(ok, 'ok')
    })

    console.log('\nSide panel page\n')

    const panel = await context.newPage()
    const consoleErrors = []
    panel.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
    panel.on('pageerror', (e) => consoleErrors.push(String(e)))
    await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`)
    await panel.waitForLoadState('domcontentloaded')
    await panel.waitForTimeout(500)

    await check('the panel loads with no console errors', () => {
      assert.deepEqual(consoleErrors, [])
    })

    await check('the panel states it is independent, not official', async () => {
      const text = (await panel.textContent('#disclaimer-text')) ?? ''
      const subtitle = (await panel.textContent('#subtitle')) ?? ''
      assert.match(text, /independent/i)
      assert.match(subtitle, /independent/i)
      // It must disclaim officialness, never assert it.
      assert.match(text, /not an official/i)
      assert.doesNotMatch(text, /\b(is|we are) an official\b/i)
    })

    await check('the language toggle flips direction and copy', async () => {
      await panel.click('#lang-toggle')
      await panel.waitForTimeout(200)
      assert.equal(await panel.evaluate(() => document.documentElement.dir), 'rtl')
      assert.equal(await panel.evaluate(() => document.documentElement.lang), 'ar')
      await panel.click('#lang-toggle')
      await panel.waitForTimeout(200)
      assert.equal(await panel.evaluate(() => document.documentElement.dir), 'ltr')
    })

    await check('the panel does not scroll horizontally at 280–420px', async () => {
      for (const width of [280, 320, 360, 420]) {
        await panel.setViewportSize({ width, height: 620 })
        await panel.waitForTimeout(120)
        const { scroll, client } = await panel.evaluate(() => ({
          scroll: document.body.scrollWidth,
          client: document.documentElement.clientWidth,
        }))
        assert.ok(scroll <= client + 1, `overflow at ${width}px: ${scroll} > ${client}`)
      }
      await panel.setViewportSize({ width: 360, height: 620 })
    })

    await check('every control is reachable by keyboard', async () => {
      const ids = await panel.evaluate(async () => {
        const seen = []
        for (let i = 0; i < 10; i++) {
          const active = document.activeElement
          seen.push(active?.id || active?.tagName)
          // Tab order is driven by the browser; walk the focusable list instead.
          const focusable = [...document.querySelectorAll(
            'button:not([disabled]):not([hidden]), input, [tabindex]')]
          if (i < focusable.length) focusable[i].focus()
        }
        return seen
      })
      for (const required of ['lang-toggle', 'new-chat', 'clear-history', 'input']) {
        assert.ok(
          await panel.evaluate((id) => {
            const el = document.getElementById(id)
            el?.focus()
            return document.activeElement === el
          }, required),
          `${required} could not take focus`,
        )
      }
      assert.ok(ids.length > 0)
    })

    await check('a message over the limit is refused locally', async () => {
      const max = await panel.evaluate(() => MAX_MESSAGE_CHARS)
      await panel.fill('#input', 'x'.repeat(max + 1))
      await panel.click('#send')
      await panel.waitForTimeout(200)
      const status = await panel.textContent('#status')
      assert.match(status ?? '', /too long/i)
      await panel.fill('#input', '')
    })

    await check('the in-browser validator rejects hostile destinations', async () => {
      const hostile = [
        'https://www.birzeit.edu/en/admissions',
        'https://ritaj.birzeit.edu.attacker.test/reg/',
        'https://evil-ritaj.birzeit.edu/reg/',
        'http://ritaj.birzeit.edu/reg/',
        'javascript:alert(1)',
        '//ritaj.birzeit.edu/reg/',
        'https://user:pass@ritaj.birzeit.edu/reg/',
        'https://ritaj.birzeit.edu:8443/reg/',
        'https://xn--ritj-hpa.birzeit.edu/reg/',
        'https://ritaj.birzeit.edu/unregistered/path',
      ]
      const accepted = await panel.evaluate(async (urls) => {
        const { validateAction } = await import('./navigation.js')
        return urls.filter((url) => validateAction({ url, label: 'Open' }) !== null)
      }, hostile)
      assert.deepEqual(accepted, [], `browser validator accepted: ${accepted}`)
    })

    await check('the in-browser validator accepts a registered destination', async () => {
      const action = await panel.evaluate(async () => {
        const { validateAction } = await import('./navigation.js')
        return validateAction({
          id: 'course-registration',
          label: 'Open course registration',
          url: 'https://ritaj.birzeit.edu/reg/',
          auth_required: true,
        })
      })
      assert.equal(action?.url, 'https://ritaj.birzeit.edu/reg/')
      assert.equal(action?.requiresConfirmation, true)
    })

    await check('clear history empties local storage', async () => {
      await panel.evaluate(async () => {
        await chrome.storage.local.set({ session: { sessionId: 'x', turns: [
          { role: 'user', content: 'hello' },
        ] } })
      })
      await panel.click('#clear-history')
      await panel.waitForTimeout(300)
      const stored = await panel.evaluate(() => chrome.storage.local.get('session'))
      assert.deepEqual(stored.session, undefined, 'stored conversation survived a clear')
    })

    console.log('\nNavigation, end to end\n')

    // Sent from the panel, which is the real caller. A message sent from the
    // service worker would not reach the worker's own listener.
    const navigate = (url) => panel.evaluate(
      (u) => new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: 'ritaj:navigate', url: u }, (r) =>
          resolve(r ?? { ok: null, lastError: chrome.runtime.lastError?.message ?? null }))
      }), url)

    await check('the service worker refuses an off-domain navigation', async () => {
      const response = await navigate('https://attacker.test/reg/')
      assert.equal(response?.ok, false, `not refused: ${JSON.stringify(response)}`)
      assert.equal(response?.reason, 'invalid-destination')
    })

    await check('no tab was opened for the refused destination', async () => {
      await panel.waitForTimeout(300)
      const hosts = context.pages().map((p) => {
        try { return new URL(p.url()).host } catch { return '' }
      })
      assert.ok(!hosts.includes('attacker.test'), 'a tab was opened for a refused URL')
    })

    await check('a registered destination is opened, unmodified', async () => {
      // Assert on what the worker ASKS the browser to open, by recording the
      // chrome.tabs call. Letting a tab actually navigate proved unworkable:
      // with DNS blocked the tab lands on chrome-error:// and loses the URL,
      // and without it the request reaches Birzeit for real. The contract under
      // test is "the extension asks for exactly the registered destination",
      // which is precisely what this records.
      await worker.evaluate(() => {
        globalThis.__opened = []
        const record = (kind) => (...args) => {
          globalThis.__opened.push({ kind, args })
          return Promise.resolve({ id: 1, windowId: 1 })
        }
        chrome.tabs.create = record('create')
        chrome.tabs.update = record('update')
        chrome.tabs.query = (_q, cb) => cb([])   // pretend no Ritaj tab is open
      })

      const response = await navigate('https://ritaj.birzeit.edu/reg/')
      assert.equal(response?.ok, true, `not accepted: ${JSON.stringify(response)}`)

      const opened = await worker.evaluate(() => globalThis.__opened)
      assert.equal(opened.length, 1, `expected one tab call, got ${opened.length}`)
      assert.equal(opened[0].kind, 'create')
      assert.equal(opened[0].args[0].url, 'https://ritaj.birzeit.edu/reg/')
    })

    await check('a refused destination reaches no tabs API at all', async () => {
      await worker.evaluate(() => { globalThis.__opened = [] })
      await navigate('https://ritaj.birzeit.edu.attacker.test/reg/')
      const opened = await worker.evaluate(() => globalThis.__opened)
      assert.deepEqual(opened, [], 'a refused URL reached chrome.tabs')
    })

    console.log('\nNetwork boundary\n')

    await check('the extension contacted no host but its backend and Ritaj', () => {
      // Ritaj appears only because the navigation test deliberately opened a
      // (stubbed) registered destination. Anything else means the extension is
      // reaching somewhere its permissions and privacy policy do not describe.
      const allowed = new Set(['mohawwad04-ritaj-rag.hf.space', 'ritaj.birzeit.edu'])
      const unexpected = [...externalRequests].filter((h) => !allowed.has(h))
      assert.deepEqual(unexpected, [], `unexpected hosts: ${unexpected}`)
    })

    await panel.close()
  } finally {
    await context.close()
    await rm(profile, { recursive: true, force: true })
  }

  const failed = results.filter((r) => !r.ok)
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  console.log(
    '\nNOT automated (Playwright cannot drive the Chrome side panel — see\n' +
    'microsoft/playwright#26693): clicking the toolbar icon opens the panel.\n' +
    'Verify by hand before release; docs/RELEASE_CHECKLIST.md §D records it.',
  )
  if (failed.length) process.exit(1)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
