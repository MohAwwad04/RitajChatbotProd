import { Brand } from '../ui/Brand'
import { GeneratedIcon } from '../ui/GeneratedIcon'
import { useI18n } from '../../i18n'

type Props = { open: boolean; onClose: () => void; onNewChat: () => void }

export function ChatSidebar({ open, onClose, onNewChat }: Props) {
  const { s } = useI18n()
  return (
    <aside className={`chat-sidebar ${open ? 'is-open' : ''}`}>
      <div className="chat-sidebar__brand">
        <Brand />
        <button className="chat-icon-button chat-sidebar__close" onClick={onClose} aria-label={s.aria_close_chats}><GeneratedIcon name="panel-close" size={19} /></button>
      </div>
      <button className="chat-new-button" onClick={onNewChat}><GeneratedIcon name="pencil" size={18} /> {s.new_chat} <span>⌘ N</span></button>
      <label className="chat-history-search"><GeneratedIcon name="search" size={17} /><input placeholder={s.search_chats} /></label>
      <div className="chat-history">
        <span className="chat-history__label">{s.recent_label}</span>
        {s.recentChats.map((chat) => (
          <button className={`chat-history__item ${chat.active ? 'is-active' : ''}`} key={chat.title}>
            <GeneratedIcon name="message" size={18} />
            <span><strong>{chat.title}</strong><small>{chat.time}</small></span>
            {chat.active ? <GeneratedIcon name="ellipsis" size={17} /> : <GeneratedIcon name="chevron" size={16} />}
          </button>
        ))}
      </div>
      <div className="chat-sidebar__footer">
        <button><GeneratedIcon name="trash" size={17} /> {s.manage_history}</button>
      </div>
    </aside>
  )
}
