import { useEffect, useMemo, useState } from 'react'
import { ChatbotPage } from './components/chatbot/ChatbotPage'
import { LangContext, dict, type Lang } from './i18n'
import './styles/chatbot.css'

function App() {
  const [lang, setLang] = useState<Lang>('ar')

  // Flip the document direction/language with the UI language.
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dict[lang].dir
  }, [lang])

  const value = useMemo(() => ({ lang, setLang, s: dict[lang] }), [lang])

  return (
    <LangContext.Provider value={value}>
      <ChatbotPage />
    </LangContext.Provider>
  )
}

export default App
