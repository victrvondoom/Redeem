"""Localised spoken read-back. Voice never authorises: the closing line always sends approval to the signed-in app."""
from .. import config  # noqa: F401

T = {
    "en": ("I will {what}. This changes records at the provider and cannot be undone by me.", "Affected: {who}.", "Amount: {amt}.",
           "I cannot approve this by voice. Please approve it in the REDEEM app."),
    "hi": ("मैं {what} करूँगा। इससे प्रदाता के रिकॉर्ड बदलते हैं और मैं इसे वापस नहीं कर सकता।", "प्रभावित: {who}।", "राशि: {amt}।",
           "मैं आवाज़ से मंज़ूरी नहीं दे सकता। कृपया REDEEM ऐप में मंज़ूर करें।"),
    "hinglish": ("Main {what} karunga. Isse provider ke records badalte hain aur main ise undo nahi kar sakta.", "Affected: {who}.", "Amount: {amt}.",
                 "Main voice se approve nahi kar sakta. Kripya REDEEM app mein approve karein."),
    "ta": ("நான் {what} செய்வேன். இது வழங்குநரின் பதிவுகளை மாற்றும்; என்னால் திரும்பப் பெற முடியாது.", "பாதிக்கப்படுவது: {who}.", "தொகை: {amt}.",
           "குரல் மூலம் என்னால் ஒப்புதல் அளிக்க முடியாது. REDEEM செயலியில் ஒப்புதல் அளியுங்கள்."),
    "te": ("నేను {what} చేస్తాను. ఇది ప్రొవైడర్ రికార్డులను మారుస్తుంది; నేను దీన్ని వెనక్కి తీసుకోలేను.", "ప్రభావితం: {who}.", "మొత్తం: {amt}.",
           "నేను వాయిస్ ద్వారా ఆమోదించలేను. దయచేసి REDEEM యాప్‌లో ఆమోదించండి."),
}


def read_back(lang: str, what: str, who: str, amount: str | None) -> str:
    a, b, c, d = T.get(lang, T["en"])
    parts = [a.format(what=what), b.format(who=who)] + ([c.format(amt=amount)] if amount else []) + [d]
    return " ".join(parts)
