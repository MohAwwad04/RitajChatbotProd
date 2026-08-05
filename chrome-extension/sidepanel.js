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

import { validateAction } from './navigation.js'

/* global BASE_URL, MAX_MESSAGE_CHARS, chrome */

// --- i18n --------------------------------------------------------------------
const STRINGS = {
  en: {
    dir: 'ltr',
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
      'Open course registration',
    ],
  },
  ar: {
    dir: 'rtl',
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
      'افتح تسجيل المساقات',
    ],
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
  $('subtitle').textContent = s.subtitle
  $('input').placeholder = s.placeholder
  $('disclaimer-text').textContent = s.disclaimer
  $('lang-toggle').textContent = lang === 'ar' ? 'EN' : 'ع'
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
  if (!links?.length) return
  const box = document.createElement('div')
  box.className = 'links'
  for (const { label, url } of links) {
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
  for (const text of S().suggestions) {
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
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      let event
      try {
        event = JSON.parse(line.slice(5).trim())
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
