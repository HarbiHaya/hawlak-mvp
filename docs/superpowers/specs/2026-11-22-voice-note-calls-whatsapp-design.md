# Voice note, follow-up calls and WhatsApp delivery: design

Status: approved by Haya, 22 November 2026.

## Why

The first live run of a real-shaped discharge PDF (`Cases.pdf`: an English summary
for a patient set to Arabic) showed five problems:

1. **The voice note tries to do too much.** It lists every medicine, so it is
   long. For an Arabic patient with an English PDF, the guard rejects every AI
   draft because the AI writes "فوروسيميد" while the guard wants "Furosemide"
   letter for letter. The draft then falls back to a template that mixes Arabic
   sentences with English lines.
2. **The call sounds like a form.** The agent reads the approved script word for
   word and cannot acknowledge, repeat, rephrase or answer "what do you mean?".
3. **The transfer did not reach anyone.** LiveKit sent a SIP REFER and Telnyx
   accepted it, so Hawlak recorded `transferred`. The care team phone
   (+966…8908, confirmed correct) never rang.
4. **Nothing arrived on WhatsApp, but the dashboard said "sent".** Meta rejected the
   voice note and the photo request with error 131047: the patient had not
   messaged the business number in the last 24 hours. Hawlak gets Meta's
   failure report but never saves it against the delivery run.
5. **A full phone number goes into the logs.** The webhook logs the whole
   `wa_message_id`, and Meta's message ID contains the recipient's number in
   base64.

## Goals

- **Voice note:** discharge instructions only. Short, complete, in everyday words
  and in the patient's dialect. No medicines.
- **Medicines:** handled outside the voice note, by the photo request and the
  reminders that already exist.
- **Calls:** feel like talking to a person (acknowledge, repeat, rephrase, ask one
  follow-up, answer from the approved instructions). Every approved question is
  still covered, and a person still gets every warning sign.
- **Transfer:** "transferred" means a care-team member answered. Otherwise the
  patient is told the team will call back, and the alert says the transfer failed.
- **WhatsApp:** messages reach a patient who has never messaged Hawlak.
- **Status:** the dashboard shows "failed" when Meta fails a message.

## Non-goals

- OCR for scanned PDFs.
- Letting the call agent give advice, change a dose or say anything clinical
  that is not in the approved content.
- A new dashboard screen beyond what is listed under "Dashboard" below.

## Anti-goals (a failure even if it works)

- The agent tells a patient something clinical that no one approved, or
  reassures them away from a warning sign.
- A warning sign ends without a person hearing about it.
- The dashboard shows "sent" or "transferred" for something that did not happen.

## Approaches (calls)

Picked by Haya: **option 1**.

1. **Free wording, approved content (picked).** The model talks naturally but
   works through the approved questions. It can answer only from the approved
   voice note and reminders. Every warning sign, unsure answer or request for a
   person goes to a person. Every turn is stored for the care team. Trade-off: the
   "exact approved script" rule becomes "approved content, checked in code".
2. Fully free agent with the whole discharge summary. Rejected: it would give
   unapproved medical advice, against the "AI changes wording only" promise.
3. More approved script variants (acknowledgements, repeats). Rejected: it keeps
   the rule but still sounds scripted, which is the complaint.

Transfer (my call): **warm dial instead of SIP REFER.** The agent dials the care
team into the same LiveKit room and connects the patient only when someone
answers. REFER can't tell Hawlak whether anyone answered, and it has already
failed silently once.

WhatsApp (my call): **opening template, then free-form.** A template can't carry
audio, so the voice note can never go as a template. The standard pattern is an
approved utility template with a button, which opens the 24-hour window when the
patient taps it.

## Design

### 1. Delivery status and logging (API only)

- When a Meta status webhook reports `failed` for a message ID that belongs to a
  delivery run (`provider_ref` holds one or two comma-joined IDs), set the run to
  `failed`, keep Meta's error code on the run, and add a `delivery_failed` alert
  (medium). The dashboard already shows `failed` as "تعذّر الإرسال" (could not
  send).
- Statuses never move a run backwards: `failed` wins over a later `sent` or
  `delivered`.
- Log message IDs as a short hash, never the raw `wamid`. Check every other log
  line that prints a `wamid`.

### 2. Voice note: instructions only, and the guard

- New prompt `journey-draft-v5.txt`; v4 stays as it is. Its voiceScript:
  - a greeting and why the message is sent;
  - each instruction section (activity, diet, follow-up, dialysis plan and
    others), in everyday words with no medical terms;
  - warning signs, with the emergency number when the document has one;
  - one sentence saying the medicines come in separate messages with photos and
    reminders;
  - a closing.
- Target length: 80 to 160 words. Every section item is still covered; merging
  is fine, dropping is not.
- Translating terms is part of "wording": "hemodialysis" becomes "الغسيل الكلوي"
  (kidney dialysis), and "NSAIDs such as ibuprofen" becomes something like
  "مسكنات الألم مثل البروفين" (painkillers like Brufen). No new facts.
- Guard changes (`guard_draft`):
  - Drop "every medicine name and dose number appears in the voice note".
  - Add "no medicine name appears in the voice note". Compare each medicine's
    first word, case-insensitively, against the voice script.
  - Add "every number in the instruction sections appears in the voice note".
    This is a cheap check that nothing was dropped.
  - Keep "no invented numbers" across all outputs.
  - Reminders still contain the medicine name exactly as printed. That matches
    the box the patient holds, and it removes the Arabic rejection.
- Template drafter (the fallback): the same structure without medicines. When the
  document language differs from the patient's language, the template copies
  the source text and the draft keeps the existing `live_draft_rejected` note.
  The reviewer translates.
- Stopped medicines: see the open questions below.

### 3. WhatsApp: open the window first

- Two Meta templates, in Arabic and English, category utility:
  - **Opener:** "مرحباً، عندك تعليمات الخروج من المستشفى من فريق رعايتك عن طريق
    حولك." ("Hello, your care team has sent your hospital discharge instructions
    through Hawlak.") With one quick-reply button: «أرسلها لي» ("Send them to
    me"). No name, no clinical content.
  - **Photo request:** the existing `WHATSAPP_PHOTO_REQUEST_TEMPLATE`, with the
    medicine names as variables. Hawlak already sends it when the setting is set.
- Approval creates an `opener` run first. It is due immediately and sent as the
  template.
- The voice note and photo request runs stay `pending` until the window is open,
  meaning the patient's last inbound message is under 24 hours old. Every inbound
  patient message, the opener button included, triggers `dispatch_due` for that
  case. The photo request uses its template when one is configured and does not
  wait.
- Reminders: when the window is closed, a reminder goes as a text template (the
  medicine name and the "taken / not yet" buttons). Otherwise it goes as today.
  The template name is a setting; when it's unset, behaviour stays as today and a
  failure now shows as `failed`.
- Templates go to Meta through the WhatsApp Business connector or Meta Business
  Manager, only on Haya's go-ahead. Names go into SSM `/hawlak/demo/env`.

### 4. Follow-up call: natural agent, checked

**Who decides what:**
- The model writes the words.
- `CallConversation` stays the authority on progress. It tracks which approved
  questions are answered, refuses to end the call before all are, and turns any
  non-clear answer into a transfer.

**What the model gets:**
- the approved opening, questions, completion and transfer lines;
- the approved voice note script and reminder scripts, as the only facts it may
  state;
- the language and dialect profile;
- no phone numbers, member ID, PDF or insurance data.

**The model has no tools** (simplified while planning):
- The classifier labels every patient turn, and `CallConversation` picks the next
  step. The model only phrases that step from a per-turn instruction.
- The model can't record an answer, skip a question, downgrade a warning sign
  or end the call.

**What the model may say:**
- acknowledgements;
- the approved question, reworded or repeated;
- one clarifying follow-up per question;
- answers taken only from the approved content;
- "I'll connect you with the care team" for anything else.

**Speech guard before text-to-speech:**
- Each sentence is checked before it is spoken. No number outside the approved
  content. No medicine name outside the plan. At most 40 words per turn.
- A sentence that fails is replaced by the approved line for the current step,
  and the failure is counted.

**Stored per call (new table, care team only):**
- each turn: who spoke, the text, the guard result and the answer kind;
- kept with the case, never in logs, analytics or the caregiver view.

The privacy doc rows 9 and 10 and the boundary table change accordingly.

**LLM setup:** use LiveKit's OpenAI chat LLM over HTTPS. Today's Responses
WebSocket client hits `wss://api.openai.com/v1` and gets a 404 on every turn.
The model name comes from `OPENAI_LLM_MODEL`.

**Warm transfer:**
- The agent dials the approved responder number as a second SIP participant with
  `wait_until_answered` and a 30-second limit.
- On answer, the responder hears one fixed line: "Hawlak follow-up call: the
  patient reported a concern at question N."
- The agent then leaves the room so patient and responder stay connected, and
  records `transferred`.
- On no answer, the patient hears a fixed line ("the care team will call you back
  shortly"), the call ends, and the outcome is `failed` with the escalation, which
  creates the existing high alert.
- The two fixed lines live in code by language, like `PHOTO_REPLIES`.

### Dashboard (Retaj's app; contract change needs both reviewers)

- A label for the new `opener` run kind.
- The call transcript on the case for the care team. Read-only, under the call
  run.

### Docs and rules to update

- AGENTS.md:
  - "Nothing reaches a patient until its exact script is approved" gets a
    narrow exception for the call agent's wording. Approved content stays the
    only source of facts.
  - The README sentence "patient-facing speech is never generated by the model"
    is replaced.
- `docs/architecture/platform-data-privacy.md`: rows 4, 9 and 10, the boundary
  table (transcripts now stored for the care team) and the status table.
- README Status.

### Order of work (each step ships alone)

1. Delivery status and logging fix.
2. Voice note and guard (prompt v5).
3. WhatsApp opener and held runs. Templates submitted to Meta in parallel.
4. Warm transfer, on the current scripted agent. It's testable on its own.
5. Natural call agent.

## Testing

- Write the tests first (AGENTS.md).
- Guard tests: an Arabic draft for an English PDF passes; a voice note that names
  a medicine fails; a dropped section number fails.
- Webhook test: a failed status marks the run failed and adds an alert.
- Agent tests drive `CallConversation` with a fake model: the model can't skip a
  question, a red flag the model calls clear still transfers, and a guard failure
  falls back to the approved line.
- Live rehearsal on hawlak.app before calling step 4 or 5 done: a real call, a
  red-flag answer, the responder phone rings, and a no-answer case.

## Decided by Haya

1. **Stopped medicines** stay in the voice note as one sentence ("stop taking X").
   They are the only medicine names the voice note may contain; the "no medicine
   name" check covers the dispensed medicines only.
2. **The call agent answers only from the approved voice note and reminders.** A
   question about a dose, a symptom or anything else not in them gets "I'll
   connect you with the care team" and a transfer.

## Calls made after the builder check (mine; Haya can overrule)

- **Every patient turn is classified**, not only the turns the model reports. The
  classifier gains a fifth kind, `question`, for "what do you mean?" or "can you
  repeat?". `red_flag` and `transfer_request` on any turn transfer at once.
  `question` or `uncertain` lets the model clarify once for the current
  question; a second one on the same question transfers. This keeps a warning
  sign said in passing from being missed, while still allowing one follow-up.
- **The responder must press 1 to accept** the warm transfer. Answering alone
  does not count, because a voicemail answers too. No key press within 30
  seconds counts as no answer: the patient hears the callback line and the
  outcome is `failed`.
- **No tap on the opener:** the opener is sent again once after 4 hours. After 24
  hours with no tap, a `patient_not_reached` alert (high) asks the care team to
  phone the patient. The held runs stay `pending`, and the dashboard shows the
  opener run's status next to them.
- **Closed-window reminder:** a Meta template whose body is a fixed prefix plus
  one variable holding the insurer-approved reminder script. The approved audio
  is not sent in that case. Dose and count come only from the approved script,
  as today.
- **"No medicine name in the voice note" is best effort:** it matches each
  medicine's first word and its approved Arabic display name. A transliteration
  it misses is caught by the reviewer, who approves every word.
- **Transcripts:** readable in the insurer workspace only, never in the hospital
  or caregiver views. Kept and deleted with the case. Retention stays an open
  item in the privacy doc.
- **Shipping order:** the API and agent ship first. The dashboard shows an
  unknown run kind by its raw name until Retaj adds the label and the transcript
  view.

## Left to the builder

- Exact prompt wording within the rules above.
- How the speech guard buffers sentences from the stream.
- The migration and model for call turns and run error codes.
- Hash format for logged message IDs.
