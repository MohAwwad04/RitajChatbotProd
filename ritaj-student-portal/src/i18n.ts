import { createContext, useContext } from 'react'

export type Lang = 'ar' | 'en'

// One flat dictionary per language. `ar` and `en` must have identical shapes —
// components read the current language's object via useI18n().s, so any missing
// key would be a type error.
export const dict = {
  ar: {
    dir: 'rtl' as const,

    assistant_name: 'مساعد رتاج',
    assistant_status: 'متصل بسجلك الأكاديمي',
    verified: 'موثّق',
    thinking: 'أراجع سجلك الأكاديمي',
    new_chat: 'محادثة جديدة',
    error_connect: 'تعذّر الاتصال بالمساعد الآن. يرجى المحاولة مرة أخرى.',

    search_chats: 'ابحث في المحادثات',
    recent_label: 'المحادثات الأخيرة',
    manage_history: 'إدارة سجل المحادثات',

    greeting: 'أهلاً بك',
    today: 'اليوم',
    overview_h1: 'كل طريقك في مكان واحد',
    overview_p: 'اسأل عن خطتك، مواعيدك، ورسومك. يربط رتاج الإجابة بسجلك الحالي.',
    signal_connected: 'السجل متصل',
    signal_courses: '5 مساقات',
    signal_progress: '82% من الخطة',

    composer_placeholder: 'اسأل رتاج عن خطتك، مساقاتك، أو مواعيدك...',
    composer_note: 'يعتمد رتاج على بيانات النظام، وقد تحتاج بعض المعلومات إلى تأكيد من الدائرة المختصة.',

    brand_name: 'رتــاج',
    brand_sub: 'بوابة الطالب',

    aria_lang: 'English',
    aria_open_chats: 'فتح المحادثات',
    aria_close_chats: 'إغلاق المحادثات',
    aria_back_home: 'العودة للرئيسية',
    aria_toggle_theme: 'تبديل المظهر',
    aria_notifications: 'التنبيهات',
    aria_share: 'مشاركة المحادثة',
    aria_close_panel: 'إغلاق اللوحة',
    aria_attach: 'إرفاق ملف',
    aria_write: 'اكتب سؤالك',
    aria_voice: 'إدخال صوتي',
    aria_send: 'إرسال',
    aria_copy: 'نسخ',
    aria_overview: 'مساعد رتاج الأكاديمي',
    aria_brand: 'رتاج',
    img_alt: 'بوابة أكاديمية تحيط بها رموز الدراسة والتقويم والتخرج',

    suggestions: ['لخّص وضعي الأكاديمي', 'متى امتحاني القادم؟', 'ما المتبقي من خطتي؟', 'اشرح رصيدي المالي'],
    recentChats: [
      { title: 'التسجيل للدورة الصيفية', time: 'الآن', active: true },
      { title: 'متطلبات التخرج المتبقية', time: 'أمس' },
      { title: 'موعد امتحان COMP 433', time: '18 حزيران' },
      { title: 'تفاصيل السجل المالي', time: '12 حزيران' },
    ],
  },
  en: {
    dir: 'ltr' as const,

    assistant_name: 'Ritaj Assistant',
    assistant_status: 'Connected to your academic record',
    verified: 'Verified',
    thinking: 'Reviewing your academic record',
    new_chat: 'New chat',
    error_connect: "Couldn't reach the assistant right now. Please try again.",

    search_chats: 'Search conversations',
    recent_label: 'Recent conversations',
    manage_history: 'Manage chat history',

    greeting: 'Welcome',
    today: 'Today',
    overview_h1: 'Your whole journey in one place',
    overview_p: 'Ask about your plan, deadlines, and fees. Ritaj ties the answer to your current record.',
    signal_connected: 'Record connected',
    signal_courses: '5 courses',
    signal_progress: '82% of plan',

    composer_placeholder: 'Ask Ritaj about your plan, courses, or deadlines...',
    composer_note: 'Ritaj relies on system data; some details may need confirmation from the relevant office.',

    brand_name: 'Ritaj',
    brand_sub: 'Student Portal',

    aria_lang: 'العربية',
    aria_open_chats: 'Open conversations',
    aria_close_chats: 'Close conversations',
    aria_back_home: 'Back to home',
    aria_toggle_theme: 'Toggle theme',
    aria_notifications: 'Notifications',
    aria_share: 'Share conversation',
    aria_close_panel: 'Close panel',
    aria_attach: 'Attach file',
    aria_write: 'Type your question',
    aria_voice: 'Voice input',
    aria_send: 'Send',
    aria_copy: 'Copy',
    aria_overview: 'Ritaj academic assistant',
    aria_brand: 'Ritaj',
    img_alt: 'An academic portal surrounded by study, calendar, and graduation icons',

    suggestions: ['Summarize my academic status', 'When is my next exam?', "What's left in my plan?", 'Explain my balance'],
    recentChats: [
      { title: 'Summer-term registration', time: 'Now', active: true },
      { title: 'Remaining graduation requirements', time: 'Yesterday' },
      { title: 'COMP 433 exam date', time: 'Jun 18' },
      { title: 'Financial record details', time: 'Jun 12' },
    ],
  },
}

type Direction = 'rtl' | 'ltr'
// Widen `dir` so both languages share one shape (ar→rtl, en→ltr).
export type Strings = Omit<typeof dict['ar'], 'dir'> & { dir: Direction }

type Ctx = { lang: Lang; setLang: (l: Lang) => void; s: Strings }
export const LangContext = createContext<Ctx>({ lang: 'ar', setLang: () => {}, s: dict.ar })
export const useI18n = () => useContext(LangContext)
