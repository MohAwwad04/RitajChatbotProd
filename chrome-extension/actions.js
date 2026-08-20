// Offline navigation: resolve a question to a reviewed action, with no network.
//
// This is a deliberate second implementation of src/ritaj/navigation.resolve()
// and the Arabic normalization it depends on. Duplicating logic is normally a
// defect; here it is the feature. The server's resolver is unreachable in
// exactly the situation the page-finder is most wanted — the Space asleep, a
// redeploy in flight, the corpus absent, the student on hotel wifi — so the
// panel carries its own.
//
// What it may NOT do is invent a destination. The resolver's entire output is
// an action drawn from BUNDLED_ACTIONS, which is generated from the reviewed
// registry, and every URL still passes navigation.destinationProblem() before
// anything opens a tab. So the offline path has the same ceiling as the online
// one: the most it can do is name something a human already approved.
//
// actions.test.mjs asserts this file and the Python resolver agree on a shared
// fixture set, which is what keeps "two implementations" from becoming "two
// behaviours".

import { BUNDLED_ACTIONS, REGISTRY_VERSION } from './actions.generated.js'
import { destinationProblem } from './navigation.js'

// --- Arabic normalization (mirrors src/ritaj/arabic.normalize_light) ---------
//
// Arabic writes the same word several ways: the definite article glued on,
// interchangeable letter forms, optional diacritics, the decorative tatweel,
// and Arabic-Indic digits. A student typing «افتح التقويم الأكاديمي» must match
// a reviewed phrase written «افتح التقويم الاكاديمي» — one hamza apart.
const DIACRITICS = /[ؐ-ًؚ-ٰٟۖ-ۭ]/g
const TATWEEL = /ـ/g

const LETTER_MAP = {
  'آ': 'ا', // آ alef madda       -> ا
  'أ': 'ا', // أ alef hamza-above -> ا
  'إ': 'ا', // إ alef hamza-below -> ا
  'ٱ': 'ا', // ٱ alef wasla       -> ا
  'ى': 'ي', // ى alef maqsura     -> ي
  'ی': 'ي', // ی farsi yeh        -> ي
  'ة': 'ه', // ة ta marbuta       -> ه
  'ؤ': 'و', // ؤ waw with hamza   -> و
  'ئ': 'ي', // ئ ya with hamza    -> ي
}

// Arabic-Indic (٠-٩) and extended/Persian (۰-۹) digits -> ASCII.
const DIGIT_OFFSETS = [
  [0x0660, 0x0669],
  [0x06f0, 0x06f9],
]

function normalizeLight(text) {
  let out = String(text ?? '')
    .replace(DIACRITICS, '')
    .replace(TATWEEL, '')
  let mapped = ''
  for (const ch of out) {
    const code = ch.codePointAt(0)
    let replaced = LETTER_MAP[ch]
    if (replaced === undefined) {
      replaced = ch
      for (const [lo, hi] of DIGIT_OFFSETS) {
        if (code >= lo && code <= hi) {
          replaced = String.fromCharCode(0x30 + (code - lo))
          break
        }
      }
    }
    mapped += replaced
  }
  return mapped
}

/**
 * Mirror of navigation._normalize: light Arabic normalization, lowercased,
 * punctuation collapsed to spaces. The Python side strips everything that is
 * not a word character, whitespace, or in the Arabic block; \p{L}\p{N} plus the
 * Arabic ranges is the same set expressed the way JavaScript spells it.
 */
export function normalizeQuestion(text) {
  const light = normalizeLight(text).toLowerCase()
  return (
    light
      // Arabic punctuation first, for the same reason the Python side does it
      // first: the class below preserves U+0600-U+06FF so Arabic letters
      // survive, and the comma, semicolon and question mark live in that block.
      .replace(/[،؍؛؞؟٪٫٬٭۔]+/g, ' ')
      .replace(/[^\p{L}\p{N}\s_؀-ۿ]+/gu, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  )
}

/**
 * Mirror of navigation._intent_match.
 *
 * Phrase containment, not similarity. The registry's intents are strings a
 * human reviewed, so a match is auditable — a reviewer can point at the phrase
 * that fired. A fuzzy matcher would quietly put destination choice back under
 * something nobody approved.
 */
export function intentMatch(question, action) {
  const normalized = normalizeQuestion(question)
  if (!normalized) return 0
  let best = 0
  const phrases = [...(action.intents_ar ?? []), ...(action.intents_en ?? [])]
  for (const phrase of phrases) {
    const candidate = normalizeQuestion(phrase)
    if (!candidate) continue
    if (normalized === candidate) return 1
    if (normalized.includes(candidate)) {
      // Longer phrases are more specific, so they earn more confidence.
      best = Math.max(best, Math.min(0.95, 0.7 + 0.05 * candidate.split(' ').length))
    }
  }
  return best
}

/**
 * Resolve a question to one reviewed action, or null.
 *
 * null is the common and correct outcome. Mirrors the server's ordering and,
 * critically, its ambiguity rule: when two actions match about equally well,
 * offering either is a coin flip on something that changes browser state, so
 * the panel offers neither.
 *
 * The retrieval-derived branch of the server resolver has no offline analogue —
 * it needs passages, which need a corpus and an embedder. Its absence is why
 * the online route is preferred whenever it answers.
 */
export function resolveLocally(question, actions = BUNDLED_ACTIONS) {
  if (!Array.isArray(actions) || actions.length === 0) return null

  const scored = actions
    .map((action) => ({ action, score: intentMatch(question, action) }))
    .sort((a, b) => b.score - a.score)

  const top = scored[0]
  if (!top) return null
  const floor = typeof top.action.min_confidence === 'number' ? top.action.min_confidence : 0.75
  if (top.score < floor) return null
  if (scored.length > 1 && Math.abs(scored[1].score - top.score) < 0.05) return null

  return { ...top.action, confidence: Math.round(top.score * 100) / 100, matched: 'intent' }
}

/**
 * The destinations this client will offer, newest trustworthy copy first.
 *
 * `fetched` is whatever /v2/navigation/actions returned, or null when the
 * backend could not be reached. A fetched list wins because it is how a bad
 * destination gets withdrawn without a Chrome Web Store review — but only after
 * every entry survives local validation, because "the server said so" is not a
 * security property when the server is the thing that might be wrong.
 */
export function usableActions(fetched) {
  const source = Array.isArray(fetched?.actions) && fetched.actions.length > 0
    ? fetched.actions
    : BUNDLED_ACTIONS
  return source.filter((action) => {
    const problem = destinationProblem(action?.url)
    if (problem !== null) {
      console.warn('[ritaj] bundled/fetched action rejected:', problem)
      return false
    }
    return typeof action.id === 'string' && action.id.length > 0
  })
}

export { BUNDLED_ACTIONS, REGISTRY_VERSION }
