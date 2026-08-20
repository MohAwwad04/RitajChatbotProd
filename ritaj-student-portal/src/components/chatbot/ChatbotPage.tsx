import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { streamChat, stripCitations } from '../../api/chat'
import { newSessionId, type ChatMessage, type Conversation } from './chatData'
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

type Props = {
  darkMode: boolean
  onToggleTheme: () => void
  onBack: () => void
  // A question chosen on the home view, handed over to be sent once.
  pendingQuestion: string | null
  onPendingConsumed: () => void
}

export function ChatbotPage({ darkMode, onToggleTheme, onBack, pendingQuestion, onPendingConsumed }: Props) {
  const { s, lang } = useI18n()
  const [conversations, setConversations] = useState<Conversation[]>(() => [
    { id: newSessionId(), title: '', messages: [] },
  ])
  const [activeId, setActiveId] = useState<string>(() => '')
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Seed the active id from the initial conversation without a second render.
  const currentId = activeId || conversations[0].id
  const messages = useMemo(
    () => conversations.find((c) => c.id === currentId)?.messages ?? [],
    [conversations, currentId],
  )

  const patchMessages = useCallback(
    (id: string, update: (current: ChatMessage[]) => ChatMessage[]) => {
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === id ? { ...conversation, messages: update(conversation.messages) } : conversation,
        ),
      )
    },
    [],
  )

  const newChat = useCallback(() => {
    const id = newSessionId()
    // Drop an untouched conversation rather than accumulating empty shells.
    setConversations((current) => [...current.filter((c) => c.messages.length > 0), { id, title: '', messages: [] }])
    setActiveId(id)
    setSidebarOpen(false)
    setInput('')
  }, [])

  const clearSession = useCallback(() => {
    const id = newSessionId()
    setConversations([{ id, title: '', messages: [] }])
    setActiveId(id)
    setInput('')
  }, [])

  const sendMessage = useCallback(
    (preset?: string) => {
      const content = (preset ?? input).trim()
      if (!content || thinking) return
      const conversationId = currentId
      const now = () => new Date().toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
      const userMessage: ChatMessage = { id: Date.now(), role: 'user', content, time: now() }
      // Conversation memory: replay the visible transcript (before this message)
      // so the backend can resolve follow-ups. The server bounds it again.
      const history = messages
        .filter((m) => m.content)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.content }))
      patchMessages(conversationId, (current) => [...current, userMessage])
      setInput('')
      setThinking(true)

      // Stream the real answer from the RAG backend into a single assistant
      // bubble, created on the first event (so "thinking" shows until then) and
      // updated in place as tokens / repair / block events arrive.
      const assistantId = Date.now() + 1
      let created = false
      let text = ''
      // `full` keeps citations so the streaming math is exact; `shown` is what
      // the student sees, with the [n] markers stripped.
      const render = (full: string) => {
        text = full
        const shown = stripCitations(full)
        if (!created) {
          created = true
          setThinking(false)
          patchMessages(conversationId, (current) => [
            ...current,
            { id: assistantId, role: 'assistant', content: shown, time: now() },
          ])
        } else {
          patchMessages(conversationId, (current) =>
            current.map((m) => (m.id === assistantId ? { ...m, content: shown } : m)),
          )
        }
      }

      streamChat(
        content,
        {
          onToken: (delta) => render(text + delta),
          onBlocked: (answer) => render(answer),
          onRepair: (answer) => render(answer),
          // Attach the cited-page links to the (already-created) bubble.
          onLinks: (links) => {
            if (!links.length) return
            patchMessages(conversationId, (current) =>
              current.map((m) => (m.id === assistantId ? { ...m, links } : m)),
            )
          },
          // "Who made this?" — render the credit text and attach the photos.
          onAbout: (answer, images) => {
            render(answer)
            patchMessages(conversationId, (current) =>
              current.map((m) => (m.id === assistantId ? { ...m, images } : m)),
            )
          },
          // Prefer our own wording for a known code, then whatever the server
          // wrote, and only fall back to the generic "couldn't reach" line when
          // there genuinely was no response to read.
          onError: (message, code, requestId) => {
            // Our wording for a code we recognise, then whatever the server
            // wrote, and only then the generic line — which now means "no
            // response at all and no idea why", not "something went wrong".
            const reason =
              (code && s.error_codes[code]) || message || s.error_connect
            // The reference is what lets a student report a failure without
            // repeating their question; only shown when the server issued one.
            render(text || (requestId ? `${reason}\n\n${s.error_reference}: ${requestId}` : reason))
          },
          onDone: () => setThinking(false),
        },
        // The session id groups this conversation's turns in the aggregate log.
        // It identifies a chat, not a student.
        { history, sessionId: conversationId },
      )
    },
    [currentId, input, lang, messages, patchMessages, s.error_connect, s.error_codes,
     s.error_reference, thinking],
  )

  // A question picked on the home view arrives as a prop; send it once.
  const sendRef = useRef(sendMessage)
  sendRef.current = sendMessage
  useEffect(() => {
    if (!pendingQuestion) return
    sendRef.current(pendingQuestion)
    onPendingConsumed()
  }, [pendingQuestion, onPendingConsumed])

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        newChat()
      }
      if (event.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [newChat])

  return (
    <div className={`chatbot-app ${darkMode ? 'is-dark' : ''}`} dir={s.dir}>
      <ChatSidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={newChat}
        conversations={conversations}
        activeId={currentId}
        onSelect={(id) => { setActiveId(id); setSidebarOpen(false) }}
        onClearSession={clearSession}
      />
      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-header__title">
            <button className="chat-icon-button mobile-chat-button" onClick={() => setSidebarOpen(true)} aria-label={s.aria_open_chats}>
              <GeneratedIcon name="menu" size={20} />
            </button>
            <button className="chat-back-button" onClick={onBack} aria-label={s.aria_back_home}>
              <GeneratedIcon name="arrow-right" size={19} />
            </button>
            <div className="chat-assistant-avatar"><GeneratedIcon name="assistant" size={27} /><i /></div>
            <div><strong>{s.assistant_name}</strong><small><i /> {s.assistant_status}</small></div>
          </div>
          <div className="chat-header__actions">
            <LangToggle className="chat-icon-button" />
            <button className="chat-icon-button" onClick={onToggleTheme} aria-label={s.aria_toggle_theme}>
              {darkMode ? <GeneratedIcon name="sun" size={19} /> : <GeneratedIcon name="moon" size={19} />}
            </button>
            <button className="chat-reset-button" onClick={newChat}>
              <GeneratedIcon name="refresh" size={16} /> {s.new_chat}
            </button>
          </div>
        </header>
        <div className="chat-conversation">
          <ChatThread messages={messages} thinking={thinking} />
          <ChatComposer
            value={input}
            onChange={setInput}
            onSend={sendMessage}
            disabled={thinking}
            showSuggestions={messages.length === 0}
          />
        </div>
      </main>
      {sidebarOpen && (
        <button className="chat-page-backdrop" onClick={() => setSidebarOpen(false)} aria-label={s.aria_close_panel} />
      )}
    </div>
  )
}
