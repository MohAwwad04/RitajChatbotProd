import { useEffect, useState } from 'react'
import { streamChat, stripCitations } from '../../api/chat'
import { type ChatMessage } from './chatData'
import { ChatComposer } from './ChatComposer'
import { ChatSidebar } from './ChatSidebar'
import { ChatThread } from './ChatThread'
import { GeneratedIcon } from '../ui/GeneratedIcon'
import { useI18n } from '../../i18n'

// Arabic ⇄ English switch; the label shows the language you'd switch TO.
function LangToggle({ className }: { className?: string }) {
  const { lang, setLang, s } = useI18n()
  return (
    <button type="button" className={className} onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')} aria-label={s.aria_lang}>
      {lang === 'ar' ? 'EN' : 'ع'}
    </button>
  )
}

// The name gate that used to live here has been removed (roadmap Phase 8).
//
// It asked every student for their name before the chat would open, and sent
// that name to the backend with every message — while the privacy policy said
// no names were collected. There are two ways to resolve a contradiction like
// that: change the policy, or stop collecting. Nothing in the product needed
// the name (it produced a sidebar avatar letter), so collecting it could not be
// justified.

// A fresh id per conversation so the admin log can group its turns.
const newSessionId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`

export function ChatbotPage() {
  const { s, lang } = useI18n()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [sessionId, setSessionId] = useState(newSessionId)

  const newChat = () => {
    setMessages([])
    setSidebarOpen(false)
    setInput('')
    setSessionId(newSessionId())
  }

  const sendMessage = (preset?: string) => {
    const content = (preset ?? input).trim()
    if (!content || thinking) return
    const now = () =>
      new Date().toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
    const userMessage: ChatMessage = { id: Date.now(), role: 'user', content, time: now() }
    // Conversation memory: replay the visible transcript (before this message)
    // so the backend can resolve follow-ups. The server bounds it again.
    const history = messages
      .filter((m) => m.content)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content }))
    setMessages((current) => [...current, userMessage])
    setInput('')
    setThinking(true)

    // Stream the real answer from the RAG backend into a single assistant bubble.
    // The bubble is created on the first event (so the "thinking" indicator shows
    // until then), and updated in place as tokens / repair / block events arrive.
    const assistantId = Date.now() + 1
    let created = false
    let text = ''
    // `full` is the raw accumulated answer (keeps citations so streaming math is
    // exact); `shown` is what the student sees, with the [n] markers stripped.
    const render = (full: string) => {
      text = full
      const shown = stripCitations(full)
      if (!created) {
        created = true
        setThinking(false)
        setMessages((current) => [
          ...current,
          { id: assistantId, role: 'assistant', content: shown, time: now() },
        ])
      } else {
        setMessages((current) =>
          current.map((m) => (m.id === assistantId ? { ...m, content: shown } : m)),
        )
      }
    }

    streamChat(content, {
      onToken: (delta) => render(text + delta),
      onBlocked: (answer) => render(answer),
      onRepair: (answer) => render(answer),
      // Attach the cited-page links to the (already-created) assistant bubble.
      onLinks: (links) => {
        if (!links.length) return
        setMessages((current) =>
          current.map((m) => (m.id === assistantId ? { ...m, links } : m)),
        )
      },
      // "Who made this?" — render the credit text and attach the team photos.
      onAbout: (answer, images) => {
        render(answer)
        setMessages((current) =>
          current.map((m) => (m.id === assistantId ? { ...m, images } : m)),
        )
      },
      onError: () => render(text || s.error_connect),
      onDone: () => setThinking(false),
    }, { history, sessionId })
  }

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        newChat()
      }
      if (event.key === 'Escape') {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  return (
    <div className={`chatbot-app ${darkMode ? 'is-dark' : ''}`} dir={s.dir}>
      <ChatSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} onNewChat={newChat} />
      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-header__title">
            <button className="chat-icon-button mobile-chat-button" onClick={() => setSidebarOpen(true)} aria-label={s.aria_open_chats}><GeneratedIcon name="menu" size={20} /></button>
            <button className="chat-back-button" aria-label={s.aria_back_home}><GeneratedIcon name="arrow-right" size={19} /></button>
            <div className="chat-assistant-avatar"><GeneratedIcon name="assistant" size={27} /><i /></div>
            <div><strong>{s.assistant_name}</strong><small><i /> {s.assistant_status}</small></div>
          </div>
          <div className="chat-header__actions">
            <LangToggle className="chat-icon-button" />
            <button className="chat-icon-button" onClick={() => setDarkMode((value) => !value)} aria-label={s.aria_toggle_theme}>{darkMode ? <GeneratedIcon name="sun" size={19} /> : <GeneratedIcon name="moon" size={19} />}</button>
            <button className="chat-icon-button desktop-chat-action" aria-label={s.aria_notifications}><GeneratedIcon name="bell" size={19} /></button>
            <button className="chat-icon-button desktop-chat-action" aria-label={s.aria_share}><GeneratedIcon name="share" size={19} /></button>
            <button className="chat-reset-button" onClick={newChat}><GeneratedIcon name="refresh" size={16} /> {s.new_chat}</button>
          </div>
        </header>
        <div className="chat-conversation">
          <ChatThread messages={messages} thinking={thinking} />
          <ChatComposer value={input} onChange={setInput} onSend={sendMessage} disabled={thinking} />
        </div>
      </main>
      {sidebarOpen && <button className="chat-page-backdrop" onClick={() => setSidebarOpen(false)} aria-label={s.aria_close_panel} />}
    </div>
  )
}
