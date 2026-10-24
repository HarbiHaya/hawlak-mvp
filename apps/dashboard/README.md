# Dashboard workspace — Retaj

Retaj owns this application. Its first integration target is the versioned `pharmacist_review_requested` contract from `@hawlak/contracts`.

The dashboard should not call OpenAI, generate audio, process WhatsApp webhooks, or decide whether a medicine photo matches a prescription. It displays the approved plan and received photos so a pharmacist can make that decision.

Recommended first screen:

1. Review queue.
2. Patient alias and masked phone number.
3. Approved plan version.
4. Medicine photos in received order.
5. Pharmacist outcomes: matched, mismatch found, unclear photo, contact patient.
6. Audit timestamp and reviewer identity.

Create the dashboard package here without changing the event contract silently. Contract changes require a pull request reviewed by Haya and Retaj.

