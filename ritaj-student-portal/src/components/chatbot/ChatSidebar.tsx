import { useState } from 'react'
import { Brand } from '../ui/Brand'
import { GeneratedIcon } from '../ui/GeneratedIcon'
import { useI18n } from '../../i18n'
import { titleFor, type Conversation } from './chatData'

type Props = {
  open: boolean
  onClose: () => void
  onNewChat: () => void
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onClearSession: () => void
}

export function ChatSidebar({
  open,
  onClose,
  onNewChat,
  conversations,
  activeId,
  onSelect,
  onClearSession,
}: Props) {
  const { s } = useI18n()
  const [filter, setFilter] = useState('')

  // Only conversations that have actually been used are listed; an empty new
  // chat is not history.
  const listed = conversations
    .filter((conversation) => conversation.messages.length > 0)
    .filter((conversation) =>
      titleFor(conversation, s.untitled_chat).toLowerCase().includes(filter.trim().toLowerCase()),
    )

  return (
    <aside className={`chat-sidebar ${open ? 'is-open' : ''}`}>
      <div className="chat-sidebar__brand">
        <Brand />
        <button className="chat-icon-button chat-sidebar__close" onClick={onClose} aria-label={s.aria_close_chats}>
          <GeneratedIcon name="panel-close" size={19} />
        </button>
      </div>

      <button className="chat-new-button" onClick={onNewChat}>
        <GeneratedIcon name="pencil" size={18} /> {s.new_chat} <span>⌘ N</span>
      </button>

      <label className="chat-history-search">
        <GeneratedIcon name="search" size={17} />
        <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder={s.search_chats} />
      </label>

      <div className="chat-history">
        <span className="chat-history__label">{s.recent_label}</span>
        {listed.length === 0 && <p className="chat-history__empty">{s.no_chats}</p>}
        {listed.map((conversation) => (
          <button
            className={`chat-history__item ${conversation.id === activeId ? 'is-active' : ''}`}
            key={conversation.id}
            onClick={() => onSelect(conversation.id)}
          >
            <GeneratedIcon name="message" size={18} />
            <span>
              <strong>{titleFor(conversation, s.untitled_chat)}</strong>
              <small>{conversation.messages.length}</small>
            </span>
            <GeneratedIcon name="chevron" size={16} />
          </button>
        ))}
      </div>

      <div className="chat-sidebar__footer">
        <button onClick={onClearSession}>
          <GeneratedIcon name="trash" size={17} /> {s.manage_history}
        </button>
      </div>
    </aside>
  )
}
