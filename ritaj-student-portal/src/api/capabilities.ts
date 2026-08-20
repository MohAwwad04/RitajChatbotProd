// What the backend can actually do right now — GET /capabilities.
//
// The home view renders this instead of a hard-coded list. That is the whole
// point: the previous dashboard described a student record (courses, GPA, a
// balance) that this product has never had access to, and nothing in the build
// could notice, because the claims lived only in JSX. Everything below is
// derived server-side from data/sources.yaml and data/navigation.yaml, so a
// topic disappears from the portal the moment its approval is withdrawn.
//
// Shapes come from src/ritaj/api.py::capabilities.

export type Topic = {
  id: string
  title: string
  language: 'ar' | 'en'
  url: string
  refresh: string
  // Past its refresh window — the answer layer says so too, and the portal
  // should not quietly present it as current.
  stale: boolean
}

export type NavigationDestination = {
  id: string
  label_ar: string
  label_en: string
  url: string
  auth_required: boolean
}

export type Capabilities = {
  corpus: {
    // False when the operator deliberately published material that did not pass
    // the Ritaj-only source policy. Comes from the corpus manifest, so it can
    // neither be forgotten on publish nor left behind when a verified corpus
    // replaces it. Optional: an older backend predates the field, and the safe
    // reading of absent is "verified".
    verified?: boolean
    provenance_note?: string
    version: string | null
    built_at: string | null
    documents: number | null
    chunks: number | null
    sources_sha256: string | null
  }
  ready: boolean
  topics: Topic[]
  // How many candidate pages are still in the review queue. Counted, never
  // named: an unapproved record is a question, not a capability.
  pending_topics: number
  navigation: NavigationDestination[]
  pending_navigation: number
  limits: {
    personal_records: boolean
    sign_in_on_your_behalf: boolean
    public_ritaj_pages: boolean
    navigation_needs_confirmation: boolean
  }
}

// Unreachable backend is a real state, not an error to swallow: the portal
// renders "can't reach the service" rather than an empty capability list, which
// would read as "this assistant knows nothing".
export async function fetchCapabilities(signal?: AbortSignal): Promise<Capabilities> {
  const response = await fetch('/capabilities', { signal })
  if (!response.ok) throw new Error(`capabilities: HTTP ${response.status}`)
  return (await response.json()) as Capabilities
}
