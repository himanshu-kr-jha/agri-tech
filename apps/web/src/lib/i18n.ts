/**
 * Interface strings, in the two languages this product is read in.
 *
 * Hand-written rather than machine-translated, and hand-written rather than pulled from a
 * library: the surface is one route group plus the sign-in page, and every string here was
 * already written bilingually somewhere in the tree — this file is where the two halves were
 * separated, not where the Hindi was invented.
 *
 * What is deliberately *not* here: the text of a government order. That is data, it is
 * canonical in Hindi (ADR-0015), and it reaches the page from the API with its own
 * `text_hi` / `text_en` pair. A translation table is the wrong home for a legal document.
 *
 * Keys are dotted and grouped by surface. `mypy`'s equivalent here is the `StringKey` union:
 * a key that does not exist is a compile error, and a key missing one language is too.
 */

import type { Locale } from "@/lib/locale";

type Entry = { en: string; hi: string };

export const STRINGS = {
  // --------------------------------------------------------------- shell
  "nav.myFarm": { en: "My farm", hi: "मेरा खेत" },
  "nav.ask": { en: "Ask", hi: "पूछिए" },
  "nav.notices": { en: "Notices", hi: "सूचनाएँ" },
  "nav.signOut": { en: "Sign out", hi: "साइन आउट" },
  "lang.switchTo": { en: "हिन्दी", hi: "English" },
  "lang.label": { en: "Switch to Hindi", hi: "Switch to English" },

  // --------------------------------------------------------------- today
  "today.myCrops": { en: "My crops", hi: "मेरी फ़सल" },
  "today.noCrop": { en: "No crop currently growing.", hi: "कोई चालू फ़सल नहीं।" },
  "today.acres": { en: "acres", hi: "एकड़" },
  "today.cropHealth": { en: "Crop health", hi: "फ़सल की स्थिति" },
  "today.noVisit": { en: "No field visit recorded yet.", hi: "अभी तक कोई जाँच नहीं।" },
  "today.expectedHarvest": { en: "Expected harvest", hi: "कटाई" },
  "today.givenToCollective": { en: "Given to the collective", hi: "समिति को दिया" },
  "today.grade": { en: "Grade", hi: "श्रेणी" },
  "today.unreachable": {
    en: "Could not reach the API. Run `make api`, and set AGRI_DEV_TOKEN to a farmer token to see this view.",
    hi: "जानकारी नहीं मिल सकी। कृपया बाद में देखें।",
  },

  // --------------------------------------------------------------- ask
  "ask.title": { en: "Ask", hi: "पूछिए" },
  "ask.intro": {
    en: "Ask about your own farm. Answers come from what is recorded about your plots and crops, and every one shows where it came from.",
    hi: "अपने खेत के बारे में पूछिए। उत्तर आपके खेत और फ़सल के दर्ज विवरण से आते हैं, और हर उत्तर अपना स्रोत दिखाता है।",
  },
  "ask.placeholder": { en: "How is my crop?", hi: "मेरी फसल कैसी है?" },
  "ask.loading": { en: "Loading…", hi: "लोड हो रहा है…" },
  //: Shown on the assistant page in the reader's own language, explaining why the rest of
  //: that page is not. See the note in (farmer)/ask/page.tsx.
  "ask.englishOnly": {
    en: "The assistant answers in English.",
    hi: "सहायक अंग्रेज़ी में उत्तर देता है। प्रश्न आप हिन्दी में भी पूछ सकते हैं।",
  },
  "ask.example.yield": {
    en: "How can I increase the yield of my crops?",
    hi: "मैं अपनी फ़सल की पैदावार कैसे बढ़ाऊँ?",
  },
  "ask.example.today": {
    en: "What should I do on my farm today?",
    hi: "आज मुझे अपने खेत में क्या करना चाहिए?",
  },
  "ask.example.schemes": {
    en: "What schemes may apply to me?",
    hi: "मुझ पर कौन सी योजनाएँ लागू हो सकती हैं?",
  },
  "ask.example.shared": {
    en: "What has the FPO shared with members?",
    hi: "समिति ने सदस्यों को क्या बताया है?",
  },

  // --------------------------------------------------------------- notices
  "notices.title": { en: "Government notices", hi: "सरकारी सूचनाएँ" },
  "notices.intro": {
    en: "Orders and guidance published by the UP Agriculture Department, shown exactly as published.",
    hi: "कृषि विभाग, उत्तर प्रदेश द्वारा प्रकाशित शासनादेश एवं जानकारी — जैसा प्रकाशित हुआ, वैसा ही।",
  },
  "notices.department": { en: "UP Agriculture Dept", hi: "कृषि विभाग, उत्तर प्रदेश" },
  "notices.search": { en: "Search", hi: "खोजें" },
  "notices.searchPlaceholder": { en: "crop insurance", hi: "फसल बीमा" },
  "notices.inert": {
    en: "General departmental guidance, not confirmation of any benefit.",
    hi: "यह विभाग की सामान्य जानकारी है — किसी लाभ की पुष्टि नहीं।",
  },
  "notices.forbidden": {
    en: "This view is for a farmer account.",
    hi: "यह पृष्ठ किसान खाते के लिए है।",
  },
  "notices.unreachable": {
    en: "Could not reach the API. Run `make api`.",
    hi: "जानकारी नहीं मिल सकी।",
  },
  "notices.none": {
    en: "The department has not published anything on this. That is a real answer — this page searches only what the government has actually issued, and invents nothing.",
    hi: "इस विषय पर विभाग ने कुछ प्रकाशित नहीं किया है। यह पृष्ठ केवल वही खोजता है जो सरकार ने वास्तव में जारी किया है।",
  },
  "notices.recent": { en: "Recent notices", hi: "हाल की सूचनाएँ" },
  "notices.countSuffix": { en: "notices", hi: "सूचनाएँ" },
  "notices.yourCrops": { en: "Your crops", hi: "आपकी फ़सलें" },
  "notices.departmentWideWithCrops": {
    en: "These notices are department-wide — none of them names a specific crop, so none is matched to your farm.",
    hi: "ये सूचनाएँ पूरे विभाग के लिए हैं — किसी एक फ़सल के लिए नहीं।",
  },
  "notices.departmentWide": {
    en: "These notices are department-wide.",
    hi: "ये सूचनाएँ पूरे विभाग के लिए हैं।",
  },
  "notices.disclaimer": {
    en: "This page does not tell you whether you qualify for anything. It shows what was published and when. Confirm eligibility and deadlines at your block office — saying you qualify when you might not would do real harm.",
    hi: "यह पृष्ठ यह नहीं बताता कि आप किसी योजना के पात्र हैं या नहीं। पात्रता एवं अंतिम तिथि की पुष्टि अपने विकास खंड कार्यालय या कृषि रक्षा इकाई से करें।",
  },
  "notices.originalHindi": {
    en: "Shown in the published Hindi because no English rendering is on record.",
    hi: "जैसा प्रकाशित हुआ।",
  },

  // --------------------------------------------------------------- sign-in
  "login.accounts": { en: "Sign in as", hi: "इस रूप में साइन इन करें" },
  "login.username": { en: "Username", hi: "उपयोगकर्ता नाम" },
  "login.password": { en: "Password", hi: "पासवर्ड" },
  "login.signIn": { en: "Sign in", hi: "साइन इन करें" },
  "login.signingIn": { en: "Signing in…", hi: "साइन इन हो रहा है…" },
  "login.failed": { en: "Could not reach the server.", hi: "सर्वर से संपर्क नहीं हो सका।" },
  "login.accountsHint": {
    en: "Sign in as each to see the same system from both sides. What a member can reach is enforced by the API, not by hiding pages.",
    hi: "दोनों दृष्टिकोणों से एक ही प्रणाली देखने के लिए बारी-बारी से साइन इन करें। कोई सदस्य क्या देख सकता है, यह API तय करता है — पृष्ठ छिपाकर नहीं।",
  },
  "login.tagline": {
    en: "Decision support that recommends, never decides. Sign in to continue.",
    hi: "निर्णय में सहायता — सुझाव देता है, निर्णय कभी नहीं। जारी रखने के लिए साइन इन करें।",
  },
  "login.eyebrow": { en: "Farmer collectives", hi: "किसान उत्पादक संगठन" },
  "login.audience.fpo": { en: "Organization console", hi: "संगठन कंसोल" },
  "login.audience.farmer": { en: "Farmer view", hi: "किसान दृश्य" },
} as const satisfies Record<string, Entry>;

export type StringKey = keyof typeof STRINGS;

/** Bind a locale once, at the top of a Server Component, and pass `t` down. */
export function translator(locale: Locale): (key: StringKey) => string {
  return (key) => STRINGS[key][locale];
}

/** The five canned searches on the notices page, in the reader's language. */
export const NOTICE_SUGGESTIONS: { en: string; hi: string }[] = [
  { en: "crop insurance", hi: "फसल बीमा" },
  { en: "soil sample", hi: "मृदा नमूना" },
  { en: "fertiliser subsidy", hi: "उर्वरक अनुदान" },
  { en: "irrigation", hi: "सिंचाई" },
  { en: "seed", hi: "बीज" },
];
