// Screenshot the side panel as it really renders, in a real Chromium.
//
// Not a test — a way to look at the thing. The Store listing needs truthful
// captures (cowork_ritaj/screenshot-checklist.md), and more immediately, a
// person changing the panel's CSS should be able to see the result without
// installing the extension by hand.
//
// The panel page is loaded directly by its chrome-extension:// URL at the width
// Chrome actually docks a side panel to. That is not the same as "the side
// panel", which Playwright cannot drive (microsoft/playwright#26693) — but it
// is the same document, the same stylesheet and the same code path, so what it
// shows is what a student sees.
//
// Run:  node scripts/screenshot_panel.mjs [outdir]
//
// Playwright comes from the web-qa skill's node_modules, like e2e_extension.mjs.

import { existsSync } from 'node:fs'
import { mkdir } from 'node:fs/promises'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const EXT = path.join(ROOT, 'chrome-extension')
const OUT = process.argv[2] ?? path.join(ROOT, 'release', 'screenshots')

async function loadPlaywright() {
  const candidates = [
    path.join(process.env.HOME ?? '', '.claude/skills/web-qa/node_modules/playwright/index.mjs'),
    'playwright',
  ]
  for (const candidate of candidates) {
    try {
      if (candidate.startsWith('/') && !existsSync(candidate)) continue
      return await import(candidate)
    } catch {
      /* try the next one */
    }
  }
  throw new Error('playwright not found — install it or run the web-qa skill once')
}

// Chrome's side panel is user-resizable. 400px is roughly the default dock
// width; 320px is the narrow case the CSS has a breakpoint for.
const WIDTHS = [
  { name: 'default', width: 400, height: 720 },
  { name: 'narrow', width: 300, height: 720 },
]

const { chromium } = await loadPlaywright()
await mkdir(OUT, { recursive: true })
const profile = await mkdtemp(path.join(tmpdir(), 'ritaj-shot-'))

const context = await chromium.launchPersistentContext(profile, {
  headless: false,
  args: [
    `--disable-extensions-except=${EXT}`,
    `--load-extension=${EXT}`,
    '--no-first-run',
    '--no-default-browser-check',
    // Same blackhole as the E2E harness: a screenshot run must not touch
    // Birzeit, and the offline render is the state worth photographing anyway
    // — it is what a student sees while the backend is down.
    '--host-resolver-rules=MAP ritaj.birzeit.edu ~NOTFOUND,'
      + 'MAP mohawwad04-ritaj-rag.hf.space ~NOTFOUND',
  ],
})

try {
  let worker = context.serviceWorkers()[0]
  if (!worker) worker = await context.waitForEvent('serviceworker', { timeout: 15_000 })
  const extensionId = new URL(worker.url()).host

  const page = await context.newPage()
  await page.goto(`chrome-extension://${extensionId}/sidepanel.html`)
  await page.waitForLoadState('domcontentloaded')

  for (const { name, width, height } of WIDTHS) {
    await page.setViewportSize({ width, height })
    for (const lang of ['en', 'ar']) {
      // The toggle is the real control; setting state through it exercises the
      // same path a student would, including the RTL flip.
      const current = await page.evaluate(() => document.documentElement.lang)
      if (current !== lang) await page.click('#lang-toggle')
      await page.waitForTimeout(400)
      const file = path.join(OUT, `panel-${name}-${lang}.png`)
      await page.screenshot({ path: file })
      console.log(`  wrote ${path.relative(ROOT, file)}  (${width}x${height}, ${lang})`)
    }
  }

  // Dark mode: Chrome side panels follow the browser theme, and an unstyled
  // dark panel is unreadable rather than merely unfashionable.
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.setViewportSize({ width: 400, height: 720 })
  await page.waitForTimeout(300)
  const darkFile = path.join(OUT, 'panel-dark.png')
  await page.screenshot({ path: darkFile })
  console.log(`  wrote ${path.relative(ROOT, darkFile)}  (dark)`)

  await page.close()
} finally {
  await context.close()
  await rm(profile, { recursive: true, force: true })
}

console.log(`\nScreenshots in ${path.relative(ROOT, OUT)}/`)
console.log(
  'These show the panel with the backend unreachable, which is its current\n'
  + 'real state. Store screenshots need a working backend and at least one\n'
  + 'approved destination first — see cowork_ritaj/screenshot-checklist.md.',
)
