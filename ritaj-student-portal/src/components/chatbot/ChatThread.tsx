import { useEffect, useRef } from 'react'
import type { ChatMessage } from './chatData'
import { GeneratedIcon } from '../ui/GeneratedIcon'
import { useI18n } from '../../i18n'

function AssistantMark() {
  const { s } = useI18n()
  return (
    <span className="assistant-mark" aria-label={s.assistant_name}>
      <GeneratedIcon name="assistant" size={19} />
      <i />
    </span>
  )
}

// `RegistrationAnswer` used to render here: a hand-written "answer" card with a
// 240 JD outstanding balance, a suggested course load and a registration window
// of "tomorrow, 09:00–11:00". It fired on `message.type === 'registration'` and
// none of it came from the backend — it was UI-authored content presented as an
// assistant answer, which is the one thing a grounded, cited product may never
// do. Answers now render only from streamed server events.

export function ChatThread({ messages, thinking }: { messages: ChatMessage[]; thinking: boolean }) {
  const { s } = useI18n()
  const endRef = useRef<HTMLDivElement>(null)
  const previousState = useRef({ messageCount: messages.length, thinking })
  useEffect(() => {
    const changed =
      previousState.current.messageCount !== messages.length || previousState.current.thinking !== thinking
    previousState.current = { messageCount: messages.length, thinking }
    if (!changed) return
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, thinking])

  return (
    <div className="chat-thread" aria-live="polite">
      {messages.length === 0 ? (
        // The opening screen describes the assistant, and nothing else. It
        // previously claimed "Record connected · 5 courses · 82% of plan" over a
        // backend that has never read a student record.
        <section className="chat-visual-overview" aria-label={s.aria_overview}>
          <img src="/assets/ritaj-ai-portal.png" alt={s.img_alt} />
          <div className="chat-visual-overview__content">
            <span>{s.greeting}</span>
            <h1>{s.hero_h1}</h1>
            <p>{s.hero_p}</p>
            <div className="chat-visual-overview__signals">
              <span><i /> {s.assistant_status}</span>
              <span>{s.verified}</span>
            </div>
            <small className="chat-visual-overview__note">{s.unofficial}</small>
          </div>
        </section>
      ) : (
        <div className="chat-day-divider"><span>{s.today}</span></div>
      )}

      {messages.map((message) => (
        <div className={`chat-message chat-message--${message.role}`} key={message.id}>
          {message.role === 'assistant' && <AssistantMark />}
          <div className="chat-message__body">
            {message.role === 'assistant' && (
              <span className="message-author">{s.assistant_name} <i>{s.verified}</i></span>
            )}
            <div className="message-bubble"><p>{message.content}</p></div>
            {message.role === 'assistant' && message.images && message.images.length > 0 && (
              <div className="message-team">
                {message.images.map((img) => (
                  <figure key={img.url}>
                    <img src={img.url} alt={img.caption ?? ''} loading="lazy" />
                    {img.caption && <figcaption>{img.caption}</figcaption>}
                  </figure>
                ))}
              </div>
            )}
            {message.role === 'assistant' && message.links && message.links.length > 0 && (
              <div className="message-links">
                {message.links.map((link) => (
                  <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer">
                    {link.label} <GeneratedIcon name="arrow-up" size={13} rotate={45} />
                  </a>
                ))}
              </div>
            )}
            <div className="message-meta">
              <time>{message.time}</time>
              {message.role === 'assistant' && (
                <span className="message-tools">
                  <button
                    aria-label={s.aria_copy}
                    onClick={() => navigator.clipboard?.writeText(message.content)}
                  >
                    <GeneratedIcon name="copy" size={14} />
                  </button>
                </span>
              )}
            </div>
          </div>
        </div>
      ))}

      {thinking && (
        <div className="chat-message chat-message--assistant">
          <AssistantMark />
          <div className="chat-message__body">
            <span className="message-author">{s.assistant_name}</span>
            <div className="thinking-bubble">
              <i /><i /><i /><span>{s.thinking}</span>
              <GeneratedIcon name="refresh" size={14} />
            </div>
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}
