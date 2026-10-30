# YC product narrative (draft — assertions below are hypotheses unless marked "built")
1. **Problem.** Post-purchase disruptions (cancelled flight → refund + hotel + calendar + telling family) span services. People spend hours chasing; chatbots only explain.
2. **Who/frequency.** Travellers and small service businesses. *Frequency and willingness to pay are unmeasured; no interviews have been done.*
3. **Why voice agents are insufficient.** They talk well but typically stop at "I've raised a request". Several projects reviewed log intent/transcripts without reading back the external effect (README-level observation, not proof).
4. **Why workflow tools fall short.** Fixed triggers/graphs, no natural-language entry, no identity/approval/verification semantics for consequential actions.
5. **Why voice + multi-domain.** The user states one outcome; the system must coordinate dependent tasks. *Built (fixture):* one mission → refund, hotel, calendar, family draft, alternatives.
6. **Defensibility.** See TECHNICAL_MOAT.md; the credible moat is verified connectors + failure traces, not the router.
7. **Measurable improvement.** On our own fixtures (7 scenarios × 30 seeds, 210 trials/policy): REDEEM 210/210 correct vs naive 0/210, checked 60/210; false success 0 vs 210/150. Not evidence of real-world reliability.
8. **Wedge.** *Consumer travel-disruption resolution*, chosen over (retail voice ops, scam prevention, complaint handling, appointments, support) because it uses the full moat, it is built end-to-end on fixtures, and none of the 14 reviewed READMEs targets it. Retail voice operations is crowded (Dukan, AI Sales Engineer, WareOnGo) and payment-scam prevention has a strong deployed rival (Ruko). Scoring is my judgement, not data.
9. **Expansion.** Travel → other post-purchase disputes (case desk) → small businesses that need verified voice-to-record operations (retail reservation, CRM) → API for developers who need verified execution.
10. **Durable company.** Per-verified-outcome pricing and a connector network, if live connectors and trust metrics are proven. *No traction, revenue or validation exists today.*
**Next evidence to collect:** 10 traveller interviews; one real airline/OTA integration or supported browser flow; live Bolna calls with consenting testers; measured cost per verified mission.
