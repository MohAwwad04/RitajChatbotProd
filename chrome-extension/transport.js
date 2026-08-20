// Why a request never produced a response.
//
// Separate from sidepanel.js so it can be tested without a DOM, the same reason
// navigation.js and links.js are separate. The panel's other failure path — a
// response that arrived carrying a refusal — is the server's business and comes
// back as a stable code; this file covers the case where nothing arrived at all
// and no server ever got to say why.
//
// The honest limit, stated once here so the messages can be honest too: `fetch`
// rejects with an opaque `TypeError` for DNS failure, a refused connection, a
// TLS problem, a blocked request and a CORS rejection alike. The Fetch standard
// withholds which, deliberately — telling them apart would let any page probe
// the user's network. So this classifies what is genuinely knowable and reports
// the rest as one honest "unreachable", rather than asserting a cause it cannot
// observe. A wrong diagnosis is worse than an admitted unknown: it sends the
// student to check a router that is demonstrably working.

/** Classify a thrown fetch/stream failure into a stable code. */
export function describeTransportFailure(err) {
  // Checked first: a real fetch failure while offline is still, first and
  // foremost, offline — and that is the one cause the student can act on.
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return { code: 'OFFLINE' }
  }
  if (err?.name === 'TimeoutError') return { code: 'TIMEOUT' }
  // Not a failure: the student pressed stop. Callers skip reporting this.
  if (err?.name === 'AbortError') return { code: 'ABORTED' }
  if (err?.name === 'TypeError') {
    // Keep the engine's own wording as detail — it differs per browser and is
    // the only string a bug report can be correlated against.
    return { code: 'UNREACHABLE', detail: err?.message }
  }
  return { code: 'UNKNOWN', detail: err?.message }
}

/**
 * A code derived from the HTTP status, for a response whose body was not the
 * backend's JSON.
 *
 * A Hugging Face Space that is asleep, building, or mid-redeploy is served an
 * HTML page by the platform's proxy — the application never runs, so it never
 * produces its own `{code, message}`. The status is then the only signal left,
 * and it is a far better one than printing "HTTP 503" at a student.
 */
export function statusCode(status) {
  if (status === 503) return 'STARTING_OR_ASLEEP'
  if (status === 502 || status === 504) return 'GATEWAY'
  if (status === 429) return 'RATE_LIMITED'
  if (status === 413) return 'REQUEST_TOO_LARGE'
  return 'HTTP_ERROR'
}
