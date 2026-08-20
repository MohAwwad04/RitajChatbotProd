// Independent destination validation — the extension does NOT trust the backend.
//
// The server already validates every navigation URL against a reviewed registry
// (src/ritaj/navigation.py). This re-implements that check on the client anyway,
// because the two failures it covers are exactly the ones server-side validation
// cannot: a compromised or impersonated backend, and a bug that lets an
// unreviewed URL into a response.
//
// The extension is what actually calls chrome.tabs.create(). Whatever holds that
// capability has to do its own checking — "the server said it was fine" is not a
// security property when the server is the thing that might be wrong.
//
// Deliberately dependency-free and synchronous so it can be reasoned about in
// full by a Chrome Web Store reviewer.

const ALLOWED_HOST = 'ritaj.birzeit.edu'
const ALLOWED_PROTOCOL = 'https:'

// Mirrors data/navigation.yaml. Duplicated on purpose: an independent check
// that reads its allowlist from the response it is checking is not independent.
// Kept in sync by scripts/check_extension.py, which fails the build on drift.
const ALLOWED_PATHS = new Set([
  '/',
  '/reg',
  '/academic-calendar',
  '/hemis/courses',
  '/bzu-msgs/boards',
])

const SAFE_QUERY_KEYS = {
  '/hemis/courses': new Set(['term']),
}

/**
 * Why `rawUrl` may not be opened, or null if it may be.
 * Returning the reason (rather than a boolean) so a rejection can be logged
 * locally without guessing which rule fired.
 */
export function destinationProblem(rawUrl) {
  if (typeof rawUrl !== 'string' || rawUrl.length === 0) return 'empty'
  if (rawUrl.length > 500) return 'too long'
  // Whitespace and backslashes let a URL be re-parsed differently by whatever
  // reads it next; reject rather than normalise.
  if (/[\s\\]/.test(rawUrl)) return 'contains whitespace or a backslash'
  // "//host/path" inherits the current scheme — a classic host-smuggling shape.
  if (rawUrl.startsWith('//')) return 'scheme-relative'
  // Traversal is judged on the RAW string, before parsing. `new URL()` resolves
  // `..` during parsing, so the check below on `url.pathname` could never fire:
  // `/reg/../../etc/passwd` reaches it already flattened to `/etc/passwd`. The
  // ALLOWED_PATHS lookup was rejecting that case for an unrelated reason, which
  // is a fine outcome and a bad reason — remove one path from the allowlist and
  // the traversal defence would have silently gone with it.
  if (/(^|\/)\.\.?(\/|$)/.test(rawUrl.replace(/^https?:\/\/[^/]*/i, ''))) {
    return 'path traversal'
  }
  if (/%2e/i.test(rawUrl)) return 'encoded dot in path'

  let url
  try {
    url = new URL(rawUrl)
  } catch {
    return 'unparseable'
  }

  if (url.protocol !== ALLOWED_PROTOCOL) return `protocol ${url.protocol}`
  // hostname (not host) excludes the port; compared exactly, so sibling
  // subdomains, suffix tricks and punycode homoglyphs all fail.
  if (url.hostname.toLowerCase() !== ALLOWED_HOST) return `host ${url.hostname}`
  if (url.port && url.port !== '443') return `port ${url.port}`
  if (url.username || url.password) return 'embedded credentials'
  if (url.hash) return 'fragment'

  const path = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, '') : '/'
  if (!ALLOWED_PATHS.has(path)) return `path ${path} is not registered`

  const safeKeys = SAFE_QUERY_KEYS[path] ?? new Set()
  for (const key of url.searchParams.keys()) {
    if (!safeKeys.has(key)) return `query parameter ${key} is not permitted`
  }

  return null
}

export function isAllowedDestination(rawUrl) {
  return destinationProblem(rawUrl) === null
}

/**
 * Validate a `navigation` event's action before it is ever rendered.
 * Returns a normalized action, or null — in which case the UI shows no button
 * at all. A rejected action is never shown as a disabled or broken control:
 * there is nothing useful for the student to do with it.
 */
export function validateAction(action) {
  if (!action || typeof action !== 'object') return null
  const problem = destinationProblem(action.url)
  if (problem !== null) {
    // Non-sensitive local diagnostic only: no URL, no message content, nothing
    // sent anywhere. It exists so a reviewer can see the check ran.
    console.warn('[ritaj] navigation action rejected:', problem)
    return null
  }
  if (typeof action.label !== 'string' || !action.label.trim()) return null
  return {
    id: String(action.id ?? ''),
    label: action.label.trim().slice(0, 80),
    url: action.url,
    authRequired: Boolean(action.auth_required),
    // Confirmation defaults to required. A missing field must mean "ask",
    // never "go" — the safe reading of an absent value.
    requiresConfirmation: action.requires_confirmation !== false,
  }
}
