import type { PageLink, TeamImage } from '../../api/chat'

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  time: string
  type?: 'registration'
  links?: PageLink[]
  images?: TeamImage[]
}

export const initialMessages: ChatMessage[] = [
  {
    id: 1,
    role: 'assistant',
    content: 'أهلاً براء، أنا مساعد رتاج الأكاديمي. أستطيع قراءة جدولك وخطتك وسجلك المالي لمساعدتك في اتخاذ الخطوة التالية.',
    time: '10:24',
  },
  {
    id: 2,
    role: 'user',
    content: 'هل أنا جاهز للتسجيل في الدورة الصيفية؟ وما المساقات التي تقترحها؟',
    time: '10:25',
  },
  {
    id: 3,
    role: 'assistant',
    content: 'أنت قريب من الجاهزية. راجعت خطتك الحالية وموعد تسجيلك، وهذه أهم النقاط قبل أن تبدأ:',
    time: '10:25',
    type: 'registration',
  },
]

export const suggestions = [
  'لخّص وضعي الأكاديمي',
  'متى امتحاني القادم؟',
  'ما المتبقي من خطتي؟',
  'اشرح رصيدي المالي',
]

export const recentChats = [
  { title: 'التسجيل للدورة الصيفية', time: 'الآن', active: true },
  { title: 'متطلبات التخرج المتبقية', time: 'أمس' },
  { title: 'موعد امتحان COMP 433', time: '18 حزيران' },
  { title: 'تفاصيل السجل المالي', time: '12 حزيران' },
]

export function answerFor(message: string): ChatMessage {
  const normalized = message.toLowerCase()
  let content = 'بحسب سجلك الحالي، أنت مسجل في 5 مساقات وأنجزت 108 ساعات من أصل 132. يمكنني تفصيل الخطة أو الجدول أو السجل المالي إذا حددت ما تريد مراجعته.'

  if (normalized.includes('امتحان') || normalized.includes('موعد')) {
    content = 'امتحانك القادم هو هندسة البرمجيات COMP 433 يوم 29 حزيران الساعة 09:00 صباحاً. أنصحك بمراجعة تعليمات القاعة قبل الموعد بيوم.'
  } else if (normalized.includes('مالي') || normalized.includes('رصيد')) {
    content = 'يوجد رصيد مستحق بقيمة 240 د.أ. يجب تسويته قبل بدء تسجيل الدورة الصيفية. يمكنك فتح السجل المالي لمعرفة تفاصيل الحركات والدفعات.'
  } else if (normalized.includes('خطة') || normalized.includes('متبقي') || normalized.includes('تخرج')) {
    content = 'أنجزت 108 من أصل 132 ساعة. المتبقي 24 ساعة تشمل متطلبات التخصص ومشروع التخرج. سأرتبها لك حسب الأولوية والمتطلبات السابقة.'
  }

  return { id: Date.now() + 1, role: 'assistant', content, time: new Date().toLocaleTimeString('ar', { hour: '2-digit', minute: '2-digit' }) }
}
