// Transport failure classification — run with `node --test`.
//
// The point of these is the ORDER and the honesty. Getting the classification
// wrong is not a crash; it is the panel confidently telling a student to check
// a connection that demonstrably works, which is worse than admitting the cause
// is unknown.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { describeTransportFailure, statusCode } from './transport.js'

// Node defines a real, getter-only `navigator`, so it has to be shadowed with
// defineProperty rather than assigned.
const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
function withOnline(online, fn) {
  Object.defineProperty(globalThis, 'navigator', {
    value: { onLine: online }, configurable: true, writable: true,
  })
  try {
    return fn()
  } finally {
    if (original) Object.defineProperty(globalThis, 'navigator', original)
    else delete globalThis.navigator
  }
}

test('offline wins over everything else', () => {
  // A fetch really does reject with TypeError while offline. Reporting that as
  // "the server is unreachable" would send the student to the wrong place.
  const err = new TypeError('Failed to fetch')
  assert.equal(withOnline(false, () => describeTransportFailure(err)).code, 'OFFLINE')
})

test('a timeout is named as a timeout', () => {
  const err = Object.assign(new Error('timed out'), { name: 'TimeoutError' })
  assert.equal(withOnline(true, () => describeTransportFailure(err)).code, 'TIMEOUT')
})

test('a cancellation is reported as such, not as a failure', () => {
  const err = Object.assign(new Error('aborted'), { name: 'AbortError' })
  assert.equal(withOnline(true, () => describeTransportFailure(err)).code, 'ABORTED')
})

test('an opaque fetch rejection keeps the engine wording as detail', () => {
  const out = withOnline(true, () => describeTransportFailure(new TypeError('Failed to fetch')))
  assert.equal(out.code, 'UNREACHABLE')
  // Chrome's wording. Kept because it is the only string a bug report can be
  // correlated against, and it differs per engine.
  assert.equal(out.detail, 'Failed to fetch')
})

test('every engine wording for the same failure classifies identically', () => {
  for (const message of [
    'Failed to fetch',                                    // Chrome / Edge
    'NetworkError when attempting to fetch resource.',    // Firefox
    'Load failed',                                        // Safari
  ]) {
    const out = withOnline(true, () => describeTransportFailure(new TypeError(message)))
    assert.equal(out.code, 'UNREACHABLE', message)
  }
})

test('an unrecognised error is UNKNOWN, never silently UNREACHABLE', () => {
  // Guessing here is how a client ends up asserting a cause it cannot observe.
  const out = withOnline(true, () => describeTransportFailure(new RangeError('nope')))
  assert.equal(out.code, 'UNKNOWN')
  assert.equal(out.detail, 'nope')
})

test('a missing navigator does not throw', () => {
  // Service worker and test contexts may have no navigator at all.
  const saved = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  delete globalThis.navigator
  try {
    assert.equal(describeTransportFailure(new TypeError('x')).code, 'UNREACHABLE')
  } finally {
    if (saved) Object.defineProperty(globalThis, 'navigator', saved)
  }
})

test('status codes map to the states a hosted Space actually reaches', () => {
  // A sleeping, building or redeploying Space is served HTML by the platform
  // proxy — the app never runs, so the status is the only signal left.
  assert.equal(statusCode(503), 'STARTING_OR_ASLEEP')
  assert.equal(statusCode(502), 'GATEWAY')
  assert.equal(statusCode(504), 'GATEWAY')
  assert.equal(statusCode(429), 'RATE_LIMITED')
  assert.equal(statusCode(413), 'REQUEST_TOO_LARGE')
  assert.equal(statusCode(418), 'HTTP_ERROR')
})
