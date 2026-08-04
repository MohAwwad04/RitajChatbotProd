# Privacy Policy — Ritaj Assistant

**Chrome extension & web chatbot for Birzeit University student services · Effective 6 July 2026**

> العربية أدناه (Arabic version below).

## What the assistant is

Ritaj Assistant answers questions about Birzeit University and the Ritaj portal
(registration, fees, grades, deadlines, IT help) in Arabic or English. It is an
independent student project and is not an official Birzeit University product.
It requires no account and no sign-in.

## What is sent to our server

When you send a message, the extension (or the web portal) transmits to our
backend at `mohawwad04-ritaj-rag.hf.space`:

- the question you typed;
- the recent turns of the current conversation, so follow-up questions make sense;
- a random session identifier (a UUID generated locally — it identifies the
  conversation, not you) and a client tag ("extension" or "portal").

Nothing else is collected: no name, no email, no student ID, no browsing
history, no page content, no location, no cookies, no advertising or analytics
trackers.

## How your message is processed

The server searches a knowledge base of public Birzeit University information
and sends your question plus the retrieved passages to a third-party
language-model provider, [Groq](https://groq.com), to compose the answer text.
Groq receives only the conversation content — never any identifier of you or
your device beyond what any internet request carries.

## Logging and retention

Questions and answers (with their random session id) may be logged on the
server so we can monitor answer quality. These logs live in temporary storage
that is erased whenever the server restarts or is rebuilt; they are not backed
up, shared, or used for anything except improving the assistant. Please do not
type passwords or personal information into the chat.

## What stays on your device

Your chat history and language preference are stored locally with
`chrome.storage.local` so the conversation survives closing the popup. They
never leave your browser except as the "recent turns" described above. Press ↺
(new chat) to erase the conversation, or uninstall the extension to remove
everything.

## What we don't do

- We do not sell, rent, or share your data with anyone.
- We do not use your data for advertising, profiling, or creditworthiness.
- The extension loads no remote code (Manifest V3 compliant) and talks to
  exactly one host: our own backend.

## Changes and contact

If this policy changes, the update will be posted at this address with a new
effective date. Questions: moh.awwad243@gmail.com.

---

# سياسة الخصوصية — مساعد ريتاج

**امتداد كروم وروبوت محادثة لخدمات طلبة جامعة بيرزيت · سارية اعتباراً من 6 تموز 2026**

## ما هو المساعد

مساعد ريتاج يجيب عن الأسئلة حول جامعة بيرزيت وبوابة ريتاج (التسجيل، الرسوم،
العلامات، المواعيد، الدعم الفني) بالعربية أو الإنجليزية. وهو مشروع طلابي مستقل
وليس منتجاً رسمياً لجامعة بيرزيت، ولا يتطلب أي حساب أو تسجيل دخول.

## ما الذي يُرسل إلى خادمنا

عند إرسال رسالة، يرسل الامتداد (أو البوابة) إلى خادمنا على
`mohawwad04-ritaj-rag.hf.space`:

- السؤال الذي كتبته؛
- الرسائل الأخيرة من المحادثة الحالية كي تُفهم أسئلة المتابعة؛
- معرّف جلسة عشوائي (يُنشأ محلياً ويعرّف المحادثة لا شخصك) ووسم العميل.

لا يُجمع أي شيء آخر: لا اسم، لا بريد إلكتروني، لا رقم جامعي، لا سجل تصفح، لا
محتوى صفحات، لا موقع جغرافي، لا ملفات تعريف ارتباط، ولا أدوات تتبع إعلانية أو
تحليلية.

## كيف تُعالج رسالتك

يبحث الخادم في قاعدة معرفية من معلومات جامعة بيرزيت العامة، ثم يرسل سؤالك مع
المقاطع المسترجعة إلى مزوّد نماذج لغوية خارجي هو [Groq](https://groq.com)
لصياغة نص الإجابة. لا يتلقى Groq سوى محتوى المحادثة — دون أي معرّف لك أو
لجهازك.

## السجلات ومدة الاحتفاظ

قد تُسجَّل الأسئلة والإجابات (مع معرّف الجلسة العشوائي) على الخادم لمراقبة جودة
الإجابات. تُحفظ هذه السجلات في تخزين مؤقت يُمسح عند كل إعادة تشغيل أو إعادة بناء
للخادم، ولا تُنسخ احتياطياً ولا تُشارك ولا تُستخدم إلا لتحسين المساعد. الرجاء
عدم كتابة كلمات سر أو معلومات شخصية في المحادثة.

## ما يبقى على جهازك

يُخزَّن سجل المحادثة وتفضيل اللغة محلياً عبر `chrome.storage.local` كي تبقى
المحادثة بعد إغلاق النافذة، ولا يغادران متصفحك إلا ضمن «الرسائل الأخيرة»
المذكورة أعلاه. اضغط ↺ (محادثة جديدة) لمسح المحادثة، أو أزل الامتداد لحذف كل
شيء.

## ما لا نفعله

- لا نبيع بياناتك ولا نؤجرها ولا نشاركها مع أي جهة.
- لا نستخدم بياناتك للإعلانات أو التنميط أو تقييم الجدارة الائتمانية.
- لا يحمّل الامتداد أي شيفرة عن بُعد (متوافق مع Manifest V3) ويتصل بمضيف واحد
  فقط: خادمنا.

## التغييرات والتواصل

إذا تغيّرت هذه السياسة فسيُنشر التحديث على هذا العنوان مع تاريخ سريان جديد.
للاستفسارات: moh.awwad243@gmail.com.
