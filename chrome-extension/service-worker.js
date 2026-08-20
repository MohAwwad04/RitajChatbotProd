// Background service worker: open the side panel, and open validated destinations.
//
// Two jobs, both deliberately small. An MV3 service worker is terminated and
// restarted freely, so it holds no state — everything durable lives in
// chrome.storage.local, owned by the panel.

import { destinationProblem } from './navigation.js'

// Clicking the toolbar icon opens the side panel instead of a popup. This is
// the whole reason for the conversion: a popup closes the moment the student
// clicks back into the Ritaj page, which is exactly when they are following the
// instructions it just gave them. A side panel stays open while they navigate.
//
// openPanelOnActionClick needs Chrome 116; manifest.json declares that as
// minimum_chrome_version so an older browser refuses the install outright
// rather than installing an extension whose toolbar button does nothing.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('[ritaj] setPanelBehavior failed', err))
})

// setPanelBehavior is not persisted across every browser update path, so it is
// re-asserted on startup too. Setting it twice is harmless.
chrome.runtime.onStartup?.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
})

/**
 * Navigation requests from the panel.
 *
 * The URL is validated HERE as well as in the panel, because this is the
 * context that actually holds the tabs capability. The panel is a web page: a
 * bug or an injected script in it must not be able to turn a message into a
 * navigation to an arbitrary host.
 */
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'ritaj:navigate') return false

  const problem = destinationProblem(message.url)
  if (problem !== null) {
    console.warn('[ritaj] navigation refused:', problem)
    sendResponse({ ok: false, reason: 'invalid-destination' })
    return false
  }

  // Always a NEW tab. There used to be a chrome.tabs.query({url: ...}) here
  // that reused an already-open Ritaj tab, which reads as a courtesy and is
  // actually a permission bug: Chrome gates the `url` filter on tabs.query
  // behind the "tabs" permission (or host access to the matched pages), and
  // this extension deliberately requests neither. Without them the filter does
  // not match — it silently returns [] rather than throwing — so the reuse path
  // was dead code that made every open look like a fallback.
  //
  // Adding "tabs" to get it back would be the wrong trade: it grants the
  // ability to read the URL and title of every tab the student has open, to buy
  // a marginal UX nicety on a page they are about to look at anyway. The store
  // listing promises the extension cannot see their browsing; that promise is
  // worth more than the reuse.
  chrome.tabs.create({ url: message.url, active: true }, (tab) => {
    // Promise rejection is not the failure mode here — the callback form
    // reports through lastError, and reading it is also what stops Chrome
    // logging "Unchecked runtime.lastError" into the student's console.
    const err = chrome.runtime.lastError
    if (err || !tab) {
      console.warn('[ritaj] tabs.create failed:', err?.message ?? 'no tab returned')
      sendResponse({ ok: false, reason: 'open-failed' })
      return
    }
    sendResponse({ ok: true })
  })

  return true // keep the message channel open for the async sendResponse
})
