// GENERATED FILE — do not edit by hand.
//
// Written by scripts/sync_extension_actions.py from data/navigation.yaml, and
// checked by scripts/check_extension.py, which fails the build if this file and
// the registry disagree.
//
// This is the extension's offline copy of the reviewed destinations. It is what
// makes the page-finder work when the backend is unreachable — asleep, mid
// redeploy, or deliberately `not-ready` because no corpus has been approved yet.
// When the network IS available the panel prefers /v2/navigation/actions, so a
// destination can be withdrawn server-side without waiting for a Store review.
//
// Only approved, enabled actions appear here. Every URL in this file is still
// validated by navigation.js before chrome.tabs.create() is called: a generated
// file is not a trusted file, and the point of the client-side check is that it
// does not trust its own inputs either.
//
// 4 approved destinations.

export const REGISTRY_VERSION = '60b6d601f739'

export const BUNDLED_ACTIONS = [
    {
      "id": "academic-calendar",
      "label_ar": "فتح التقويم الأكاديمي",
      "label_en": "Open the academic calendar",
      "url": "https://ritaj.birzeit.edu/academic-calendar",
      "auth_required": false,
      "requires_confirmation": true,
      "intents_ar": [
        "افتح التقويم الاكاديمي",
        "صفحه التقويم الاكاديمي",
        "اعرض التقويم"
      ],
      "intents_en": [
        "open the academic calendar",
        "show me the academic calendar",
        "go to the calendar page"
      ],
      "min_confidence": 0.75
    },
    {
      "id": "course-registration",
      "label_ar": "فتح تسجيل المساقات",
      "label_en": "Open course registration",
      "url": "https://ritaj.birzeit.edu/reg/",
      "auth_required": true,
      "requires_confirmation": true,
      "intents_ar": [
        "افتح تسجيل المساقات",
        "صفحه التسجيل",
        "اذهب الى التسجيل",
        "وين اسجل المساقات",
        "بدي انزل مساقات"
      ],
      "intents_en": [
        "open course registration",
        "go to registration",
        "open the registration page",
        "where do i register for courses",
        "take me to course registration"
      ],
      "min_confidence": 0.75
    },
    {
      "id": "message-boards",
      "label_ar": "فتح لوحات الإعلانات",
      "label_en": "Open the message boards",
      "url": "https://ritaj.birzeit.edu/bzu-msgs/boards",
      "auth_required": true,
      "requires_confirmation": true,
      "intents_ar": [
        "افتح لوحات الاعلانات",
        "اعرض الاعلانات",
        "افتح اللوحات"
      ],
      "intents_en": [
        "open the message boards",
        "show announcements",
        "open the boards"
      ],
      "min_confidence": 0.8
    },
    {
      "id": "ritaj-home",
      "label_ar": "فتح بوابة ريتاج",
      "label_en": "Open the Ritaj portal",
      "url": "https://ritaj.birzeit.edu/",
      "auth_required": true,
      "requires_confirmation": true,
      "intents_ar": [
        "افتح ريتاج",
        "اذهب الى ريتاج",
        "افتح بوابه ريتاج"
      ],
      "intents_en": [
        "open ritaj",
        "go to ritaj",
        "open the ritaj portal"
      ],
      "min_confidence": 0.9
    }
  ]
