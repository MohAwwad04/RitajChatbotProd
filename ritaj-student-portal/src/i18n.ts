import { createContext, useContext } from 'react'

export type Lang = 'ar' | 'en'

// One flat dictionary per language. `ar` and `en` must have identical shapes —
// components read the current language's object via useI18n().s, so any missing
// key would be a type error.
//
// A note on what this copy may claim. An earlier version of these strings told
// the student the assistant was "connected to your academic record" and offered
// "Summarize my academic status" as the first suggestion — while
// src/ritaj/guardrails.py declines every personal-record question by design and
// says so permanently ("I have no access to your student account"). The first
// tap on the first chip was a guaranteed refusal. Copy here therefore describes
// only what the backend does: read approved, public Ritaj pages, cite them, and
// hand off to a human office for anything else.
export const dict = {
  ar: {
    dir: 'rtl' as const,

    // --- identity -----------------------------------------------------------
    assistant_name: 'مساعد رتاج',
    assistant_status: 'يقرأ صفحات ريتاج العامة',
    verified: 'موثّق بالمصادر',
    thinking: 'أبحث في الصفحات المعتمدة',
    new_chat: 'محادثة جديدة',
    error_connect: 'تعذّر الاتصال بالمساعد الآن. يرجى المحاولة مرة أخرى.',
    // Per-code wording. The backend refuses with a stable code and the right
    // advice differs per cause — telling a student to "try again" when no
    // corpus has been approved is advice that can never come true.
    error_codes: {
      NO_CORPUS: 'الإجابات المبنية على المصادر متوقفة: لم تُنشر بعد أي مصادر معتمدة من ريتاج. لا يزال البحث عن الصفحات يعمل.',
      NOT_READY: 'المساعد غير متاح مؤقتاً. حاول بعد قليل.',
      INITIALIZING: 'المساعد قيد التشغيل. حاول بعد لحظات.',
      RATE_LIMITED: 'ترسل رسائل بسرعة كبيرة. انتظر لحظة ثم حاول مجدداً.',
      LLM_BUDGET_EXHAUSTED: 'بلغ المساعد حد الاستخدام اليومي. حاول غداً، أو افتح صفحة ريتاج مباشرة.',
      LLM_UNAVAILABLE: 'خدمة الإجابة غير متاحة حالياً. حاول بعد قليل.',
      LLM_TIMEOUT: 'استغرقت الإجابة وقتاً طويلاً. حاول مجدداً أو اطرح سؤالاً أقصر.',
      BUSY: 'المساعد مشغول حالياً. حاول بعد قليل.',
      REQUEST_TOO_LARGE: 'الرسالة طويلة جداً. يرجى اختصارها.',
      // Transport failures — the request never reached the service, or never
      // came back. Each says what is actually known, and what to do about it.
      OFFLINE: 'جهازك غير متصل بالإنترنت. لا يزال بحث الصفحات يعمل دون اتصال.',
      TIMEOUT: 'استغرق الخادم وقتاً طويلاً للرد. قد يكون قيد التشغيل — حاول بعد دقيقة.',
      UNREACHABLE: 'تعذّر الوصول إلى الخادم. اتصالك يعمل (فقد حمّلت هذه الصفحة)، لذا الخادم على الأرجح متوقف أو يعيد التشغيل. لا يمكن للمتصفح تحديد السبب بدقة.',
      STARTING_OR_ASLEEP: 'الخدمة قيد التشغيل أو كانت نائمة. تستغرق أول محاولة نحو دقيقة.',
      GATEWAY: 'تعذّر على المنصة الوصول إلى التطبيق. غالباً أثناء إعادة النشر — حاول بعد دقيقة.',
      HTTP_ERROR: 'ردّ الخادم بخطأ غير متوقع.',
      UNKNOWN: 'فشل الطلب لسبب غير معروف.',
    } as Record<string, string>,
    error_reference: 'الرقم المرجعي',
    unofficial: 'مشروع طلابي مستقل — ليس خدمة رسمية من جامعة بيرزيت',

    search_chats: 'ابحث في المحادثات',
    recent_label: 'محادثات هذه الجلسة',
    no_chats: 'لا توجد محادثات بعد في هذه الجلسة.',
    manage_history: 'مسح محادثات الجلسة',
    untitled_chat: 'محادثة جديدة',

    // --- shell / navigation -------------------------------------------------
    brand_name: 'رتــاج',
    brand_sub: 'مساعد الطالب',
    portal_label: 'مساعد الطالب',
    nav_group_about: 'عن المساعد',
    view_home: 'الرئيسية',
    view_ask: 'اسأل المساعد',
    view_topics: 'ما يمكنني الإجابة عنه',
    view_open: 'الانتقال إلى ريتاج',
    view_status: 'حالة الخدمة',
    view_privacy: 'الخصوصية',
    search_placeholder: 'ابحث في المواضيع المعتمدة...',

    // --- hero ---------------------------------------------------------------
    hero_eyebrow: 'مساعد مبني على مصادر ريتاج العامة',
    hero_h1: 'اسأل، واحصل على إجابة مع مصدرها',
    hero_p: 'يجيب المساعد من صفحات ريتاج العامة المعتمدة فقط، ويذكر الصفحة التي أخذ منها الإجابة. إن لم يجد مصدراً، يقول ذلك بدل أن يخمّن.',
    hero_cta: 'ابدأ سؤالاً',
    hero_secondary: 'ما الذي يمكنه الإجابة عنه؟',

    // --- stats --------------------------------------------------------------
    stat_topics: 'مواضيع معتمدة',
    stat_topics_meta: 'صفحات ريتاج عامة موافق عليها',
    stat_pending: 'قيد المراجعة',
    stat_pending_meta: 'صفحات مرشحة بانتظار الموافقة',
    stat_destinations: 'وجهات تنقّل',
    stat_destinations_meta: 'روابط ريتاج معتمدة للفتح',
    stat_corpus: 'نسخة المحتوى',
    stat_corpus_none: 'لا توجد',
    stat_corpus_meta_none: 'لم تُنشر نسخة بعد',
    unit_topic: 'موضوع',
    unit_page: 'صفحة',
    unit_destination: 'وجهة',

    // --- topics panel -------------------------------------------------------
    topics_eyebrow: 'مأخوذة من ritaj.birzeit.edu فقط',
    topics_title: 'ما يمكنني الإجابة عنه',
    topics_empty_title: 'لم تُنشر أي مصادر بعد',
    topics_empty_body: 'لم تُعتمد أي صفحة من ريتاج حتى الآن، لذلك سيمتنع المساعد عن الإجابة بدل التخمين. هذه ليست عطلاً — إنها السلوك المقصود إلى أن يوافق أصحاب المحتوى على الصفحات.',
    topics_none_matching: 'لا توجد مواضيع مطابقة لبحثك.',
    topics_refresh: 'يُراجع',
    topics_stale: 'يحتاج تحديثاً',
    topics_open: 'فتح الصفحة',
    topics_pending_note: 'صفحة مرشحة بانتظار موافقة صاحب المحتوى',
    topics_pending_note_plural: 'صفحات مرشحة بانتظار موافقة أصحابها',

    // --- ask panel ----------------------------------------------------------
    ask_eyebrow: 'أمثلة على أسئلة ضمن النطاق',
    ask_title: 'جرّب أن تسأل',
    ask_hint: 'اضغط أي سؤال لبدء محادثة.',
    ask_abstain_note: 'بما أنه لا توجد مصادر منشورة بعد، سيمتنع المساعد عن الإجابة ويحيلك إلى الدائرة المختصة.',
    suggestions: [
      'كيف أسجل المساقات؟',
      'أين أجد التقويم الأكاديمي؟',
      'ما هي تعليمات التسجيل؟',
      'كيف أفتح لوحات الإعلانات؟',
    ],

    // --- limits panel -------------------------------------------------------
    limits_eyebrow: 'حدود واضحة، بالتصميم',
    limits_title: 'ما لا أستطيع فعله',
    limit_records: 'لا أطّلع على سجلك الشخصي',
    limit_records_body: 'العلامات، المعدل، الجدول، والرصيد المالي — لا وصول لي إليها إطلاقاً. راجعها بنفسك بعد تسجيل الدخول إلى ريتاج.',
    limit_signin: 'لا أسجّل الدخول نيابة عنك',
    limit_signin_body: 'لا أطلب كلمة مرورك ولا أستخدمها، ولا أنفّذ أي إجراء داخل حسابك.',
    limit_links: 'لا أخترع الروابط',
    limit_links_body: 'أفتح فقط وجهات ريتاج مراجَعة مسبقاً، وبعد ضغطك على الزر — لا انتقال تلقائي.',
    limit_guess: 'لا أخمّن عند غياب المصدر',
    limit_guess_body: 'إن لم تدعم صفحةٌ معتمدة الإجابة، أقول إنني لا أعرف وأحيلك إلى دائرة التسجيل والقبول أو المالية.',

    // --- navigation panel ---------------------------------------------------
    nav_eyebrow: 'روابط مراجَعة مسبقاً',
    nav_title: 'الانتقال إلى ريتاج',
    nav_empty_title: 'لم تُعتمد أي وجهة بعد',
    nav_empty_body: 'لن يفتح المساعد أي صفحة حتى يوافق مسؤول الخدمة على وجهتها. حتى ذلك الحين افتح ريتاج بنفسك.',
    nav_pending: 'وجهة بانتظار الموافقة',
    nav_pending_plural: 'وجهات بانتظار الموافقة',
    nav_auth: 'تحتاج تسجيل دخول',
    nav_confirm: 'يُفتح بعد ضغطك فقط',

    // --- status -------------------------------------------------------------
    status_title: 'حالة الخدمة',
    status_eyebrow: 'مأخوذة مباشرة من الخادم',
    status_ready: 'جاهز للإجابة',
    status_not_ready: 'غير جاهز — لا مصادر منشورة',
    status_unreachable: 'تعذّر الوصول إلى الخدمة',
    status_loading: 'جارٍ التحقق...',
    status_corpus_version: 'نسخة المحتوى',
    status_documents: 'المستندات',
    status_chunks: 'المقاطع',
    status_none: 'لا يوجد',
    status_retry: 'إعادة المحاولة',
    status_abstain_note: 'عندما لا تكون هناك مصادر منشورة، يمتنع المساعد عن الإجابة. هذا هو السلوك المقصود.',

    // --- misc ---------------------------------------------------------------
    footer_note: 'مشروع طلابي مستقل في جامعة بيرزيت. المعلومات الرسمية مصدرها ريتاج والدوائر المختصة.',
    composer_placeholder: 'اسأل عن التسجيل، التقويم الأكاديمي، أو خدمات ريتاج...',
    composer_note: 'يجيب من صفحات ريتاج العامة فقط، ولا يطّلع على سجلك الجامعي. للأمور الشخصية راجع الدائرة المختصة.',
    greeting: 'أهلاً بك',
    today: 'اليوم',

    // --- aria ---------------------------------------------------------------
    aria_lang: 'English',
    aria_open_chats: 'فتح المحادثات',
    aria_close_chats: 'إغلاق المحادثات',
    aria_back_home: 'العودة للرئيسية',
    aria_toggle_theme: 'تبديل المظهر',
    aria_status: 'حالة الخدمة',
    aria_close_panel: 'إغلاق اللوحة',
    aria_write: 'اكتب سؤالك',
    aria_send: 'إرسال',
    aria_copy: 'نسخ',
    aria_overview: 'مساعد رتاج',
    aria_brand: 'رتاج',
    aria_menu: 'القائمة',
    aria_sidebar: 'التنقل الرئيسي',
    img_alt: 'بوابة أكاديمية تحيط بها رموز الدراسة والتقويم والتخرج',
  },
  en: {
    dir: 'ltr' as const,

    // --- identity -----------------------------------------------------------
    assistant_name: 'Ritaj Assistant',
    assistant_status: 'Reads public Ritaj pages',
    verified: 'Answers carry sources',
    thinking: 'Searching the approved pages',
    new_chat: 'New chat',
    error_connect: "Couldn't reach the assistant right now. Please try again.",
    error_codes: {
      NO_CORPUS: 'Factual answers are switched off: no approved Ritaj sources have been published yet. The page finder still works.',
      NOT_READY: 'The assistant is temporarily unavailable. Try again shortly.',
      INITIALIZING: 'The assistant is starting up. Try again in a moment.',
      RATE_LIMITED: "You're sending messages too quickly. Wait a moment and try again.",
      LLM_BUDGET_EXHAUSTED: "The assistant has reached today's usage limit. Try again tomorrow, or open the Ritaj page directly.",
      LLM_UNAVAILABLE: 'The answering service is unavailable right now. Try again shortly.',
      LLM_TIMEOUT: 'That took too long. Try again, or ask a shorter question.',
      BUSY: 'The assistant is busy right now. Try again shortly.',
      REQUEST_TOO_LARGE: 'That message is too long. Please shorten it.',
      // Transport failures — the request never reached the service, or never
      // came back. Each says what is actually known, and what to do about it.
      OFFLINE: 'Your device is offline. The page finder still works without a connection.',
      TIMEOUT: 'The server took too long to respond. It may be starting up — try again in a minute.',
      UNREACHABLE: "Couldn't reach the server. Your connection works (you loaded this page over it), so the server is most likely down or restarting. The browser does not reveal the exact cause.",
      STARTING_OR_ASLEEP: 'The service is starting up, or was asleep. The first request takes about a minute.',
      GATEWAY: 'The hosting platform could not reach the app — usually a redeploy in progress. Try again in a minute.',
      HTTP_ERROR: 'The server replied with an unexpected error.',
      UNKNOWN: 'The request failed for an unrecognised reason.',
    } as Record<string, string>,
    error_reference: 'Reference',
    unofficial: 'An independent student project — not an official Birzeit University service',

    search_chats: 'Search conversations',
    recent_label: 'This session',
    no_chats: 'No conversations in this session yet.',
    manage_history: 'Clear this session',
    untitled_chat: 'New chat',

    // --- shell / navigation -------------------------------------------------
    brand_name: 'Ritaj',
    brand_sub: 'Student Assistant',
    portal_label: 'Student Assistant',
    nav_group_about: 'About the assistant',
    view_home: 'Home',
    view_ask: 'Ask the assistant',
    view_topics: 'What I can answer',
    view_open: 'Open in Ritaj',
    view_status: 'Service status',
    view_privacy: 'Privacy',
    search_placeholder: 'Search approved topics...',

    // --- hero ---------------------------------------------------------------
    hero_eyebrow: 'Built on public Ritaj sources',
    hero_h1: 'Ask, and get the source with the answer',
    hero_p: 'The assistant answers only from approved public Ritaj pages, and names the page it used. When no source supports an answer, it says so instead of guessing.',
    hero_cta: 'Ask a question',
    hero_secondary: 'What can it answer?',

    // --- stats --------------------------------------------------------------
    stat_topics: 'Approved topics',
    stat_topics_meta: 'Public Ritaj pages signed off',
    stat_pending: 'In review',
    stat_pending_meta: 'Candidate pages awaiting approval',
    stat_destinations: 'Navigation destinations',
    stat_destinations_meta: 'Reviewed Ritaj links it may open',
    stat_corpus: 'Corpus version',
    stat_corpus_none: 'None',
    stat_corpus_meta_none: 'Nothing published yet',
    unit_topic: 'topic',
    unit_page: 'page',
    unit_destination: 'destination',

    // --- topics panel -------------------------------------------------------
    topics_eyebrow: 'From ritaj.birzeit.edu only',
    topics_title: 'What I can answer',
    topics_empty_title: 'No sources published yet',
    topics_empty_body: 'No Ritaj page has been approved yet, so the assistant abstains rather than guessing. That is not a fault — it is the intended behaviour until content owners sign the pages off.',
    topics_none_matching: 'No topics match your search.',
    topics_refresh: 'Re-checked',
    topics_stale: 'Needs a refresh',
    topics_open: 'Open the page',
    topics_pending_note: 'candidate page awaiting its content owner’s approval',
    topics_pending_note_plural: 'candidate pages awaiting their owners’ approval',

    // --- ask panel ----------------------------------------------------------
    ask_eyebrow: 'Examples of in-scope questions',
    ask_title: 'Try asking',
    ask_hint: 'Pick one to start a conversation.',
    ask_abstain_note: 'With no sources published yet, the assistant will abstain and point you to the relevant office.',
    suggestions: [
      'How do I register for courses?',
      'Where is the academic calendar?',
      'What are the registration instructions?',
      'How do I open the message boards?',
    ],

    // --- limits panel -------------------------------------------------------
    limits_eyebrow: 'Limits, by design',
    limits_title: 'What I cannot do',
    limit_records: 'I cannot see your record',
    limit_records_body: 'Grades, GPA, schedule and balance are out of reach entirely. Sign in to Ritaj yourself to see them.',
    limit_signin: 'I cannot sign in for you',
    limit_signin_body: 'I never ask for or use your password, and I take no action inside your account.',
    limit_links: 'I do not invent links',
    limit_links_body: 'I open only pre-reviewed Ritaj destinations, and only after you click — never automatically.',
    limit_guess: 'I do not guess without a source',
    limit_guess_body: 'If no approved page supports the answer, I say I do not know and point you to Registration & Admission or Finance.',

    // --- navigation panel ---------------------------------------------------
    nav_eyebrow: 'Pre-reviewed links',
    nav_title: 'Open in Ritaj',
    nav_empty_title: 'No destination approved yet',
    nav_empty_body: 'The assistant will not open any page until a service owner approves its destination. Until then, open Ritaj yourself.',
    nav_pending: 'destination awaiting approval',
    nav_pending_plural: 'destinations awaiting approval',
    nav_auth: 'Sign-in required',
    nav_confirm: 'Opens only when you click',

    // --- status -------------------------------------------------------------
    status_title: 'Service status',
    status_eyebrow: 'Read straight from the server',
    status_ready: 'Ready to answer',
    status_not_ready: 'Not ready — no sources published',
    status_unreachable: "Can't reach the service",
    status_loading: 'Checking...',
    status_corpus_version: 'Corpus version',
    status_documents: 'Documents',
    status_chunks: 'Chunks',
    status_none: 'None',
    status_retry: 'Try again',
    status_abstain_note: 'With no corpus published, the assistant abstains. That is the intended behaviour.',

    // --- misc ---------------------------------------------------------------
    footer_note: 'An independent student project at Birzeit University. Official information comes from Ritaj and the relevant offices.',
    composer_placeholder: 'Ask about registration, the academic calendar, or Ritaj services...',
    composer_note: 'Answers come from public Ritaj pages only; it cannot see your student record. For anything personal, contact the relevant office.',
    greeting: 'Welcome',
    today: 'Today',

    // --- aria ---------------------------------------------------------------
    aria_lang: 'العربية',
    aria_open_chats: 'Open conversations',
    aria_close_chats: 'Close conversations',
    aria_back_home: 'Back to home',
    aria_toggle_theme: 'Toggle theme',
    aria_status: 'Service status',
    aria_close_panel: 'Close panel',
    aria_write: 'Type your question',
    aria_send: 'Send',
    aria_copy: 'Copy',
    aria_overview: 'Ritaj Assistant',
    aria_brand: 'Ritaj',
    aria_menu: 'Menu',
    aria_sidebar: 'Main navigation',
    img_alt: 'An academic portal surrounded by study, calendar, and graduation icons',
  },
}

type Direction = 'rtl' | 'ltr'
// Widen `dir` so both languages share one shape (ar→rtl, en→ltr).
export type Strings = Omit<typeof dict['ar'], 'dir'> & { dir: Direction }

type Ctx = { lang: Lang; setLang: (l: Lang) => void; s: Strings }
export const LangContext = createContext<Ctx>({ lang: 'ar', setLang: () => {}, s: dict.ar })
export const useI18n = () => useContext(LangContext)
