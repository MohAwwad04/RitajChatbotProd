// Source-link validation — run with `node --test chrome-extension/`.
//
// Deliberately a separate suite from navigation.test.mjs, because the two
// policies differ and a shared fixture list would hide that. The clearest
// evidence they are genuinely independent is the pair of cases at the bottom:
// a URL that navigation accepts and links reject, and one that links accept
// and navigation rejects. If a future refactor ever merges the allowlists,
// those two tests fail first.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { isOfficialSourceLink, sourceLinkProblem, validateLink, validateLinks } from './links.js'
import { destinationProblem } from './navigation.js'

const HOSTILE = [
  ['javascript:alert(document.cookie)', 'script scheme'],
  ['javascript:void(0)', 'script scheme, benign-looking'],
  ['data:text/html,<script>alert(1)</script>', 'data scheme'],
  ['vbscript:msgbox(1)', 'vbscript scheme'],
  ['file:///etc/passwd', 'file scheme'],
  ['blob:https://www.birzeit.edu/1234', 'blob scheme'],
  ['http://www.birzeit.edu/en/admissions', 'not https'],
  ['//www.birzeit.edu/en/admissions', 'scheme-relative'],
  ['https://attacker.test/en/admissions', 'off-domain'],
  ['https://birzeit.edu.attacker.test/', 'suffix trick'],
  ['https://www.birzeit.edu.attacker.test/', 'suffix trick with www'],
  ['https://attacker.test/www.birzeit.edu/en', 'host in path'],
  ['https://evil-ritaj.birzeit.edu/reg/', 'sibling subdomain'],
  ['https://notbirzeit.edu/', 'lookalike registrable domain'],
  ['https://user:pass@www.birzeit.edu/en', 'embedded credentials'],
  ['https://www.birzeit.edu@attacker.test/', 'userinfo confusion'],
  ['https://www.birzeit.edu:8443/en', 'non-standard port'],
  ['https://www.birzeit.edu/en/../../etc/passwd', 'path traversal'],
  ['https://xn--brzeit-5wa.edu/', 'punycode homoglyph'],
  ['https://www.birzeit.edu/en?next=https://attacker.test', 'query string'],
  ['https://www.birzeit.edu/en#javascript:alert(1)', 'fragment'],
  ['https://www.birzeit.edu\\@attacker.test/', 'backslash'],
  ['https://www.birzeit.edu/en ?x=1', 'whitespace'],
  ['https://www.birzeit.edu/\u202een.html', 'bidi override'],
  ['https://www.birzeit.edu/\u0000en', 'NUL byte'],
  ['', 'empty'],
  [null, 'null'],
  [undefined, 'undefined'],
  [42, 'number'],
  [{ url: 'https://www.birzeit.edu/en' }, 'not a string'],
]

test('every hostile source link is rejected', () => {
  for (const [url, why] of HOSTILE) {
    assert.notEqual(sourceLinkProblem(url), null, `should reject ${why}: ${url}`)
    assert.equal(isOfficialSourceLink(url), false, why)
  }
})

test('real citations from data/links.yaml are accepted', () => {
  // Sampled from the three hosts the curated map actually cites.
  for (const url of [
    'https://ritaj.birzeit.edu/academic-calendar',
    'https://ritaj.birzeit.edu/',
    'https://www.birzeit.edu/en/admissions',
    'https://www.birzeit.edu/en/admissions/new-students-admission/admission-process',
    'https://birzeit.edu/en/admissions',
    'https://koha.birzeit.edu/',
  ]) {
    assert.equal(sourceLinkProblem(url), null, `should accept ${url}`)
  }
})

test('host comparison is case-insensitive but exact', () => {
  assert.equal(sourceLinkProblem('https://WWW.Birzeit.EDU/en'), null)
  assert.notEqual(sourceLinkProblem('https://www.birzeit.edu.evil.test/en'), null)
})

test('traversal is judged on the raw string, before the parser flattens it', () => {
  // There is no path allowlist here to catch traversal as a side effect, so
  // this check is load-bearing. `/en/../../etc/passwd` reaches `.pathname` as
  // `/etc/passwd`; only the raw string still shows what was written.
  assert.equal(sourceLinkProblem('https://www.birzeit.edu/en/../../etc/passwd'), 'path traversal')
  assert.equal(sourceLinkProblem('https://www.birzeit.edu/a/../en'), 'path traversal')
  assert.equal(sourceLinkProblem('https://www.birzeit.edu/./en'), 'path traversal')
  assert.equal(sourceLinkProblem('https://www.birzeit.edu/%2e%2e/en'), 'encoded dot in path')
  assert.equal(sourceLinkProblem('https://www.birzeit.edu/en'), null)
})

test('an over-long URL is rejected before parsing', () => {
  assert.equal(sourceLinkProblem(`https://www.birzeit.edu/${'a'.repeat(600)}`), 'too long')
})

test('validateLink drops an entry with no usable label', () => {
  assert.equal(validateLink({ url: 'https://www.birzeit.edu/en', label: '   ' }), null)
  assert.equal(validateLink({ url: 'https://www.birzeit.edu/en' }), null)
  assert.equal(validateLink(null), null)
  assert.equal(validateLink('https://www.birzeit.edu/en'), null)
})

test('validateLink truncates an over-long label rather than rendering it whole', () => {
  const link = validateLink({ url: 'https://www.birzeit.edu/en', label: 'L'.repeat(400) })
  assert.equal(link.label.length, 120)
})

test('validateLinks drops bad entries, keeps good ones, and dedupes', () => {
  const out = validateLinks([
    { label: 'Admissions', url: 'https://www.birzeit.edu/en/admissions' },
    { label: 'Phishing', url: 'https://attacker.test/en/admissions' },
    { label: 'Admissions again', url: 'https://www.birzeit.edu/en/admissions' },
    { label: 'Calendar', url: 'https://ritaj.birzeit.edu/academic-calendar' },
    'not an object',
  ])
  assert.deepEqual(out, [
    { label: 'Admissions', url: 'https://www.birzeit.edu/en/admissions' },
    { label: 'Calendar', url: 'https://ritaj.birzeit.edu/academic-calendar' },
  ])
})

test('validateLinks tolerates a non-array', () => {
  assert.deepEqual(validateLinks(null), [])
  assert.deepEqual(validateLinks({ label: 'x', url: 'https://www.birzeit.edu/en' }), [])
})

// --- The two policies are independent, and these prove it -------------------

test('a link the citation policy accepts is NOT a navigation destination', () => {
  // The public admissions page is a legitimate citation. It is not somewhere
  // the extension may steer the browser: navigation is ritaj.birzeit.edu only.
  const url = 'https://www.birzeit.edu/en/admissions'
  assert.equal(sourceLinkProblem(url), null)
  assert.notEqual(destinationProblem(url), null)
})

test('a destination the navigation policy accepts is NOT necessarily a link', () => {
  // The course browser carries ?term=, which navigation explicitly permits and
  // the citation policy explicitly does not — no entry in links.yaml has a
  // query, so one arriving in a response body is not something we produced.
  const url = 'https://ritaj.birzeit.edu/hemis/courses?term=fall2026'
  assert.equal(destinationProblem(url), null)
  assert.notEqual(sourceLinkProblem(url), null)
})
