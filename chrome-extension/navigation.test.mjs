// Client-side destination validation — run with `node --test chrome-extension/`.
//
// This mirrors tests/test_navigation.py deliberately. The two validators are
// separate implementations of one policy, and the whole point of the client
// check is that it does not depend on the server's, so it needs its own tests.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { destinationProblem, isAllowedDestination, validateAction } from './navigation.js'

const HOSTILE = [
  ['https://www.birzeit.edu/en/admissions', 'off-domain'],
  ['https://koha.birzeit.edu/', 'off-domain sibling'],
  ['https://ritaj.birzeit.edu.attacker.test/reg/', 'suffix trick'],
  ['https://evil-ritaj.birzeit.edu/reg/', 'sibling subdomain'],
  ['https://attacker.test/ritaj.birzeit.edu/reg/', 'host in path'],
  ['http://ritaj.birzeit.edu/reg/', 'not https'],
  ['//ritaj.birzeit.edu/reg/', 'scheme-relative'],
  ['javascript:alert(document.cookie)', 'script scheme'],
  ['data:text/html,<script>alert(1)</script>', 'data scheme'],
  ['https://user:pass@ritaj.birzeit.edu/reg/', 'embedded credentials'],
  ['https://ritaj.birzeit.edu@attacker.test/', 'userinfo confusion'],
  ['https://ritaj.birzeit.edu:8443/reg/', 'non-standard port'],
  ['https://ritaj.birzeit.edu/reg/../../etc/passwd', 'path traversal'],
  ['https://xn--ritj-hpa.birzeit.edu/reg/', 'punycode homoglyph'],
  ['https://ritaj.birzeit.edu/reg/#javascript:alert(1)', 'fragment'],
  ['https://ritaj.birzeit.edu\\@attacker.test/', 'backslash'],
  ['https://ritaj.birzeit.edu/reg/ ?x=1', 'whitespace'],
  ['https://ritaj.birzeit.edu/unregistered/path', 'unregistered path'],
  ['', 'empty'],
  [null, 'null'],
  [undefined, 'undefined'],
  [{ url: 'https://ritaj.birzeit.edu/reg/' }, 'not a string'],
]

test('every hostile destination is rejected', () => {
  for (const [url, why] of HOSTILE) {
    assert.notEqual(destinationProblem(url), null, `should reject ${why}: ${url}`)
    assert.equal(isAllowedDestination(url), false, why)
  }
})

test('registered destinations are accepted', () => {
  for (const url of [
    'https://ritaj.birzeit.edu/',
    'https://ritaj.birzeit.edu/reg',
    'https://ritaj.birzeit.edu/reg/',
    'https://ritaj.birzeit.edu/academic-calendar',
    'https://ritaj.birzeit.edu/hemis/courses',
    'https://ritaj.birzeit.edu/bzu-msgs/boards',
  ]) {
    assert.equal(destinationProblem(url), null, `should accept ${url}`)
  }
})

test('host comparison is case-insensitive but exact', () => {
  assert.equal(destinationProblem('https://RITAJ.birzeit.edu/reg/'), null)
  assert.notEqual(destinationProblem('https://ritaj.birzeit.edu.evil.test/reg/'), null)
})

test('only declared query parameters are permitted', () => {
  assert.equal(destinationProblem('https://ritaj.birzeit.edu/hemis/courses?term=fall2026'), null)
  assert.notEqual(
    destinationProblem('https://ritaj.birzeit.edu/hemis/courses?redirect=https://attacker.test'),
    null,
  )
  // A path with no declared safe keys accepts none at all.
  assert.notEqual(destinationProblem('https://ritaj.birzeit.edu/reg/?next=/x'), null)
})

test('an over-long URL is rejected before parsing', () => {
  const long = `https://ritaj.birzeit.edu/reg/?${'a'.repeat(600)}`
  assert.notEqual(destinationProblem(long), null)
})

test('validateAction rejects an action with a bad destination', () => {
  assert.equal(validateAction({ url: 'https://attacker.test/', label: 'Open' }), null)
  assert.equal(validateAction({ url: 'https://ritaj.birzeit.edu/reg/', label: '   ' }), null)
  assert.equal(validateAction(null), null)
  assert.equal(validateAction('https://ritaj.birzeit.edu/reg/'), null)
})

test('validateAction normalizes a good action', () => {
  const action = validateAction({
    id: 'course-registration',
    label: 'Open course registration',
    url: 'https://ritaj.birzeit.edu/reg/',
    auth_required: true,
    requires_confirmation: true,
  })
  assert.equal(action.id, 'course-registration')
  assert.equal(action.url, 'https://ritaj.birzeit.edu/reg/')
  assert.equal(action.authRequired, true)
  assert.equal(action.requiresConfirmation, true)
})

test('a missing requires_confirmation means ask, never go', () => {
  const action = validateAction({
    id: 'x',
    label: 'Open',
    url: 'https://ritaj.birzeit.edu/reg/',
  })
  assert.equal(action.requiresConfirmation, true)
})

test('an over-long label is truncated rather than rendered whole', () => {
  const action = validateAction({
    id: 'x',
    label: 'L'.repeat(500),
    url: 'https://ritaj.birzeit.edu/reg/',
  })
  assert.equal(action.label.length, 80)
})
