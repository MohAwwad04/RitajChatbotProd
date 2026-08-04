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

  // Reuse an existing Ritaj tab when there is one: students commonly have the
  // portal open already, and opening a second copy of a login-gated page is
  // both confusing and slower.
  chrome.tabs.query({ url: 'https://ritaj.birzeit.edu/*' }, (tabs) => {
    const existing = tabs?.[0]
    if (existing?.id != null) {
      chrome.tabs.update(existing.id, { url: message.url, active: true })
      if (existing.windowId != null) chrome.windows.update(existing.windowId, { focused: true })
    } else {
      chrome.tabs.create({ url: message.url, active: true })
    }
    sendResponse({ ok: true })
  })

  return true // keep the message channel open for the async sendResponse
})
