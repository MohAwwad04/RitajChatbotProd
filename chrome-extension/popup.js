// Ritaj Assistant popup — a thin client over the hosted RAG backend.
//
// The server is stateless: the popup owns the conversation, persists it in
// chrome.storage.local (so closing the popup doesn't lose the chat), and sends
// the prior turns back with every message so follow-ups resolve correctly.

/* global BASE_URL, chrome */

// --- i18n --------------------------------------------------------------------
const STRINGS = {
  en: {
    dir: 'ltr',
    subtitle: 'Birzeit University',
    placeholder: 'Ask about Ritaj or Birzeit…',
    welcome: 'Hi! I’m the Ritaj Assistant. Ask me about registration, fees, grades, the academic calendar, IT help, or anything Birzeit.',
    error: 'Could not reach the assistant. Please check your connection and try again.',
    suggestions: [
      'How do I register for courses?',
      'How much is one credit hour?',
      'When does the semester start?',
      'I forgot my Ritaj password',
    ],
  },
  ar: {
    dir: 'rtl',
    subtitle: 'جامعة بيرزيت',
    placeholder: 'اسأل عن ريتاج أو جامعة بيرزيت…',
    welcome: 'أهلاً! أنا مساعد ريتاج. اسألني عن التسجيل، الرسوم، العلامات، التقويم الأكاديمي، الدعم الفني، أو أي شيء عن بيرزيت.',
    error: 'تعذّر الوصول إلى المساعد. تحقّق من اتصالك بالإنترنت وحاول مرة أخرى.',
    suggestions: [
      'كيف أسجّل المساقات؟',
      'كم سعر الساعة المعتمدة؟',
      'متى يبدأ الفصل الدراسي؟',
      'نسيت كلمة سر ريتاج',
    ],
  },
}

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
let turns = [] // [{role, content, links?}] — content is the citation-free text
let busy = false

const $ = (id) => document.getElementById(id)
const thread = $('thread')

function newSessionId() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
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

function saveState() {
  chrome.storage.local.set({ lang, session: { sessionId, turns } })
}

// --- Rendering ------------------------------------------------------------------
function applyLang() {
  const s = STRINGS[lang]
  document.documentElement.dir = s.dir
  document.body.dir = s.dir
  $('subtitle').textContent = s.subtitle
  $('input').placeholder = s.placeholder
  $('lang-toggle').textContent = lang === 'ar' ? 'EN' : 'ع'
  renderThread()
}

function renderLinks(container, links) {
  if (!links || !links.length) return
  const box = document.createElement('div')
  box.className = 'links'
  for (const { label, url } of links) {
    const a = document.createElement('a')
    a.href = url
    a.textContent = label
    a.target = '_blank'
    a.rel = 'noopener'
    box.appendChild(a)
  }
  container.appendChild(box)
}

function addBubble(role, content, links) {
  const div = document.createElement('div')
  div.className = `msg msg--${role}`
  div.textContent = content
  renderLinks(div, links)
  thread.appendChild(div)
  thread.scrollTop = thread.scrollHeight
  return div
}

function renderThread() {
  const s = STRINGS[lang]
  thread.innerHTML = ''
  if (!turns.length) {
    const w = document.createElement('div')
    w.className = 'welcome'
    w.textContent = s.welcome
    thread.appendChild(w)
    renderSuggestions()
    return
  }
  $('suggestions').innerHTML = ''
  for (const t of turns) addBubble(t.role, t.content, t.links)
}

function renderSuggestions() {
  const box = $('suggestions')
  box.innerHTML = ''
  for (const text of STRINGS[lang].suggestions) {
    const b = document.createElement('button')
    b.type = 'button'
    b.textContent = text
    b.onclick = () => send(text)
    box.appendChild(b)
  }
}

// --- Streaming client (SSE over fetch, mirrors the portal) -----------------------
async function streamChat(message, history, callbacks) {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history,
      session_id: sessionId,
      client: 'extension',
    }),
  })
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)

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
      try { event = JSON.parse(line.slice(5).trim()) } catch { continue }
      switch (event.type) {
        case 'token': callbacks.onToken?.(event.text); break
        case 'blocked': callbacks.onReplace?.(event.answer); break
        case 'repair': callbacks.onReplace?.(event.answer); break
        case 'about': callbacks.onReplace?.(event.answer); break
        case 'links': callbacks.onLinks?.(event.links ?? []); break
        case 'error': callbacks.onError?.(event.message); break
        case 'done': return
      }
    }
  }
}

// --- Send flow --------------------------------------------------------------------
async function send(preset) {
  const input = $('input')
  const message = (preset ?? input.value).trim()
  if (!message || busy) return
  busy = true
  input.value = ''
  $('send').disabled = true

  // History = the transcript BEFORE this message (server bounds it again).
  const history = turns.slice(-8).map((t) => ({ role: t.role, content: t.content }))

  if (!turns.length) $('suggestions').innerHTML = ''
  if (thread.querySelector('.welcome')) thread.innerHTML = ''

  turns.push({ role: 'user', content: message })
  addBubble('user', message)

  const spinner = document.createElement('div')
  spinner.className = 'thinking'
  thread.appendChild(spinner)
  thread.scrollTop = thread.scrollHeight

  let raw = '' // accumulated answer WITH citations (for exact streaming math)
  let bubble = null
  const turn = { role: 'assistant', content: '', links: undefined }

  const show = (full) => {
    raw = full
    turn.content = stripCitations(full)
    if (!bubble) {
      spinner.remove()
      bubble = addBubble('assistant', turn.content)
    } else {
      bubble.firstChild ? (bubble.childNodes[0].textContent = turn.content) : (bubble.textContent = turn.content)
    }
    thread.scrollTop = thread.scrollHeight
  }

  try {
    await streamChat(message, history, {
      onToken: (delta) => show(raw + delta),
      onReplace: (answer) => show(answer),
      onLinks: (links) => {
        if (!links.length || !bubble) return
        turn.links = links
        renderLinks(bubble, links)
        thread.scrollTop = thread.scrollHeight
      },
      onError: (msg) => { if (!raw) show(STRINGS[lang].error) },
    })
  } catch {
    show(raw || STRINGS[lang].error)
  }

  if (!turn.content) show(STRINGS[lang].error)
  turns.push(turn)
  saveState()
  spinner.remove()
  busy = false
  $('send').disabled = !input.value.trim()
  input.focus()
}

// --- Wire-up -------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
  await loadState()
  applyLang()

  const input = $('input')
  input.addEventListener('input', () => { $('send').disabled = !input.value.trim() || busy })
  $('composer').addEventListener('submit', (e) => { e.preventDefault(); send() })
  $('new-chat').onclick = () => {
    turns = []
    sessionId = newSessionId()
    saveState()
    renderThread()
    input.focus()
  }
  $('lang-toggle').onclick = () => {
    lang = lang === 'ar' ? 'en' : 'ar'
    saveState()
    applyLang()
  }
  $('open-portal').onclick = () => chrome.tabs ? chrome.tabs.create({ url: BASE_URL }) : window.open(BASE_URL)
  input.focus()
})
