import { createContext, ReactNode, useContext, useState } from "react";
export type Lang = "en" | "hi";
const HI: Record<string, string> = {
  Home: "होम", Market: "बाज़ार", Portfolio: "पोर्टफोलियो", Business: "बिज़नेस", News: "समाचार", Ranks: "रैंक",
  "Total net worth": "कुल संपत्ति", Cash: "नकद", Invested: "निवेशित", "Top gainers": "टॉप गेनर्स", "Top losers": "टॉप लूज़र्स",
  "Latest news": "ताज़ा खबर", "See all": "सब देखें", Back: "वापस", Buy: "खरीदें", Sell: "बेचें", "Search stocks": "स्टॉक खोजें",
  "Portfolio value": "पोर्टफोलियो वैल्यू", Holdings: "होल्डिंग्स", History: "इतिहास", Deals: "डील्स", Leaderboard: "लीडरबोर्ड",
  Rewards: "इनाम", Watchlist: "वॉचलिस्ट", Settings: "सेटिंग्स", Theme: "थीम", Language: "भाषा", Notifications: "नोटिफिकेशन",
  Auto: "ऑटो", Light: "लाइट", Dark: "डार्क", Today: "आज", "7 days": "7 दिन", "30 days": "30 दिन", "All time": "सारा समय",
  "Daily reward": "दैनिक इनाम", Claim: "लें", Missions: "मिशन", Badges: "बैज", Streak: "स्ट्रीक", Alert: "अलर्ट",
  "Price alerts": "प्राइस अलर्ट", Create: "बनाएं", Delete: "हटाएं", Accept: "स्वीकार", Cancel: "रद्द", "New deal": "नई डील",
  "Total": "कुल", "You receive": "आपको मिलेगा", Value: "मूल्य", Fee: "फीस", "Confirm Buy": "खरीद पक्की करें", "Confirm Sell": "बिक्री पक्की करें",
  "All": "सभी", "Company news": "कंपनी न्यूज़", "Sector news": "सेक्टर न्यूज़", "Major only": "सिर्फ बड़ी", "Off": "बंद",
  "No holdings yet.": "अभी कोई होल्डिंग नहीं।", "No trades yet.": "अभी कोई ट्रेड नहीं।", "No news yet.": "अभी कोई खबर नहीं।",
  "Waiting for approval": "अप्रूवल का इंतज़ार", "Create company": "कंपनी बनाएं", "My Companies": "मेरी कंपनियाँ", "IPO Market": "IPO मार्केट", Bank: "बैंक",
  Arena: "अखाड़ा", Orders: "ऑर्डर्स",
  Dividends: "डिविडेंड", "Take a loan": "लोन लें", Borrow: "उधार लें", Repay: "चुकाएं", Manage: "मैनेज", "Launch IPO": "IPO शुरू करें",
};
const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (s: string) => string }>({ lang: "en", setLang: () => {}, t: (s) => s });
export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, set] = useState<Lang>(() => { try { return (localStorage.getItem("sw-lang") as Lang) || "en"; } catch { return "en"; } });
  const setLang = (l: Lang) => { set(l); try { localStorage.setItem("sw-lang", l); } catch { /* ignore */ } };
  return <Ctx.Provider value={{ lang, setLang, t: (s) => (lang === "hi" ? HI[s] ?? s : s) }}>{children}</Ctx.Provider>;
}
export const useT = () => useContext(Ctx);
