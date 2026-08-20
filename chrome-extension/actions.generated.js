// GENERATED FILE — do not edit by hand.
//
// Written by scripts/sync_extension_actions.py from data/navigation.yaml, and
// checked by scripts/check_extension.py, which fails the build if this file and
// the registry disagree.
//
// This is the extension's offline copy of the reviewed destinations. It is what
// makes the page-finder work when the backend is unreachable — asleep, mid
// redeploy, or deliberately `not-ready` because no corpus has been approved yet.
// When the network IS available the panel prefers /v2/navigation/actions, so a
// destination can be withdrawn server-side without waiting for a Store review.
//
// Only approved, enabled actions appear here. Every URL in this file is still
// validated by navigation.js before chrome.tabs.create() is called: a generated
// file is not a trusted file, and the point of the client-side check is that it
// does not trust its own inputs either.
//
// No destination is approved yet: every action in data/navigation.yaml is
// `enabled: false` with an empty `approved_by`, pending a human opening each
// URL in a signed-out browser. The panel renders no page-finder buttons in
// this state, which is the honest outcome — see cowork_ritaj/human-actions.md
// section H4.

export const REGISTRY_VERSION = '4f53cda18c2b'

export const BUNDLED_ACTIONS = []
