// Ritaj Assistant side panel — a thin client over the hosted RAG backend.
//
// The server is stateless: this panel owns the conversation, persists it in
// chrome.storage.local (bounded — see TURN_CAP/BYTE_CAP), and replays the prior
// turns with every message so follow-ups resolve.
//
// Three things this file will not do, by design:
//   * open a URL the backend sent without re-validating it (navigation.js)
//   * read the Ritaj page, its DOM, cookies, storage or form values
//   * send anything but the student's typed message and the prior turns

import { REGISTRY_VERSION, resolveLocally, usableActions } from './actions.js'
import { validateLinks } from './links.js'
import { validateAction } from './navigation.js'

/* global BASE_URL, MAX_MESSAGE_CHARS, chrome */

// --- i18n --------------------------------------------------------------------
const STRINGS = {
  en: {
    dir: 'ltr',
    title: 'Ritaj Assistant',
    subtitle: 'Independent · Birzeit University',
    placeholder: 'Ask about Ritaj…',
    welcome:
      'Hi! I’m an independent, student-built Ritaj assistant — not an official Birzeit service. ' +
      'Ask about registration, the academic calendar, or how to find something on Ritaj.',
    disclaimer:
      'Independent project — not an official Birzeit service. Confirm anything important on the linked Ritaj page.',
    error: 'Could not reach the assistant. Please check your connection and try again.',
    offline: 'You appear to be offline. The assistant needs a connection to answer.',
    tooLong: 'That message is too long. Please shorten it to {max} characters or fewer.',
    sources: 'Sources',
    stale: 'may be out of date',
    finderTitle: 'Find a Ritaj page',
    finderNote: 'Opens in a new tab',
    finderEmpty:
      'No Ritaj destinations have been approved yet. Each one has to be confirmed by a person before this assistant will open it.',
    finderSignIn: 'sign-in needed',
    chatOk: 'Chat ready',
    chatDegraded: 'Chat unavailable',
    chatOffline: 'Offline',
    chatDegradedNote:
      'Factual answers are unavailable right now. The page finder above still works.',
    openFailed: 'Could not open that tab. Try again.',
    requestId: 'Reference',
    stopped: 'Stopped.',
    cleared: 'History cleared.',
    confirmNav: 'Opens {host} in a tab. You may need to sign in.',
    thinking: 'Thinking…',
    answering: 'Answering.',
    answered: 'Answer complete.',
    codes: {
      INITIALIZING: 'The assistant is starting up. Try again in a moment.',
      NOT_READY: 'The assistant is temporarily unavailable. Try again shortly.',
      RATE_LIMITED: 'You’re sending messages too quickly. Wait a moment and try again.',
      LLM_BUDGET_EXHAUSTED:
        'The assistant has reached today’s usage limit. Try again tomorrow, or use the linked Ritaj page directly.',
      LLM_UNAVAILABLE: 'The answering service is unavailable right now. Try again shortly.',
      LLM_TIMEOUT: 'That took too long. Try again, or ask a shorter question.',
      BUSY: 'The assistant is busy right now. Try again shortly.',
      REQUEST_TOO_LARGE: 'That message is too long. Please shorten it.',
    },
    suggestions: [
      'How do I register for courses?',
      'When does the semester start?',
      'Where do I find my schedule on Ritaj?',
    ],
    // Offered only when the finder actually has a destination — a chip that
    // resolves to nothing teaches a student the assistant is broken.
    navSuggestions: ['Open course registration'],
  },
  ar: {
    dir: 'rtl',
    title: 'مساعد ريتاج',
    subtitle: 'مستقل · جامعة بيرزيت',
    placeholder: 'اسأل عن ريتاج…',
    welcome:
      'أهلاً! أنا مساعد ريتاج مستقل من إعداد طلبة — ولست خدمة رسمية من جامعة بيرزيت. ' +
      'اسألني عن التسجيل أو التقويم الأكاديمي أو كيفية الوصول إلى صفحة في ريتاج.',
    disclaimer:
      'مشروع مستقل — ليس خدمة رسمية من جامعة بيرزيت. تأكّد من أي معلومة مهمة على صفحة ريتاج المرتبطة.',
    error: 'تعذّر الوصول إلى المساعد. تحقّق من اتصالك وحاول مرة أخرى.',
    offline: 'يبدو أنك غير متصل بالإنترنت. يحتاج المساعد إلى اتصال للإجابة.',
    tooLong: 'الرسالة طويلة جداً. يرجى اختصارها إلى {max} حرف أو أقل.',
    sources: 'المصادر',
    stale: 'قد تكون غير محدّثة',
    finderTitle: 'ابحث عن صفحة في ريتاج',
    finderNote: 'تُفتح في تبويب جديد',
    finderEmpty:
      'لم تتم الموافقة على أي صفحة في ريتاج بعد. يجب أن يؤكّد شخص كل صفحة قبل أن يفتحها المساعد.',
    finderSignIn: 'يتطلب تسجيل الدخول',
    chatOk: 'الدردشة جاهزة',
    chatDegraded: 'الدردشة غير متاحة',
    chatOffline: 'غير متصل',
    chatDegradedNote:
      'الإجابات المبنية على المصادر غير متاحة حالياً. لا يزال البحث عن الصفحات أعلاه يعمل.',
    openFailed: 'تعذّر فتح التبويب. حاول مرة أخرى.',
    requestId: 'الرقم المرجعي',
    stopped: 'تم الإيقاف.',
    cleared: 'تم مسح المحادثات.',
    confirmNav: 'سيفتح {host} في تبويب جديد. قد تحتاج إلى تسجيل الدخول.',
    thinking: 'جارٍ التفكير…',
    answering: 'يتم الرد.',
    answered: 'اكتملت الإجابة.',
    codes: {
      INITIALIZING: 'المساعد قيد التشغيل. حاول بعد لحظات.',
      NOT_READY: 'المساعد غير متاح مؤقتاً. حاول بعد قليل.',
      RATE_LIMITED: 'ترسل رسائل بسرعة كبيرة. انتظر لحظة ثم حاول مجدداً.',
      LLM_BUDGET_EXHAUSTED: 'بلغ المساعد حد الاستخدام اليومي. حاول غداً أو افتح صفحة ريتاج مباشرة.',
      LLM_UNAVAILABLE: 'خدمة الإجابة غير متاحة حالياً. حاول بعد قليل.',
      LLM_TIMEOUT: 'استغرقت الإجابة وقتاً طويلاً. حاول مجدداً أو اطرح سؤالاً أقصر.',
      BUSY: 'المساعد مشغول حالياً. حاول بعد قليل.',
      REQUEST_TOO_LARGE: 'الرسالة طويلة جداً. يرجى اختصارها.',
    },
    suggestions: [
      'كيف أسجّل المساقات؟',
      'متى يبدأ الفصل الدراسي؟',
      'أين أجد جدولي في ريتاج؟',
    ],
    navSuggestions: ['افتح تسجيل المساقات'],
  },
}

// --- Storage bounds -----------------------------------------------------------
// chrome.storage.local is finite and shared with everything else the extension
// stores. An unbounded transcript grows until writes start failing silently,
// which loses the conversation exactly when it got long enough to matter.
const TURN_CAP = 40
const BYTE_CAP = 120_000

// --- Citation stripping (mirrors the portal's chat.ts) ------------------------
function stripCitations(text) {
  return text
    .replace(/\s*\[\d+\](?:\s*[،,]\s*\[\d+\])*/g, '')
    .replace(/\s*\[\d*$/g, '')
    .replace(/[ \t]+([.!?؟،,])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
}

// --- State --------------------------------------------------------------------
let lang = 'en'
let sessionId = null
let turns = [] // [{role, content, sources?, links?, navigation?}]
let busy = false
let controller = null // AbortController for the in-flight request

const $ = (id) => document.getElementById(id)
// The destinations currently on screen. Seeded from the bundled registry so the
// finder renders before any network call, then replaced by the server's copy if
// one arrives — see refreshCapabilities().
let knownActions = usableActions(null)
let registryVersion = REGISTRY_VERSION

const thread = () => $('thread')
const S = () => STRINGS[lang]

function newSessionId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function loadState() {
  const stored = await chrome.storage.local.get(['lang', 'session'])
  lang = stored.lang || ((navigator.language || '').startsWith('ar') ? 'ar' : 'en')
  const session = stored.session
  if (session && Array.isArray(session.turns)) {
    sessionId = session.sessionId || newSessionId()
    turns = session.turns
  } else {
    sessionId = newSessionId()
    turns = []
  }
}

function trimForStorage(list) {
  let kept = list.slice(-TURN_CAP)
  // Drop from the front until it fits. Oldest-first: the recent turns are what
  // the next follow-up depends on.
  while (kept.length > 2 && JSON.stringify(kept).length > BYTE_CAP) {
    kept = kept.slice(1)
  }
  return kept
}

function saveState() {
  turns = trimForStorage(turns)
  chrome.storage.local.set({ lang, session: { sessionId, turns } })
}

// --- Status banner ------------------------------------------------------------
function showRequestId(id) {
  if (!id) return
  const banner = $('status')
  if (banner.hidden) return
  const el = document.createElement('div')
  el.className = 'request-id'
  el.textContent = `${S().requestId}: ${id}`
  banner.appendChild(el)
}

function showStatus(message) {
  const box = $('status')
  if (!message) {
    box.hidden = true
    box.textContent = ''
    return
  }
  box.textContent = message
  box.hidden = false
}

function messageForCode(code, fallback) {
  return S().codes[code] || fallback || S().error
}

function announce(message) {
  $('sr-status').textContent = message
}

// --- Rendering ------------------------------------------------------------------
function applyLang() {
  const s = S()
  document.documentElement.dir = s.dir
  document.documentElement.lang = lang
  document.body.dir = s.dir
  $('title').textContent = s.title
  $('subtitle').textContent = s.subtitle
  $('input').placeholder = s.placeholder
  $('disclaimer-text').textContent = s.disclaimer
  $('lang-toggle').textContent = lang === 'ar' ? 'EN' : 'ع'
  renderFinder()
  // The pill keeps its state and changes language with everything else.
  if (!$('service-pill').hidden) {
    const el = $('service-pill')
    const state = el.classList.contains('pill--ok')
      ? 'ok'
      : el.classList.contains('pill--offline')
        ? 'offline'
        : 'degraded'
    setServicePill(state)
  }
  renderThread()
}

/** Sources as structured rows: page name, host, capture date, staleness. */
function renderSources(container, sources) {
  if (!sources?.length) return
  const box = document.createElement('div')
  box.className = 'sources'

  const label = document.createElement('div')
  label.className = 'sources__label'
  label.textContent = S().sources
  box.appendChild(label)

  for (const src of sources.slice(0, 4)) {
    const row = document.createElement('div')
    row.className = 'source'

    const title = document.createElement('span')
    title.className = 'source__title'
    title.textContent = src.title || src.source || '—'
    row.appendChild(title)

    if (src.url) {
      let host = ''
      try {
        host = new URL(src.url).hostname
      } catch {
        host = ''
      }
      if (host) {
        const el = document.createElement('span')
        el.className = 'source__host'
        el.textContent = ` · ${host}`
        row.appendChild(el)
      }
    }
    if (src.as_of) {
      const el = document.createElement('span')
      el.className = 'source__date'
      el.textContent = ` · ${src.as_of}`
      row.appendChild(el)
    }
    if (src.stale) {
      const el = document.createElement('span')
      el.className = 'source__stale'
      el.textContent = ` ${S().stale}`
      row.appendChild(el)
    }
    box.appendChild(row)
  }
  container.appendChild(box)
}

function renderLinks(container, links) {
  // Every citation is re-validated here against links.js, which knows the
  // official Birzeit hosts and nothing else. This used to assign `a.href`
  // straight from the response body: a compromised or impersonated backend
  // could put `javascript:` or a lookalike domain in front of a student who had
  // every reason to trust it, because the panel had just cited it as a source.
  //
  // The policy is deliberately NOT navigation.js's. That one answers "may we
  // steer the browser here", and its answer is five reviewed paths on one host;
  // a citation is a different object with a different threat.
  const safe = validateLinks(links)
  if (!safe.length) return
  const box = document.createElement('div')
  box.className = 'links'
  for (const { label, url } of safe) {
    const a = document.createElement('a')
    a.href = url
    a.textContent = label
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    box.appendChild(a)
  }
  container.appendChild(box)
}

/**
 * A navigation action, rendered only if it passes our own validation.
 * A rejected action shows nothing at all — there is nothing useful a student
 * could do with a disabled "open" button.
 */
function renderNavigation(container, rawAction) {
  const action = validateAction(rawAction)
  if (!action) return

  const box = document.createElement('div')
  box.className = 'nav-action'

  const button = document.createElement('button')
  button.type = 'button'
  button.textContent = action.label
  button.addEventListener('click', () => {
    // The service worker validates again before touching the tabs API.
    chrome.runtime.sendMessage({ type: 'ritaj:navigate', url: action.url })
  })
  box.appendChild(button)

  let host = ''
  try {
    host = new URL(action.url).hostname
  } catch {
    host = ''
  }
  const note = document.createElement('small')
  note.textContent = S().confirmNav.replace('{host}', host)
  box.appendChild(note)

  container.appendChild(box)
}

/* --- Page finder ------------------------------------------------------------
 *
 * The section that has to keep working when nothing else does. It renders from
 * `knownActions`, which starts as the bundled registry generated from
 * data/navigation.yaml and is replaced by /v2/navigation/actions when the
 * backend answers. Every URL passes navigation.destinationProblem() first, and
 * the service worker validates it a third time before it opens a tab.
 */
function renderFinder() {
  const s = S()
  const section = $('finder')
  const grid = $('finder-grid')
  $('finder-title').textContent = s.finderTitle
  grid.innerHTML = ''

  if (!knownActions.length) {
    // Honest empty state rather than a hidden section. "Nobody has approved a
    // destination yet" and "this feature does not exist" are different facts,
    // and hiding the section would tell the student the second one.
    $('finder-note').textContent = ''
    const note = document.createElement('p')
    note.className = 'finder__empty'
    note.textContent = s.finderEmpty
    grid.appendChild(note)
    section.hidden = false
    return
  }

  $('finder-note').textContent = s.finderNote
  // Destinations arriving from the network can unlock the navigation
  // suggestion chips, which are rendered from the same knownActions list. Only
  // while the welcome screen is showing — never mid-conversation.
  if (!turns.length) renderSuggestions()
  for (const action of knownActions) {
    const label = lang === 'ar' ? action.label_ar : action.label_en
    if (!label) continue

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'finder__item'

    const name = document.createElement('span')
    name.textContent = label
    button.appendChild(name)

    if (action.auth_required) {
      const lock = document.createElement('span')
      lock.className = 'finder__lock'
      lock.textContent = `· ${s.finderSignIn}`
      button.appendChild(lock)
    }

    // The host is shown before the click, not after. A student should be able
    // to see where a button goes without trusting the label above it.
    const host = document.createElement('span')
    host.className = 'finder__host'
    try {
      host.textContent = new URL(action.url).hostname
    } catch {
      host.textContent = ''
    }
    button.appendChild(host)

    button.addEventListener('click', () => openDestination(action.url))
    grid.appendChild(button)
  }
  section.hidden = false
}

/** Ask the service worker to open a validated destination. */
function openDestination(url) {
  chrome.runtime.sendMessage({ type: 'ritaj:navigate', url }, (response) => {
    // Reading lastError is what suppresses Chrome's "Unchecked runtime.lastError"
    // noise, and it is also the only way a failed open becomes visible here.
    if (chrome.runtime.lastError || !response?.ok) {
      showStatus(S().openFailed)
    }
  })
}

/* --- Service status ---------------------------------------------------------
 *
 * Reports whether CHAT can answer. The finder is deliberately excluded: it
 * works offline, so folding it into one "service status" would either
 * understate the outage or overstate the capability.
 */
function setServicePill(state) {
  const pill = $('service-pill')
  const text = $('service-pill-text')
  const s = S()
  pill.classList.remove('pill--ok', 'pill--degraded', 'pill--offline')
  if (state === 'ok') {
    pill.classList.add('pill--ok')
    text.textContent = s.chatOk
  } else if (state === 'offline') {
    pill.classList.add('pill--offline')
    text.textContent = s.chatOffline
  } else {
    pill.classList.add('pill--degraded')
    text.textContent = s.chatDegraded
  }
  pill.hidden = false
}

/**
 * Refresh destinations and chat readiness from the backend, best-effort.
 *
 * Every failure path here is non-fatal on purpose. The panel has already
 * rendered from the bundled registry by the time this runs, so an unreachable
 * backend leaves a working page finder and a truthful "chat unavailable" pill
 * rather than an empty panel and a spinner.
 */
async function refreshCapabilities() {
  if (!navigator.onLine) {
    setServicePill('offline')
    return
  }
  try {
    const [actionsRes, capsRes] = await Promise.allSettled([
      fetch(`${BASE_URL}/v2/navigation/actions`, { signal: AbortSignal.timeout(8000) }),
      fetch(`${BASE_URL}/capabilities`, { signal: AbortSignal.timeout(8000) }),
    ])

    if (actionsRes.status === 'fulfilled' && actionsRes.value.ok) {
      const fetched = await actionsRes.value.json()
      const next = usableActions(fetched)
      // Only re-render when the answer actually differs from what is on screen,
      // so a refresh does not steal focus from a button mid-click.
      if (fetched.version !== registryVersion || next.length !== knownActions.length) {
        knownActions = next
        registryVersion = fetched.version ?? registryVersion
        renderFinder()
      }
    }

    if (capsRes.status === 'fulfilled' && capsRes.value.ok) {
      const caps = await capsRes.value.json()
      // `modes` is the newer, per-feature block; `ready` is the older single
      // flag. Prefer the first, fall back to the second, so this panel works
      // against a backend that has not been redeployed yet.
      const ready = caps.modes ? caps.modes.ready : caps.ready
      setServicePill(ready ? 'ok' : 'degraded')
      if (!ready) showStatus(S().chatDegradedNote)
    } else {
      setServicePill('degraded')
    }
  } catch {
    // Network refused, DNS failed, the Space is asleep — all the same to the
    // student, and none of them should empty the panel.
    setServicePill('degraded')
  }
}

function addBubble(role, content, turn) {
  const div = document.createElement('div')
  div.className = `msg msg--${role}`
  const text = document.createElement('div')
  text.textContent = content
  div.appendChild(text)
  if (turn) {
    renderSources(div, turn.sources)
    renderLinks(div, turn.links)
    renderNavigation(div, turn.navigation)
  }
  thread().appendChild(div)
  thread().scrollTop = thread().scrollHeight
  return { bubble: div, text }
}

function renderThread() {
  const s = S()
  thread().innerHTML = ''
  if (!turns.length) {
    const w = document.createElement('div')
    w.className = 'welcome'
    w.textContent = s.welcome
    thread().appendChild(w)
    renderSuggestions()
    return
  }
  $('suggestions').innerHTML = ''
  for (const t of turns) addBubble(t.role, t.content, t)
}

function renderSuggestions() {
  const box = $('suggestions')
  box.innerHTML = ''
  const s = S()
  // A navigation prompt is only a real suggestion if a reviewed destination
  // exists to answer it. With none approved, "Open course registration"
  // resolves to nothing and reads as a broken product rather than an honest one.
  const prompts = knownActions.length
    ? [...s.suggestions, ...(s.navSuggestions ?? [])]
    : s.suggestions
  for (const text of prompts) {
    const b = document.createElement('button')
    b.type = 'button'
    b.textContent = text
    b.onclick = () => send(text)
    box.appendChild(b)
  }
}

// --- Streaming client (SSE over fetch) -------------------------------------------
async function streamChat(message, history, callbacks, signal) {
  const response = await fetch(`${BASE_URL}/v2/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      message,
      history,
      session_id: sessionId,
      client: 'chrome-extension',
      locale: lang,
      // Deliberately no page context: no URL, no title, no DOM. The store
      // listing says this extension does not read the page, and that is only
      // true if the request carries nothing from it.
    }),
  })

  if (!response.ok) {
    // Structured refusals (429/503) carry a stable code; surface that rather
    // than "HTTP 503".
    let code = null
    try {
      code = (await response.json())?.code ?? null
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(code || `HTTP ${response.status}`)
    err.code = code
    err.retryAfter = Number(response.headers.get('Retry-After')) || null
    // The join key between what a student can quote and the protected log line
    // that holds the provider's actual error. Surfacing it means a bug can be
    // reported without anyone asking the student to repeat their question.
    err.requestId = response.headers.get('X-Request-ID')
    throw err
  }
  if (!response.body) throw new Error('EMPTY_RESPONSE')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // An SSE frame ends with a blank line, which the spec allows to be CRLF,
    // LF or CR. Splitting on '\n\n' alone means a proxy that normalises to
    // CRLF produces one frame that never terminates, and the panel streams
    // nothing at all while appearing to work.
    const frames = buffer.split(/\r\n\r\n|\n\n|\r\r/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      // `data:` may legally be repeated; the value is the lines joined by LF.
      const data = frame
        .split(/\r\n|\n|\r/)
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trim())
        .join('\n')
      if (!data) continue
      let event
      try {
        event = JSON.parse(data)
      } catch {
        continue
      }
      // Unknown event types are ignored on purpose: the server may add one in a
      // later release, and a published extension must not break when it does.
      switch (event.type) {
        case 'sources': callbacks.onSources?.(event.sources ?? []); break
        case 'token': callbacks.onToken?.(event.text); break
        case 'blocked': callbacks.onReplace?.(event.answer); break
        case 'repair': callbacks.onReplace?.(event.answer); break
        case 'about': callbacks.onReplace?.(event.answer); break
        case 'links': callbacks.onLinks?.(event.links ?? []); break
        case 'navigation': callbacks.onNavigation?.(event.action); break
        case 'error': callbacks.onError?.(event.code, event.message); break
        case 'done': return
        default: break
      }
    }
  }
}

// --- Send flow --------------------------------------------------------------------
function setBusy(next) {
  busy = next
  $('send').hidden = next
  $('stop').hidden = !next
  $('send').disabled = next || !$('input').value.trim()
}

async function send(preset) {
  const input = $('input')
  const message = (preset ?? input.value).trim()
  if (!message || busy) return

  // Refuse locally rather than spending a round trip on a request the server
  // will reject. MAX_MESSAGE_CHARS mirrors the server's limit; the two are kept
  // in step by scripts/check_extension.py.
  if (message.length > MAX_MESSAGE_CHARS) {
    showStatus(S().tooLong.replace('{max}', String(MAX_MESSAGE_CHARS)))
    return
  }
  if (!navigator.onLine) {
    showStatus(S().offline)
    return
  }
  showStatus(null)
  input.value = ''
  setBusy(true)

  // History = the transcript BEFORE this message (the server bounds it again).
  const history = turns.slice(-8).map((t) => ({ role: t.role, content: t.content }))

  if (!turns.length) $('suggestions').innerHTML = ''
  if (thread().querySelector('.welcome')) thread().innerHTML = ''

  turns.push({ role: 'user', content: message })
  addBubble('user', message)

  const spinner = document.createElement('div')
  spinner.className = 'thinking'
  spinner.textContent = S().thinking
  thread().appendChild(spinner)
  thread().scrollTop = thread().scrollHeight
  announce(S().thinking)

  let raw = '' // accumulated answer WITH citations (for exact streaming math)
  let bubble = null
  let textNode = null
  const turn = { role: 'assistant', content: '' }

  const show = (full) => {
    raw = full
    turn.content = stripCitations(full)
    if (!bubble) {
      spinner.remove()
      const made = addBubble('assistant', turn.content)
      bubble = made.bubble
      textNode = made.text
      announce(S().answering)
    } else {
      textNode.textContent = turn.content
    }
    thread().scrollTop = thread().scrollHeight
  }

  controller = new AbortController()
  let aborted = false
  try {
    await streamChat(message, history, {
      onToken: (delta) => show(raw + delta),
      onReplace: (answer) => show(answer),
      onSources: (sources) => { turn.sources = sources },
      onLinks: (links) => {
        if (!links.length) return
        turn.links = links
        if (bubble) renderLinks(bubble, links)
      },
      onNavigation: (action) => {
        turn.navigation = action
        if (bubble) renderNavigation(bubble, action)
      },
      onError: (code, message) => {
        showStatus(messageForCode(code, message))
        if (!raw) show(messageForCode(code, message))
      },
    }, controller.signal)
    // Sources arrive before the first token, so they are attached after the
    // stream settles rather than re-rendering the bubble mid-answer.
    if (bubble && turn.sources?.length) renderSources(bubble, turn.sources)
  } catch (err) {
    if (err?.name === 'AbortError') {
      aborted = true
      if (!raw) {
        spinner.remove()
        announce(S().stopped)
      }
    } else {
      const text = messageForCode(err?.code, null)
      showStatus(text)
      showRequestId(err?.requestId)
      show(raw || text)
    }
  } finally {
    controller = null
  }

  spinner.remove()
  if (!turn.content && !aborted) show(S().error)
  if (turn.content) {
    turns.push(turn)
    saveState()
    announce(S().answered)
  }
  setBusy(false)
  input.focus()
}

// --- Wire-up -------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  await loadState()
  applyLang()

  // The finder is drawn from the bundled registry before any network call, so
  // the panel is useful the instant it opens — including with the backend down.
  renderFinder()
  refreshCapabilities()

  // Coming back online is the moment a "chat unavailable" pill is most likely
  // to be stale, and the moment a student retries.
  window.addEventListener('online', () => refreshCapabilities())
  window.addEventListener('offline', () => setServicePill('offline'))

  const input = $('input')
  input.addEventListener('input', () => {
    $('send').disabled = !input.value.trim() || busy
  })
  $('composer').addEventListener('submit', (e) => {
    e.preventDefault()
    send()
  })

  // Stopping matters on a metered provider: an abandoned stream that runs to
  // completion still spends the day's quota on tokens nobody reads.
  $('stop').addEventListener('click', () => {
    controller?.abort()
    showStatus(S().stopped)
  })

  $('new-chat').addEventListener('click', () => {
    controller?.abort()
    turns = []
    sessionId = newSessionId()
    saveState()
    renderThread()
    input.focus()
  })

  // Distinct from "new chat": this erases what is stored on disk, which is the
  // action the privacy policy promises a student can take.
  $('clear-history').addEventListener('click', async () => {
    controller?.abort()
    turns = []
    sessionId = newSessionId()
    await chrome.storage.local.remove('session')
    renderThread()
    showStatus(S().cleared)
    announce(S().cleared)
  })

  $('lang-toggle').addEventListener('click', () => {
    lang = lang === 'ar' ? 'en' : 'ar'
    saveState()
    applyLang()
  })

  window.addEventListener('online', () => showStatus(null))
  window.addEventListener('offline', () => showStatus(S().offline))

  input.focus()
})
