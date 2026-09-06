import type { Locale } from "@/lib/locale";
import { interfaceCopy, UI_COPY, type CopyKey } from "@/lib/ui-copy";

const TERMS: Record<string, string> = {
  "member farmers": "सदस्य किसान", "operated area": "कृषि क्षेत्रफल", "crops in the ground": "खेतों में फ़सलें",
  "active crop cycles": "सक्रिय फ़सल चक्र", "aggregated for sale": "बिक्री के लिए एकत्रित", "live buyer offers": "वर्तमान खरीदार प्रस्ताव",
  "unresolved data conflicts": "अनसुलझे डेटा मतभेद", "awaiting your approval": "आपकी स्वीकृति की प्रतीक्षा में",
  "unclaimed scheme benefit": "अप्राप्त योजना लाभ", "working capital": "कार्यशील पूँजी",
  "anchored to mandi modal prices": "मंडी के प्रचलित भावों पर आधारित", "sources disagree; awaiting verification": "स्रोत असहमत हैं; सत्यापन लंबित है",
  "ai recommends; you decide": "एआई सुझाव देता है; निर्णय आप लेते हैं", "identified across members": "सदस्यों में पहचाना गया",
  "scheme engine not yet run": "योजनाओं का मूल्यांकन अभी नहीं हुआ", "cold store capacity unknown": "शीतगृह क्षमता अज्ञात", "nothing sown": "अभी बुआई नहीं हुई",
  "ac": "एकड़", "acre": "एकड़", "acres": "एकड़", "ha": "हेक्टेयर", "kg": "किग्रा", "t": "टन", "tonnes": "टन", "km": "किमी", "d": "दिन",
  "ganga par": "गंगापार", "ganga-par": "गंगापार", "doab": "दोआब", "yamuna par": "यमुनापार", "yamuna-par": "यमुनापार",
  "potato": "आलू", "wheat": "गेहूँ", "paddy": "धान", "rice": "चावल", "mustard": "सरसों", "guava": "अमरूद", "tomato": "टमाटर", "chickpea": "चना", "arhar": "अरहर", "pigeonpea": "अरहर", "maize": "मक्का", "lentil": "मसूर", "pea": "मटर", "peas": "मटर", "sugarcane": "गन्ना",
  "rabi": "रबी", "kharif": "खरीफ़", "zaid": "ज़ायद", "growing": "बढ़ रही है", "harvested": "कटाई हो चुकी", "planned": "नियोजित", "failed": "विफल", "closed": "बंद", "sown": "बोई गई",
  "field officer": "क्षेत्र अधिकारी", "farmer self report": "किसान का स्वयं विवरण", "farmer reported": "किसान द्वारा दर्ज", "ai inference": "एआई अनुमान", "ai inferred": "एआई द्वारा अनुमानित", "external source": "बाहरी स्रोत", "org record": "संगठन अभिलेख", "organization record": "संगठन अभिलेख", "fixture": "सुरक्षित स्रोत", "cached source": "सुरक्षित स्रोत",
  "fpo ceo": "एफ़पीओ मुख्य कार्यकारी", "market officer": "बाज़ार अधिकारी", "finance officer": "वित्त अधिकारी", "platform admin": "प्लेटफ़ॉर्म प्रशासक", "farmer": "किसान", "member": "सदस्य", "fpo": "एफ़पीओ", "pacs": "पैक्स", "shg": "स्वयं सहायता समूह",
  "weather": "मौसम", "climate": "जलवायु", "market": "बाज़ार", "crop health": "फ़सल की स्थिति", "policy": "नीति", "supply chain": "आपूर्ति शृंखला", "global": "वैश्विक", "input price": "कृषि सामग्री की कीमत",
  "high": "उच्च", "medium": "मध्यम", "low": "कम", "moderate": "मध्यम", "uncertain": "अनिश्चित", "confounded": "अन्य कारणों से प्रभावित",
  "full": "पूर्ण", "partial": "आंशिक", "none": "कोई नहीं", "not followed": "पालन नहीं हुआ", "fully followed": "पूर्ण पालन", "partially followed": "आंशिक पालन", "unknown": "अज्ञात",
  "plot": "खेत", "crop cycle": "फ़सल चक्र", "lot": "लॉट", "plot area": "खेत का क्षेत्रफल", "yield": "पैदावार", "quantity": "मात्रा",
  "suggested": "प्रस्तावित", "reviewed": "समीक्षित", "approved": "स्वीकृत", "executed": "लागू", "rejected": "अस्वीकृत", "superseded": "प्रतिस्थापित", "outcome recorded": "परिणाम दर्ज", "approve": "स्वीकृत", "reject": "अस्वीकृत", "modify": "संशोधित", "approved modified": "संशोधन के साथ स्वीकृत",
  "authoritative": "प्रामाणिक", "advisory": "परामर्शात्मक", "verified": "सत्यापित", "unverified": "असत्यापित",
  "sandy loam": "बलुई दोमट", "loam": "दोमट", "clay loam": "चिकनी दोमट", "alluvial": "जलोढ़", "sandy": "बलुई", "clay": "चिकनी मिट्टी", "canal": "नहर", "tubewell": "नलकूप", "tube well": "नलकूप", "rainfed": "वर्षा आधारित", "well": "कुआँ", "borewell": "बोरवेल",
  "prayagraj": "प्रयागराज", "uttar pradesh": "उत्तर प्रदेश",
};

export function term(value: string | null | undefined, locale: Locale): string {
  if (!value) return "—";
  if (locale === "en") return value;
  const normalized = value.replace(/_/g, " ").toLowerCase();
  return TERMS[normalized] ?? value;
}

export function recordText(value: string | null | undefined, locale: Locale): string {
  if (!value) return "";
  if (locale === "en" || /[\u0900-\u097f]/.test(value)) return value;
  const copy = interfaceCopy(locale);
  if (value in UI_COPY) return copy(value as CopyKey);
  const normalized = value.toLowerCase();
  if (TERMS[normalized]) return TERMS[normalized];
  const lots = /^across (\d+) lots$/.exec(value);
  if (lots) return `${lots[1]} लॉट में`;
  // Quantities stay unchanged; only the known crop and unit vocabulary is translated.
  if (/^(?:[\w -]+ )?[\d,.]+ (?:ac|ha|kg|t)(?:, |$)/.test(value)) {
    return value.replace(/[A-Za-z]+(?: [A-Za-z]+)*/g, (word) => term(word, locale));
  }
  return copy("A translation of this record is not available in the selected language.");
}

export function localeDate(value: string, locale: Locale, options: Intl.DateTimeFormatOptions = {}): string {
  return new Date(value).toLocaleDateString(locale === "hi" ? "hi-IN" : "en-IN", {
    timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", ...options,
  });
}

export function localeDateTime(value: string, locale: Locale): string {
  return new Date(value).toLocaleString(locale === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata" });
}

export function localizedMass(kg: number, locale: Locale): string {
  const value = kg >= 1000 ? kg / 1000 : kg;
  return `${value.toLocaleString(locale === "hi" ? "hi-IN" : "en-IN", { maximumFractionDigits: 1 })} ${term(kg >= 1000 ? "t" : "kg", locale)}`;
}
