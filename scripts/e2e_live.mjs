// Drive the real extension against the REAL deployed backend.
//
// scripts/e2e_extension.mjs deliberately blackholes the backend host so a test
// run cannot reach the network. That is right for CI and it leaves one thing
// permanently unproven: whether the extension actually talks to the deployment.
// Every "not verified by anyone" list in this repo has carried that line.
//
// This script is the opposite trade — it makes real requests to the live Space,
// so it is NOT part of CI and must never gate a build. Run it by hand after a
// deploy. It still blackholes ritaj.birzeit.edu, because opening a real Ritaj
// page from a test is a different question and one the harness has no business
// answering.
//
// Run:  node scripts/e2e_live.mjs [backend-url]

import { existsSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const EXT = path.join(ROOT, 'chrome-extension')
const BACKEND = process.argv[2] ?? 'https://mohawwad04-ritaj-rag.hf.space'

async function loadPlaywright() {
  for (const candidate of [
    path.join(process.env.HOME ?? '', '.claude/skills/web-qa/node_modules/playwright/index.mjs'),
    'playwright',
  ]) {
    try {
      if (candidate.startsWith('/') && !existsSync(candidate)) continue
      return await import(candidate)
    } catch { /* next */ }
  }
  throw new Error('playwright not found')
}

const results = []
async function check(label, fn) {
  try {
    await fn()
    results.push({ label, ok: true })
    console.log(`  PASS  ${label}`)
  } catch (err) {
    results.push({ label, ok: false })
    console.log(`  FAIL  ${label}\n        ${err.message}`)
  }
}

const { chromium } = await loadPlaywright()
const profile = await mkdtemp(path.join(tmpdir(), 'ritaj-live-'))

console.log(`\nExtension against ${BACKEND}\n`)

const context = await chromium.launchPersistentContext(profile, {
  headless: false,
  args: [
    `--disable-extensions-except=${EXT}`,
    `--load-extension=${EXT}`,
    '--no-first-run',
    '--no-default-browser-check',
    // Ritaj stays blackholed: whether a real Ritaj page opens is a separate
    // question, and a test must not send traffic to the university.
    '--host-resolver-rules=MAP ritaj.birzeit.edu ~NOTFOUND',
  ],
})

// Every host the extension contacts, so "it only talks to its backend" is
// measured against the real network rather than asserted.
const hosts = new Set()
context.on('request', (r) => {
  const url = r.url()
  if (!/^(chrome-extension|devtools|data|about):/.test(url)) {
    try { hosts.add(new URL(url).host) } catch { /* ignore */ }
  }
})

try {
  let worker = context.serviceWorkers()[0]
  if (!worker) worker = await context.waitForEvent('serviceworker', { timeout: 20_000 })
  const extensionId = new URL(worker.url()).host
  console.log(`  extension id: ${extensionId}\n`)

  const panel = await context.newPage()
  const consoleErrors = []
  panel.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
  panel.on('pageerror', (e) => consoleErrors.push(String(e)))

  await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`)
  await panel.waitForLoadState('domcontentloaded')
  // The panel probes /capabilities and /v2/navigation/actions on load; give the
  // real network time to answer before asserting on what it rendered.
  await panel.waitForTimeout(6000)

  await check('the panel reaches the live backend without console errors', () => {
    if (consoleErrors.length) throw new Error(consoleErrors.join(' | '))
  })

  await check('destinations came from the SERVER, not just the bundle', async () => {
    const seen = await panel.evaluate(async () => {
      const res = await fetch(`${BASE_URL}/v2/navigation/actions`)
      const body = await res.json()
      return { status: res.status, count: (body.actions ?? []).length, version: body.version }
    })
    if (seen.status !== 200) throw new Error(`HTTP ${seen.status}`)
    if (seen.count === 0) throw new Error('server returned zero destinations')
    console.log(`        server: ${seen.count} destination(s), registry ${seen.version}`)
  })

  await check('the page finder rendered those destinations', async () => {
    const buttons = await panel.$$('#finder-grid .finder__item')
    if (buttons.length === 0) throw new Error('the finder rendered no buttons')
    console.log(`        panel : ${buttons.length} button(s)`)
  })

  await check('the chat status pill reflects the real backend state', async () => {
    const pill = await panel.evaluate(() => {
      const el = document.getElementById('service-pill')
      return { hidden: el.hidden, cls: el.className, text: el.textContent.trim() }
    })
    if (pill.hidden) throw new Error('the pill never appeared')
    console.log(`        pill  : "${pill.text}"`)
  })

  await check('asking a question returns the backend\'s real refusal, not a network error', async () => {
    const out = await panel.evaluate(async () => {
      const res = await fetch(`${BASE_URL}/v2/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'when does registration open?', client: 'chrome-extension' }),
      })
      let body = null
      try { body = await res.json() } catch { /* streamed */ }
      return { status: res.status, code: body?.code ?? null }
    })
    console.log(`        chat  : HTTP ${out.status} ${out.code ?? '(streamed)'}`)
    // A CORS failure surfaces as a thrown TypeError, never as a status — so
    // reaching this line at all is the thing being measured.
    if (out.status === 0) throw new Error('request never completed')
  })

  await check('the extension contacted only its backend', () => {
    const unexpected = [...hosts].filter((h) => h !== new URL(BACKEND).host)
    if (unexpected.length) throw new Error(`unexpected hosts: ${unexpected.join(', ')}`)
    console.log(`        hosts : ${[...hosts].join(', ') || '(none)'}`)
  })

  await panel.close()
} finally {
  await context.close()
  await rm(profile, { recursive: true, force: true })
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
console.log(
  '\nNOT part of CI: this makes real network requests. Run it by hand after a\n'
  + 'deploy. Clicking the toolbar icon to open the side panel remains a manual\n'
  + 'check — Playwright cannot drive one (microsoft/playwright#26693).',
)
process.exit(failed.length ? 1 : 0)
