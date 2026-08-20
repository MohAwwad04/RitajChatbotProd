// Independent SOURCE-LINK validation — a second, deliberately different policy.
//
// navigation.js answers "may the extension steer the browser here?" and its
// answer is exactly one host and five reviewed paths. This file answers a
// different question: "may the panel render this citation as a clickable link?"
//
// The two must not share an allowlist, because they do not share a threat.
// A navigation action is a URL the product *chose* and a student clicks once;
// a source link is a URL that arrives inside a response body, one per cited
// document, from a server that might be compromised, impersonated, or simply
// buggy. Until this file existed, renderLinks() assigned `a.href = url`
// straight from that body with no check at all — a backend that returned
// `javascript:` or a lookalike host got exactly what it asked for.
//
// The path allowlist that protects navigation cannot work here: the curated map
// in data/links.yaml points at 39 different pages across the public site and
// there is no finite path set to enumerate. So the policy is host-exact plus a
// shape check, which is the strongest rule that still admits a real citation.
//
// Dependency-free and synchronous, like navigation.js, so a Chrome Web Store
// reviewer can read the whole rule in one sitting.

// Exact hosts only — compared with ===, never by suffix. Suffix matching is how
// `birzeit.edu.attacker.test` gets in, and it is the single most common way an
// allowlist like this fails.
//
// Each entry is here because data/links.yaml actually cites it:
//   ritaj.birzeit.edu  the portal itself (13 links)
//   www.birzeit.edu    the public university site (25 links)
//   koha.birzeit.edu   the library catalogue (1 link)
// `birzeit.edu` (bare) is included because the public site is reachable without
// the www label and a citation may legitimately carry either form.
//
// Kept in sync with data/links.yaml by scripts/check_extension.py, which fails
// the build if the map ever cites a host that is not listed here.
const OFFICIAL_HOSTS = new Set([
  'ritaj.birzeit.edu',
  'www.birzeit.edu',
  'birzeit.edu',
  'koha.birzeit.edu',
])

const ALLOWED_PROTOCOL = 'https:'
const MAX_URL_LENGTH = 500

/**
 * Why `rawUrl` may not be rendered as a source link, or null if it may be.
 *
 * Returns the reason rather than a boolean so a rejection can be logged locally
 * without re-deriving which rule fired — the same contract as
 * navigation.destinationProblem, so the two read alike at the call site.
 */
export function sourceLinkProblem(rawUrl) {
  if (typeof rawUrl !== 'string' || rawUrl.length === 0) return 'empty'
  if (rawUrl.length > MAX_URL_LENGTH) return 'too long'
  // Whitespace and backslashes let a URL be re-parsed differently by whatever
  // reads it next (the browser, a logger, a copy-paste into a terminal).
  // Reject rather than normalise: normalising picks one of the readings and
  // the attacker was relying on the other.
  if (/[\s\\]/.test(rawUrl)) return 'contains whitespace or a backslash'
  // C0/C1 control characters, plus the bidirectional overrides that make a URL
  // *render* as one string while it *resolves* to another. Written as \u
  // escapes, not literal bytes, so the rule survives a copy-paste or an editor
  // that strips unprintables.
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/.test(rawUrl)) {
    return 'contains control or bidirectional-override characters'
  }
  // "//host/path" inherits the current scheme — a classic host-smuggling shape.
  if (rawUrl.startsWith('//')) return 'scheme-relative'
  // Traversal has to be judged on the RAW string. `new URL()` resolves `..`
  // segments during parsing, so `/en/../../etc/passwd` arrives at `.pathname`
  // already flattened to `/etc/passwd` and a check on the parsed path can never
  // fire. (navigation.js had exactly that dead check; its path allowlist was
  // catching the case by accident.) `%2e` is the encoded dot that smuggles the
  // same segment past a naive literal match.
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
  // hostname (not host) excludes the port. Lowercased then compared exactly, so
  // sibling subdomains, suffix tricks and punycode homoglyphs all fail: the URL
  // parser has already converted a Unicode homoglyph to its xn-- form by here,
  // and that form is not in the set.
  if (!OFFICIAL_HOSTS.has(url.hostname.toLowerCase())) return `host ${url.hostname}`
  if (url.port && url.port !== '443') return `port ${url.port}`
  if (url.username || url.password) return 'embedded credentials'
  // Every URL in data/links.yaml is a bare page address: 39 of them, none with
  // a query and none with a fragment. Anything carrying one is not a citation
  // this product produced, so there is no reason to follow it.
  if (url.search) return 'query string'
  if (url.hash) return 'fragment'

  return null
}

export function isOfficialSourceLink(rawUrl) {
  return sourceLinkProblem(rawUrl) === null
}

/**
 * Normalize one {label, url} citation, or null if it must not be rendered.
 *
 * A rejected link is dropped entirely rather than shown inert. A greyed-out
 * "source" tells a student the answer had a citation the panel would not open,
 * which is both alarming and useless; showing nothing is honest, because from
 * the student's point of view that citation did not survive review.
 */
export function validateLink(entry) {
  if (!entry || typeof entry !== 'object') return null
  const problem = sourceLinkProblem(entry.url)
  if (problem !== null) {
    // Local diagnostic only: no URL body, no message content, nothing leaves
    // the machine. It exists so a reviewer can confirm the check ran.
    console.warn('[ritaj] source link rejected:', problem)
    return null
  }
  const label = typeof entry.label === 'string' ? entry.label.trim() : ''
  if (!label) return null
  return { label: label.slice(0, 120), url: entry.url }
}

/** Validate a list of citations, dropping every entry that fails. */
export function validateLinks(entries) {
  if (!Array.isArray(entries)) return []
  const out = []
  const seen = new Set()
  for (const entry of entries) {
    const link = validateLink(entry)
    if (!link || seen.has(link.url)) continue
    seen.add(link.url)
    out.push(link)
  }
  return out
}
