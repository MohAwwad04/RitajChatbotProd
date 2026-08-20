import type { PageLink, TeamImage } from '../../api/chat'

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  time: string
  links?: PageLink[]
  images?: TeamImage[]
}

// One conversation in *this* browser session. Nothing is persisted: the server
// is stateless by design and the client owns the transcript, so a reload starts
// clean. That is also why the sidebar can list these honestly — they are real
// conversations the student had a moment ago, unlike the four hard-coded
// "recent chats" ("COMP 433 exam date", "Financial record details") this file
// used to export, which appeared identically for every visitor on first load.
export type Conversation = {
  id: string
  title: string
  messages: ChatMessage[]
}

// `initialMessages`, `suggestions`, `recentChats` and `answerFor` are gone.
// `answerFor` was a keyword-matching fake responder that invented balances,
// exam dates and remaining credit hours in the UI layer — a second, ungrounded
// answer path sitting next to the cited one.

export const newSessionId = (): string =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`

// A conversation is titled by its first question, which is the only label the
// client can produce without asking the student for one.
export function titleFor(conversation: Conversation, fallback: string): string {
  const first = conversation.messages.find((message) => message.role === 'user')
  if (!first) return fallback
  return first.content.length > 42 ? `${first.content.slice(0, 42)}…` : first.content
}
