import type { Lang } from "./api";

// NOTE: translations are first drafts written for this build and have NOT had native-speaker review.
type Dict = Record<string, string>;

const en: Dict = {
  "nav.product": "Product", "nav.how": "How it works", "nav.solutions": "Solutions", "nav.security": "Security",
  "nav.business": "For Business", "nav.developers": "Developers", "nav.signin": "Sign in", "nav.start": "Get started",
  "hero.eyebrow": "Your life has enough follow-ups.", "hero.title1": "Speak your need.", "hero.title2": "We take the lead.",
  "hero.sub": "Refunds, bookings, service issues, customer calls and everyday tasks. REDEEM works across your services, takes authorized action, and shows you what actually happened.",
  "hero.cta1": "Start with your voice", "hero.cta2": "See how it works",
  "composer.title": "What do you need sorted?", "composer.placeholder": "Describe the problem in your own words…",
  "composer.mic": "Speak", "composer.stop": "Stop", "composer.listening": "Listening… speak now", "composer.submit": "Start mission",
  "composer.language": "Language", "composer.suggested": "Try one of these",
  "composer.micNote": "Uses your browser's speech recognition. Nothing is acted on until you review the transcript.",
  "composer.micUnsupported": "Voice input isn't supported in this browser. Type instead, or use Voice Studio after signing in.",
  "composer.lowConfidence": "I wasn't sure I heard that right — please check the text.",
  "p.1": "My flight was cancelled. Help me recover my refund.", "p.2": "A customer wants a keyboard reserved for Saturday.",
  "p.3": "Someone asked me to share an OTP to avoid account block.",
  "how.title": "From conversation to confirmed outcome", "how.1": "Speak", "how.1d": "Say the problem in your language. Review the transcript.",
  "how.2": "Plan", "how.2d": "REDEEM finds the right records and prepares exact actions.",
  "how.3": "Approve", "how.3d": "Each action is shown with its target and amount. You approve, or not.",
  "how.4": "Verify", "how.4d": "A separate check reads the real system state and issues a receipt.",
  "console.hello": "Hello", "console.new": "New mission", "console.active": "Active missions", "console.recent": "Recent missions",
  "console.empty": "No missions yet. Describe a problem above to begin.", "console.pending": "Waiting for you",
  "side.console": "Console", "side.voice": "Voice Studio", "side.domains": "Domains", "side.connections": "Connections",
  "side.vault": "Evidence Vault", "side.history": "History", "side.quality": "Quality Lab", "side.settings": "Settings", "side.signout": "Sign out",
  "status.VERIFIED": "Verified", "status.NEEDS_APPROVAL": "Needs your approval", "status.DISCOVERING": "Needs a detail from you",
  "status.AUTHORIZED": "Approved — ready to run", "status.UNCERTAIN": "Uncertain — checking", "status.FAILED": "Failed",
  "status.CANCELLED": "Cancelled", "status.PARTIALLY_VERIFIED": "Partly verified", "status.EXECUTING": "Running",
  "status.INTENT_CAPTURED": "Captured", "status.CLASSIFIED": "Understood",
};

const hi: Dict = {
  "nav.product": "उत्पाद", "nav.how": "यह कैसे काम करता है", "nav.solutions": "समाधान", "nav.security": "सुरक्षा",
  "nav.business": "व्यवसाय के लिए", "nav.developers": "डेवलपर्स", "nav.signin": "साइन इन", "nav.start": "शुरू करें",
  "hero.eyebrow": "आपकी ज़िंदगी में पहले से बहुत फ़ॉलो-अप हैं।", "hero.title1": "अपनी ज़रूरत बोलिए।", "hero.title2": "आगे का काम हम संभालेंगे।",
  "hero.sub": "रिफंड, बुकिंग, सर्विस की दिक्कतें, ग्राहकों के कॉल और रोज़ के काम। REDEEM आपकी सेवाओं में काम करता है, अनुमति के साथ कदम उठाता है, और दिखाता है कि असल में क्या हुआ।",
  "hero.cta1": "आवाज़ से शुरू करें", "hero.cta2": "देखें कैसे काम करता है",
  "composer.title": "आपको क्या सुलझाना है?", "composer.placeholder": "अपनी बात अपने शब्दों में बताइए…",
  "composer.mic": "बोलिए", "composer.stop": "रोकें", "composer.listening": "सुन रहा हूँ… बोलिए", "composer.submit": "मिशन शुरू करें",
  "composer.language": "भाषा", "composer.suggested": "इनमें से कोई आज़माइए",
  "composer.micNote": "यह आपके ब्राउज़र की स्पीच पहचान इस्तेमाल करता है। आपके टेक्स्ट देख लेने तक कुछ नहीं किया जाता।",
  "composer.micUnsupported": "इस ब्राउज़र में आवाज़ इनपुट उपलब्ध नहीं है। टाइप करें, या साइन इन के बाद Voice Studio इस्तेमाल करें।",
  "composer.lowConfidence": "शायद मैंने ठीक से नहीं सुना — कृपया टेक्स्ट जाँच लें।",
  "p.1": "मेरी फ्लाइट रद्द हो गई। रिफंड वापस पाने में मदद करें।", "p.2": "एक ग्राहक शनिवार के लिए कीबोर्ड रिज़र्व करवाना चाहता है।",
  "p.3": "किसी ने खाता ब्लॉक होने से बचाने के लिए OTP माँगा है।",
  "how.title": "बातचीत से पुष्टि किए गए नतीजे तक", "how.1": "बोलिए", "how.1d": "अपनी भाषा में समस्या बताइए। टेक्स्ट देख लीजिए।",
  "how.2": "योजना", "how.2d": "REDEEM सही रिकॉर्ड ढूँढकर सटीक कदम तैयार करता है।",
  "how.3": "मंज़ूरी", "how.3d": "हर कदम अपने लक्ष्य और राशि के साथ दिखता है। आप मंज़ूर करें या नहीं।",
  "how.4": "सत्यापन", "how.4d": "एक अलग जाँच असली सिस्टम की स्थिति पढ़कर रसीद देती है।",
  "console.hello": "नमस्ते", "console.new": "नया मिशन", "console.active": "चालू मिशन", "console.recent": "हाल के मिशन",
  "console.empty": "अभी कोई मिशन नहीं। ऊपर अपनी समस्या लिखें।", "console.pending": "आपके जवाब का इंतज़ार",
  "side.console": "कंसोल", "side.voice": "वॉइस स्टूडियो", "side.domains": "क्षेत्र", "side.connections": "कनेक्शन",
  "side.vault": "प्रमाण तिजोरी", "side.history": "इतिहास", "side.quality": "क्वालिटी लैब", "side.settings": "सेटिंग्स", "side.signout": "साइन आउट",
  "status.VERIFIED": "सत्यापित", "status.NEEDS_APPROVAL": "आपकी मंज़ूरी चाहिए", "status.DISCOVERING": "आपसे एक जानकारी चाहिए",
  "status.AUTHORIZED": "मंज़ूर — चलाने को तैयार", "status.FAILED": "विफल", "status.CANCELLED": "रद्द",
};

const hinglish: Dict = {
  ...en,
  "nav.how": "Kaise kaam karta hai", "nav.security": "Security", "nav.signin": "Sign in", "nav.start": "Shuru karein",
  "hero.eyebrow": "Aapki life mein pehle se bahut follow-ups hain.", "hero.title1": "Apni zaroorat boliye.", "hero.title2": "Aage ka kaam hum sambhalenge.",
  "hero.sub": "Refund, booking, service ki dikkat, customer calls aur roz ke kaam. REDEEM aapki permission se action leta hai aur dikhata hai ki asal mein kya hua.",
  "hero.cta1": "Awaaz se shuru karein", "hero.cta2": "Kaise kaam karta hai dekhein",
  "composer.title": "Aapko kya sort karwana hai?", "composer.placeholder": "Apni baat apne shabdon mein batayein…",
  "composer.mic": "Boliye", "composer.stop": "Rokein", "composer.listening": "Sun raha hoon… boliye", "composer.submit": "Mission shuru karein",
  "composer.language": "Bhasha", "composer.suggested": "Inmein se koi try karein",
  "p.1": "Meri flight cancel ho gayi. Refund wapas dilane mein madad karo.", "p.2": "Ek customer Saturday ke liye keyboard reserve karwana chahta hai.",
  "p.3": "Kisi ne account block se bachne ke liye OTP maanga hai.",
  "console.hello": "Namaste", "console.new": "Naya mission", "status.VERIFIED": "Verify ho gaya", "status.NEEDS_APPROVAL": "Aapki approval chahiye",
};

const ta: Dict = {
  ...en,
  "nav.product": "தயாரிப்பு", "nav.how": "எப்படி செயல்படுகிறது", "nav.solutions": "தீர்வுகள்", "nav.security": "பாதுகாப்பு",
  "nav.business": "வணிகத்திற்கு", "nav.developers": "டெவலப்பர்கள்", "nav.signin": "உள்நுழை", "nav.start": "தொடங்குங்கள்",
  "hero.eyebrow": "உங்கள் வாழ்க்கையில் ஏற்கனவே போதுமான பின்தொடர்தல்கள் உள்ளன.", "hero.title1": "உங்கள் தேவையைச் சொல்லுங்கள்.", "hero.title2": "மீதியை நாங்கள் பார்த்துக்கொள்கிறோம்.",
  "hero.sub": "ரீஃபண்ட், முன்பதிவு, சேவை சிக்கல்கள், வாடிக்கையாளர் அழைப்புகள். REDEEM உங்கள் அனுமதியுடன் செயல்பட்டு, உண்மையில் என்ன நடந்தது என்பதைக் காட்டுகிறது.",
  "hero.cta1": "குரலில் தொடங்குங்கள்", "hero.cta2": "எப்படி என்று பாருங்கள்",
  "composer.title": "என்ன சரிசெய்ய வேண்டும்?", "composer.placeholder": "உங்கள் பிரச்சினையை உங்கள் சொற்களில் எழுதுங்கள்…",
  "composer.mic": "பேசுங்கள்", "composer.stop": "நிறுத்து", "composer.listening": "கேட்கிறேன்… பேசுங்கள்", "composer.submit": "பணியைத் தொடங்கு",
  "composer.language": "மொழி", "composer.suggested": "இவற்றில் ஒன்றை முயற்சிக்கவும்",
  "p.1": "என் விமானம் ரத்தானது. ரீஃபண்ட் பெற உதவுங்கள்.", "p.2": "ஒரு வாடிக்கையாளர் சனிக்கிழமைக்கு கீபோர்டு முன்பதிவு செய்ய விரும்புகிறார்.",
  "p.3": "கணக்கு முடக்கத்தைத் தவிர்க்க OTP கேட்கிறார்கள்.",
  "console.hello": "வணக்கம்", "console.new": "புதிய பணி", "status.VERIFIED": "சரிபார்க்கப்பட்டது", "status.NEEDS_APPROVAL": "உங்கள் ஒப்புதல் தேவை",
};

const te: Dict = {
  ...en,
  "nav.product": "ఉత్పత్తి", "nav.how": "ఎలా పనిచేస్తుంది", "nav.solutions": "పరిష్కారాలు", "nav.security": "భద్రత",
  "nav.business": "వ్యాపారానికి", "nav.developers": "డెవలపర్లు", "nav.signin": "సైన్ ఇన్", "nav.start": "ప్రారంభించండి",
  "hero.eyebrow": "మీ జీవితంలో ఇప్పటికే చాలా ఫాలో-అప్‌లు ఉన్నాయి.", "hero.title1": "మీ అవసరం చెప్పండి.", "hero.title2": "మిగతాది మేము చూసుకుంటాం.",
  "hero.sub": "రీఫండ్‌లు, బుకింగ్‌లు, సర్వీస్ సమస్యలు, కస్టమర్ కాల్స్. REDEEM మీ అనుమతితో చర్య తీసుకుని, నిజంగా ఏం జరిగిందో చూపిస్తుంది.",
  "hero.cta1": "మీ గొంతుతో ప్రారంభించండి", "hero.cta2": "ఎలాగో చూడండి",
  "composer.title": "ఏమి సరిచేయాలి?", "composer.placeholder": "మీ సమస్యను మీ మాటల్లో చెప్పండి…",
  "composer.mic": "మాట్లాడండి", "composer.stop": "ఆపండి", "composer.listening": "వింటున్నాను… మాట్లాడండి", "composer.submit": "మిషన్ ప్రారంభించు",
  "composer.language": "భాష", "composer.suggested": "వీటిలో ఒకటి ప్రయత్నించండి",
  "p.1": "నా విమానం రద్దయింది. రీఫండ్ పొందడానికి సహాయం చేయండి.", "p.2": "ఒక కస్టమర్ శనివారానికి కీబోర్డ్ రిజర్వ్ చేయాలని కోరుతున్నారు.",
  "p.3": "ఖాతా బ్లాక్ కాకుండా ఉండటానికి OTP అడిగారు.",
  "console.hello": "నమస్కారం", "console.new": "కొత్త మిషన్", "status.VERIFIED": "ధృవీకరించబడింది", "status.NEEDS_APPROVAL": "మీ ఆమోదం కావాలి",
};

export const MESSAGES: Record<Lang, Dict> = { en, hi, hinglish, ta, te };
export const LANG_LABEL: Record<Lang, string> = { en: "English", hi: "हिन्दी", hinglish: "Hinglish", ta: "தமிழ்", te: "తెలుగు" };
export const HTML_LANG: Record<Lang, string> = { en: "en-IN", hi: "hi", hinglish: "en-IN", ta: "ta", te: "te" };
export const SPEECH_LANG: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", hinglish: "en-IN", ta: "ta-IN", te: "te-IN" };
