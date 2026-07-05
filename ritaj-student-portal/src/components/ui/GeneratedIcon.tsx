export type GeneratedIconName =
  | 'graduation' | 'pencil' | 'search' | 'message' | 'chevron' | 'ellipsis'
  | 'panel-close' | 'trash' | 'menu' | 'arrow-right' | 'moon' | 'sun'
  | 'bell' | 'share' | 'refresh' | 'sparkle' | 'book' | 'check'
  | 'dollar' | 'clock' | 'copy' | 'thumbs-up' | 'thumbs-down' | 'paperclip'
  | 'microphone' | 'arrow-up' | 'calendar' | 'compass' | 'shield' | 'assistant'

type Props = {
  name: GeneratedIconName
  size?: number
  rotate?: number
  className?: string
}

export function GeneratedIcon({ name, size = 18, rotate = 0, className = '' }: Props) {
  return (
    <img
      className={`generated-icon ${className}`}
      src={`/assets/generated-icons/${name}.png`}
      width={size}
      height={size}
      style={{ transform: rotate ? `rotate(${rotate}deg)` : undefined }}
      alt=""
      aria-hidden="true"
      draggable={false}
    />
  )
}
