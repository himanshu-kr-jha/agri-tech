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
import { interfaceCopy, type CopyKey, type CopyValues } from "@/lib/ui-copy";

type Entry = { en: string; hi: string };

export const STRINGS = {
  // --------------------------------------------------------------- shell
  "nav.myFarm": { en: "My farm", hi: "मेरा खेत" },
  "nav.ask": { en: "Ask", hi: "पूछिए" },
  "nav.notices": { en: "Notices", hi: "सूचनाएँ" },
  "nav.signOut": { en: "Sign out", hi: "साइन आउट" },
  "lang.switchTo": { en: "हिन्दी", hi: "English" },
  "lang.label": { en: "Switch to Hindi", hi: "Switch to English" },

  // --------------------------------------------------------------- console
  //: The FPO console. Its *data* stays English — claims, units and refusals are assembled
  //: by deterministic modules that write English, and translating a chrome label does not
  //: change what a finding says. What is here is navigation and page headings: the parts a
  //: reader uses to find their way rather than the parts they act on.
  "con.nav.dashboard": { en: "Dashboard", hi: "डैशबोर्ड" },
  "con.nav.group.decide": { en: "Decide", hi: "निर्णय" },
  "con.nav.assistant": { en: "Ask", hi: "पूछिए" },
  "con.nav.decisions": { en: "Decisions", hi: "निर्णय-सूची" },
  "con.nav.risk": { en: "Risk", hi: "जोखिम" },
  "con.nav.group.collective": { en: "Collective", hi: "समिति" },
  "con.nav.farmers": { en: "Farmers", hi: "किसान" },
  "con.nav.market": { en: "Market", hi: "बाज़ार" },
  "con.nav.discrepancies": { en: "Conflicts", hi: "मतभेद" },
  "con.nav.knowledge": { en: "Published", hi: "प्रकाशित" },
  "con.nav.impact": { en: "Impact", hi: "प्रभाव" },

  "con.dashboard.eyebrow": { en: "FPO Command Centre", hi: "एफ़पीओ कमांड सेंटर" },
  "con.dashboard.title": { en: "Dashboard", hi: "डैशबोर्ड" },
  "con.assistant.eyebrow": { en: "Assistant", hi: "सहायक" },
  "con.assistant.title": { en: "Ask the collective", hi: "समिति से पूछिए" },
  "con.decisions.eyebrow": { en: "Ledger", hi: "बही" },
  "con.decisions.title": { en: "Decisions", hi: "निर्णय" },
  "con.risk.eyebrow": { en: "Exposure", hi: "जोखिम-भार" },
  "con.risk.title": { en: "Risk register", hi: "जोखिम रजिस्टर" },
  "con.farmers.eyebrow": { en: "Membership", hi: "सदस्यता" },
  "con.farmers.title": { en: "Farmers", hi: "किसान" },
  "con.market.eyebrow": { en: "Aggregation", hi: "एकत्रीकरण" },
  "con.market.title": { en: "Market", hi: "बाज़ार" },
  "con.conflicts.title": { en: "Where the sources disagree", hi: "जहाँ स्रोत असहमत हैं" },
  "con.impact.eyebrow": { en: "The closed loop", hi: "पूरा चक्र" },
  "con.impact.title": { en: "Impact", hi: "प्रभाव" },
  "con.knowledge.title": {
    en: "What the government has published",
    hi: "सरकार ने क्या प्रकाशित किया है",
  },
  //: Shown once in the console, in the reader's language, for the same reason the farmer
  //: assistant carries one: the figures below it are English and pretending otherwise
  //: would be a promise the page cannot keep.
  //: The real page headings. (`INV-4` and `DR-07` stay as they are — a requirement id is a
  //: name, not a phrase, and translating it would break the link to docs/SRS.md.)
  "con.decisions.h1": {
    en: "Every question, and what came of it",
    hi: "हर प्रश्न, और उसका परिणाम",
  },
  "con.decisions.sub": {
    en: "The evidence behind each answer is frozen at the moment it was given. Open one to approve, reject, or see why it said what it said.",
    hi: "हर उत्तर के पीछे का प्रमाण उसी क्षण स्थिर कर दिया जाता है जब वह दिया गया था। स्वीकार करने, अस्वीकार करने, या यह देखने के लिए कि ऐसा क्यों कहा गया, किसी एक को खोलें।",
  },
  "con.risk.h1": { en: "What is exposed, worst first", hi: "क्या जोखिम में है — सबसे गंभीर पहले" },
  "con.risk.sub": {
    en: "Ordered by how much is at stake, not by how likely it is. Weather figures are frequencies from 30 years of record — how often the window has been hit, not a forecast that it will be.",
    hi: "क्रम इस आधार पर है कि दाँव पर कितना है, इस पर नहीं कि सम्भावना कितनी है। मौसम के आँकड़े 30 वर्षों के अभिलेख से ली गई आवृत्तियाँ हैं — यह कि वह अवधि कितनी बार प्रभावित हुई, न कि यह पूर्वानुमान कि होगी।",
  },
  "con.impact.h1": { en: "What we can honestly claim", hi: "हम ईमानदारी से क्या कह सकते हैं" },
  "con.impact.sub": {
    en: "What the decision loop has actually recorded — including what it could not honestly claim.",
    hi: "निर्णय-चक्र ने वास्तव में क्या दर्ज किया — वह भी जो वह ईमानदारी से नहीं कह सका।",
  },
  "con.market.h1": { en: "Lots and offers", hi: "लॉट एवं प्रस्ताव" },
  "con.market.sub": {
    en: "Buyer offers are anchored to real mandi prices from Agmarknet.",
    hi: "क्रेता प्रस्ताव Agmarknet की वास्तविक मंडी कीमतों पर आधारित हैं।",
  },
  "con.conflicts.sub": {
    en: "Nothing on this page has been resolved, and that is deliberate. When two records conflict beyond tolerance the system lowers its confidence and waits, rather than picking a number nobody chose.",
    hi: "इस पृष्ठ पर कुछ भी सुलझाया नहीं गया है, और यह जानबूझकर है। जब दो अभिलेख सहनसीमा से अधिक भिन्न हों, तो प्रणाली अपना विश्वास घटाकर प्रतीक्षा करती है — कोई ऐसा आँकड़ा नहीं चुनती जिसे किसी ने तय न किया हो।",
  },
  "con.assistant.sub": {
    en: "Every answer arrives with its evidence. Anything it proposes waits for a human before it happens.",
    hi: "हर उत्तर अपने प्रमाण के साथ आता है। जो कुछ भी वह सुझाता है, वह होने से पहले किसी व्यक्ति की स्वीकृति की प्रतीक्षा करता है।",
  },
  "con.knowledge.sub": {
    en: "Cached public agricultural text — Uttar Pradesh government orders and departmental guidance — searchable in Hindi or English. Results are ranked by relevance multiplied by how much the source is worth trusting, so a well-matching passage nobody has cleared us to rely on loses to a cited one.",
    hi: "संचित सार्वजनिक कृषि पाठ — उत्तर प्रदेश के शासनादेश एवं विभागीय दिशा-निर्देश — हिन्दी या अंग्रेज़ी में खोजने योग्य। परिणाम प्रासंगिकता को स्रोत की विश्वसनीयता से गुणा करके क्रमबद्ध किए जाते हैं, इसलिए ऐसा अंश जो शब्दों से भले ही मेल खाता हो पर जिस पर निर्भर रहने की अनुमति किसी ने नहीं दी, उद्धृत अंश से पीछे रह जाता है।",
  },

  //: Dashboard panel headings. The landing screen, so worth translating even though the
  //: figures inside each panel stay English.
  "con.dash.waiting.eyebrow": { en: "Waiting on you", hi: "आपकी प्रतीक्षा में" },
  "con.dash.waiting.title": { en: "Nothing here has happened yet", hi: "यहाँ अभी कुछ नहीं हुआ है" },
  "con.dash.closing.eyebrow": { en: "Closing soon", hi: "जल्द बंद हो रहा" },
  "con.dash.closing.title": { en: "Windows about to shut", hi: "अवधियाँ जो समाप्त होने वाली हैं" },
  "con.dash.watch.eyebrow": { en: "Worth watching", hi: "ध्यान देने योग्य" },
  "con.dash.watch.title": { en: "Moving, not yet actionable", hi: "गतिशील, पर अभी कार्रवाई योग्य नहीं" },
  "con.dash.health.eyebrow": { en: "Data health", hi: "डेटा की स्थिति" },
  "con.dash.health.title": { en: "What the answers rest on", hi: "उत्तर किस पर टिके हैं" },
  "con.dash.briefing.eyebrow": { en: "Briefing", hi: "सार" },
  "con.dash.briefing.title": {
    en: "Nothing needs a decision today",
    hi: "आज किसी निर्णय की आवश्यकता नहीं है",
  },

  "con.dataInEnglish": {
    en: "Findings and figures are shown in English.",
    hi: "निष्कर्ष एवं आँकड़े अंग्रेज़ी में दिखाए जाते हैं।",
  },

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

export type StringKey = keyof typeof STRINGS | CopyKey;

/** Bind a locale once, at the top of a Server Component, and pass `t` down. */
/** What ``translator`` returns. Named so a component can take one as a prop. */
export type Translate = (key: StringKey, values?: CopyValues) => string;

export function translator(locale: Locale): Translate {
  const copy = interfaceCopy(locale);
  return (key, values) => key in STRINGS
    ? STRINGS[key as keyof typeof STRINGS][locale]
    : copy(key as CopyKey, values);
}

/** The five canned searches on the notices page, in the reader's language. */
export const NOTICE_SUGGESTIONS: { en: string; hi: string }[] = [
  { en: "crop insurance", hi: "फसल बीमा" },
  { en: "soil sample", hi: "मृदा नमूना" },
  { en: "fertiliser subsidy", hi: "उर्वरक अनुदान" },
  { en: "irrigation", hi: "सिंचाई" },
  { en: "seed", hi: "बीज" },
];
