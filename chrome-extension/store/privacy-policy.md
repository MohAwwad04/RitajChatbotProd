# Privacy policy — Ritaj Assistant

**Last updated:** 4 August 2026
**Applies to:** the Ritaj Assistant Chrome extension and the web version at
`mohawwad04-ritaj-rag.hf.space`.

> العربية أدناه (Arabic version below).

Ritaj Assistant is an **independent student project**. It is not an official
Birzeit University product and is not endorsed by Birzeit University.

This policy describes what actually happens, checked against the code. Where a
behaviour is a limitation rather than a promise, it says so.

---

## 1. What is sent to our server

When you send a message, the extension sends:

- the text you typed;
- up to the last 8 turns of the current conversation, so follow-up questions
  make sense;
- a random session id generated in your browser, which groups one conversation's
  turns. It is not derived from anything about you, and it is replaced when you
  start a new chat or clear history;
- the language you have selected (`ar` or `en`);
- the label `chrome-extension`, so we can tell extension traffic from web traffic.

**Nothing else.** In particular the extension does **not** send the page you are
viewing, its URL, its title, its content, your cookies, your login session, your
form entries, your student id, or your browsing history. It has no permission to
read any of those — see §6.

The web version sends the same fields with a different client label.

## 2. Who processes your message

To compose an answer, your message and the retrieved Ritaj document excerpts are
sent to **Cloudflare Workers AI**, which runs the Google Gemma 4 language model.
Cloudflare receives the conversation content and nothing that identifies you —
no name, no student id, no session id, and no IP address from us.

Cloudflare's handling of that data is governed by their terms, not ours.

*(An earlier version of this policy named Groq. The provider changed; this
document is the current one.)*

## 3. What is stored on your device

Your conversation and language preference are stored in `chrome.storage.local`,
on your computer. It never syncs to a Google account, and we cannot read it.

It is capped at 40 turns or roughly 120 KB, whichever comes first; older turns
are dropped past that.

**Delete it at any time** with the 🗑 button in the panel, or by removing the
extension. That erases it immediately and completely.

## 4. What is stored on our server

By default the server keeps **aggregate operational records only**:

- when a request happened, and how long it took;
- whether the answer was grounded, repaired, refused or abstained;
- which approved Ritaj documents were used;
- an error code if something failed;
- the random session id and the client label;
- the *length* of your question and answer, not their text.

**The text of your questions and answers is not stored** in this mode.

Server logs record a coarsened form of your IP address (e.g. `192.0.x.x`) for
abuse control and rate limiting, plus a random per-request id. Identifiers such
as student ids, emails and phone numbers are masked before anything is written.

Records are deleted after **30 days**.

### If raw conversations are ever stored

A "full" logging mode exists for a supervised pilot. It would store redacted
conversation text. It is **off**, and turning it on requires a clear in-product
opt-in and a stated retention period first. If you were not asked, it is not on.

## 5. Opening Ritaj pages

Some answers offer a button such as **Open course registration**. If you press
it, the extension opens that page in a tab.

- The destination comes from a **fixed, human-reviewed list** of
  `ritaj.birzeit.edu` addresses. The language model cannot produce a URL; the
  most it can do is name an entry that already exists on that list.
- The extension checks the address itself before opening it — correct scheme,
  exactly the host `ritaj.birzeit.edu`, and a registered path.
- Nothing happens without your click.
- Once the page is open, the extension **does not read it, fill it, click
  anything in it, or submit anything**. If Ritaj asks you to sign in, that is
  between you and Ritaj; we never see your password or your session.

The assistant cannot register you for a course, drop one, pay a fee, or submit
any form. It refuses and offers to open the relevant page instead.

## 6. Permissions, and why each exists

| Permission | Why it is needed |
|---|---|
| `storage` | keeps your conversation and language on your device |
| `sidePanel` | shows the chat in Chrome's side panel when you click the icon |
| access to `mohawwad04-ritaj-rag.hf.space` | our backend — where questions are answered |

The extension does **not** request `tabs`, `activeTab`, `scripting`,
`webNavigation`, `cookies`, `history`, or access to `ritaj.birzeit.edu` itself.
Chrome does not require the `tabs` permission to open a tab, and host access to
Ritaj would let the extension read your Ritaj pages, which it must not.

## 7. Limited Use

Our use of information received from Google APIs adheres to the
[Chrome Web Store User Data Policy](https://developer.chrome.com/docs/webstore/program-policies/limited-use),
including the Limited Use requirements. Specifically:

- data is used **only** to provide the assistant's answering feature;
- it is **not** sold or transferred to third parties, except to the model
  provider in §2 for the sole purpose of composing your answer;
- it is **not** used for advertising, credit assessment, or any purpose
  unrelated to answering your question;
- no human reads your conversations, except where you explicitly opt in to a
  pilot.

**Browsing activity:** the extension collects none. It does not read the URL,
title or content of any page, including Ritaj pages.

## 8. What we do not claim

- We do **not** claim to be private by design, anonymous, or free of data
  collection. Sections 1–4 describe what is transferred and what is kept.
- We do **not** claim answers are always correct. The assistant answers from a
  limited set of approved Ritaj pages, which can be out of date.
- We do **not** claim to be an official Birzeit service.

## 9. Accuracy and disclaimer

Information may change without the assistant knowing. Deadlines, fees and
regulations must be confirmed on Ritaj or with the relevant office — **the
linked Ritaj page is authoritative, not the answer**. The assistant does not
give personalised academic, financial or legal advice, and no decision with
academic or financial consequences should rest on it alone.

Answers show which page each fact came from and when that page was captured. If
a source is past its refresh window, the answer says so.

## 10. Children

The assistant is intended for university students and staff. It is not directed
at children under 13.

## 11. Changes

Material changes appear here with a new "last updated" date, and in the
extension listing before the change ships.

## 12. Contact

Questions, corrections, or a request to delete data:
**ritaj.assistant.project@gmail.com**

To delete everything held about you on your device, press 🗑 in the panel. There
is no server-side account to delete, because we do not create one.

---

# سياسة الخصوصية — مساعد ريتاج

**آخر تحديث:** 4 آب 2026

مساعد ريتاج **مشروع طلابي مستقل**، وليس منتجاً رسمياً لجامعة بيرزيت ولا معتمداً
منها.

## 1. ما يُرسَل إلى خادمنا

عند إرسال رسالة تُرسِل الإضافة: نص رسالتك، وحتى آخر 8 مداخلات من المحادثة الحالية،
ومعرّف جلسة عشوائي يُنشأ في متصفحك لتجميع مداخلات المحادثة الواحدة، واللغة التي
اخترتها.

**ولا شيء غير ذلك.** لا تُرسِل الإضافة الصفحة التي تتصفحها ولا عنوانها ولا محتواها
ولا ملفات تعريف الارتباط ولا جلسة دخولك ولا ما تكتبه في النماذج ولا رقمك الجامعي
ولا سجل تصفحك. ولا تملك أصلاً الصلاحيات اللازمة لقراءة أي من ذلك — انظر البند 6.

## 2. من يعالج رسالتك

لصياغة الإجابة تُرسَل رسالتك ومقاطع من صفحات ريتاج المعتمدة إلى **Cloudflare
Workers AI** الذي يشغّل نموذج Google Gemma 4. يتلقى Cloudflare محتوى المحادثة فقط،
دون أي معرّف لك — لا اسم ولا رقم جامعي ولا معرّف جلسة ولا عنوان IP من طرفنا.

*(كانت نسخة سابقة من هذه السياسة تذكر Groq؛ تغيّر المزوّد، وهذه هي النسخة الحالية.)*

## 3. ما يُخزَّن على جهازك

تُحفظ محادثتك وتفضيل اللغة في `chrome.storage.local` على جهازك فقط، ولا تُزامَن مع
حساب Google، ولا يمكننا قراءتها. الحد الأقصى 40 مداخلة أو نحو 120 كيلوبايت.

**يمكنك حذفها في أي وقت** بزر 🗑 في اللوحة أو بإزالة الإضافة.

## 4. ما يُخزَّن على خادمنا

افتراضياً تُحفظ **سجلات تشغيلية مجمّعة فقط**: وقت الطلب ومدته، ونتيجة التحقق من
الإسناد، والوثائق المعتمدة المستخدَمة، ورمز الخطأ إن وُجد، ومعرّف الجلسة العشوائي،
وطول السؤال والإجابة — **دون نص السؤال أو الإجابة**.

تُسجَّل صيغة مبهمة من عنوان IP (مثل `192.0.x.x`) لمنع إساءة الاستخدام. وتُخفى
المعرّفات مثل الأرقام الجامعية والبريد الإلكتروني والهواتف قبل أي كتابة. وتُحذف
السجلات بعد **30 يوماً**.

## 5. فتح صفحات ريتاج

قد تتضمن بعض الإجابات زراً مثل **فتح تسجيل المساقات**. عند الضغط عليه تُفتح الصفحة
في تبويب جديد.

- الوجهة مختارة من **قائمة ثابتة راجعها إنسان** من عناوين `ritaj.birzeit.edu`.
  لا يستطيع النموذج اللغوي إنتاج رابط؛ أقصى ما يفعله تسمية إدخال موجود مسبقاً.
- تتحقق الإضافة من العنوان بنفسها قبل فتحه.
- لا يحدث شيء دون ضغطك.
- بعد فتح الصفحة **لا تقرأها الإضافة ولا تملؤها ولا تضغط فيها ولا ترسل شيئاً**.
  وإن طلب ريتاج تسجيل الدخول فذلك بينك وبين ريتاج؛ لا نرى كلمة سرك ولا جلستك.

لا يستطيع المساعد تسجيلك في مساق أو حذفه أو دفع رسوم أو إرسال أي طلب؛ سيرفض ذلك
ويعرض عليك فتح الصفحة المناسبة.

## 6. الصلاحيات

`storage` لحفظ المحادثة على جهازك، و`sidePanel` لعرض المحادثة في اللوحة الجانبية،
والوصول إلى `mohawwad04-ritaj-rag.hf.space` وهو خادمنا.

لا تطلب الإضافة `tabs` ولا `activeTab` ولا `scripting` ولا `cookies` ولا `history`
ولا أي وصول إلى `ritaj.birzeit.edu` نفسه.

## 7. ما لا ندّعيه

لا ندّعي أن الخدمة خاصة تماماً أو أنها لا تجمع أي بيانات — البنود 1 إلى 4 تصف ما
يُنقَل وما يُحفظ. ولا ندّعي أن الإجابات صحيحة دائماً: صفحة ريتاج المرتبطة هي المرجع
وليست الإجابة. ولسنا خدمة رسمية من جامعة بيرزيت.

## 8. إخلاء المسؤولية

قد تتغير المعلومات دون أن يعلم المساعد. تأكّد من المواعيد والرسوم والأنظمة على
ريتاج أو من الدائرة المعنية. لا يقدّم المساعد استشارة أكاديمية أو مالية أو قانونية
شخصية، ولا ينبغي أن يُبنى عليه وحده أي قرار له أثر أكاديمي أو مالي.

## 9. التواصل

للأسئلة أو التصحيحات أو طلب حذف البيانات:
**ritaj.assistant.project@gmail.com**
