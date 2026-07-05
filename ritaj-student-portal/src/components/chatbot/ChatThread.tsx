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

function RegistrationAnswer() {
  return (
    <div className="registration-answer">
      <div className="readiness-line"><span><GeneratedIcon name="check" size={15} /></span><div><strong>الخطة الدراسية جاهزة</strong><small>المساقات المقترحة متوافقة مع متطلباتك السابقة.</small></div></div>
      <div className="readiness-line is-warning"><span><GeneratedIcon name="dollar" size={16} /></span><div><strong>يلزم تسوية الرصيد المالي</strong><small>الرصيد المستحق 240 د.أ قبل فتح التسجيل.</small></div></div>
      <div className="course-suggestion">
        <div className="course-suggestion__head"><span><GeneratedIcon name="book" size={17} /> اقتراح رتاج</span><small>6 ساعات</small></div>
        <strong>أنظمة التشغيل · ENCS 3390</strong>
        <p>مع مشروع التخرج 1 · COMP 440</p>
        <button>عرض الخطة المقترحة <GeneratedIcon name="arrow-up" size={15} rotate={-45} /></button>
      </div>
      <div className="registration-window"><GeneratedIcon name="clock" size={17} /><span><small>نافذة تسجيلك</small><strong>غداً، 09:00 – 11:00 صباحاً</strong></span></div>
    </div>
  )
}

export function ChatThread({ messages, thinking, userName }: { messages: ChatMessage[]; thinking: boolean; userName: string }) {
  const { s } = useI18n()
  const endRef = useRef<HTMLDivElement>(null)
  const previousState = useRef({ messageCount: messages.length, thinking })
  useEffect(() => {
    const changed = previousState.current.messageCount !== messages.length || previousState.current.thinking !== thinking
    previousState.current = { messageCount: messages.length, thinking }
    if (!changed) return
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, thinking])

  return (
    <div className="chat-thread" aria-live="polite">
      <div className="chat-day-divider"><span>{s.today}</span></div>
      <section className="chat-visual-overview" aria-label={s.aria_overview}>
        <img src="/assets/ritaj-ai-portal.png" alt={s.img_alt} />
        <div className="chat-visual-overview__content">
          <span>{s.greeting} {userName}</span>
          <h1>{s.overview_h1}</h1>
          <p>{s.overview_p}</p>
          <div className="chat-visual-overview__signals">
            <span><i /> {s.signal_connected}</span>
            <span>{s.signal_courses}</span>
            <span>{s.signal_progress}</span>
          </div>
        </div>
      </section>
      {messages.map((message) => (
        <div className={`chat-message chat-message--${message.role}`} key={message.id}>
          {message.role === 'assistant' && <AssistantMark />}
          <div className="chat-message__body">
            {message.role === 'assistant' && <span className="message-author">{s.assistant_name} <i>{s.verified}</i></span>}
            <div className="message-bubble"><p>{message.content}</p>{message.type === 'registration' && <RegistrationAnswer />}</div>
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
              {message.role === 'assistant' && <span className="message-tools"><button aria-label={s.aria_copy}><GeneratedIcon name="copy" size={14} /></button></span>}
            </div>
          </div>
        </div>
      ))}
      {thinking && (
        <div className="chat-message chat-message--assistant">
          <AssistantMark />
          <div className="chat-message__body"><span className="message-author">{s.assistant_name}</span><div className="thinking-bubble"><i /><i /><i /><span>{s.thinking}</span><GeneratedIcon name="refresh" size={14} /></div></div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}
