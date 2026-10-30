# 90-second demo (fixture-backed; say so on camera)
1. Landing → pick Hindi → back to English. Type: "My flight FA2041 was cancelled. I need my refund, my hotel rescheduled, and my calendar corrected." → sign up.
2. Mission page: 3 planned actions, exact ₹ amount, digest, blocked voice call labelled PROVIDER_NOT_CONFIGURED.
3. Press "Lose the provider's acknowledgement" → Approve 3 → Run. Show ledger: ACK_LOST → RECONCILED_FOUND → VERIFIED. Receipt + ledger hash. Reload: receipt persists.
4. Correction demo: new mission "Flight cancelled for Rahul" → pick Rahul Sharma → Approve → type "Flight FA2087 …" in *Wait — change something?* → approval invalidated → re-approve → verified, other Rahul untouched.
5. Shop: "Customer Amit wants a keyboard reserved for Saturday" → disambiguate Amit Patel/Patil → verified stock 4→3.
6. Quality Lab: benchmark + ablation table; "Not measured" where nothing is measured.
(With Bolna credentials: Voice Studio live call; see MANUAL_ACTIONS_LATER.)
