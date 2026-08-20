import { GeneratedIcon } from '../ui/GeneratedIcon'
import { useI18n } from '../../i18n'

type Props = {
  value: string
  onChange: (value: string) => void
  onSend: (value?: string) => void
  disabled: boolean
  showSuggestions: boolean
}

// The attach and microphone buttons are gone. Neither had a handler: the
// product accepts no uploads and does no speech input, and a control that looks
// live but does nothing is a claim about the product like any other.
export function ChatComposer({ value, onChange, onSend, disabled, showSuggestions }: Props) {
  const { s } = useI18n()
  return (
    <div className="chat-composer-wrap">
      {showSuggestions && (
        <div className="chat-suggestions">
          {s.suggestions.map((suggestion) => (
            <button key={suggestion} onClick={() => onSend(suggestion)}>{suggestion}</button>
          ))}
        </div>
      )}
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); onSend() }}>
        <textarea
          aria-label={s.aria_write}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              onSend()
            }
          }}
          placeholder={s.composer_placeholder}
          rows={1}
        />
        <button className="composer-send" type="submit" disabled={!value.trim() || disabled} aria-label={s.aria_send}>
          <GeneratedIcon name="arrow-up" size={20} />
        </button>
      </form>
      <p className="composer-note"><GeneratedIcon name="sparkle" size={13} /> {s.composer_note}</p>
    </div>
  )
}
