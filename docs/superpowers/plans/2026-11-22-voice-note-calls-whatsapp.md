# Voice note, calls and WhatsApp delivery: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instructions-only voice notes, WhatsApp delivery that reaches patients who
never messaged first, honest failed statuses, a warm transfer that only counts when
a person accepts, and a call agent that talks naturally inside approved content.

**Architecture:** API changes in `apps/api` (guard, prompt v5, held runs, opener
run, status webhook, call turns). Agent changes in `apps/agent`. Code stays the
authority on call progress: the classifier labels every patient turn, and
`CallConversation` decides the next step. The model only phrases that step, and a
speech guard checks every sentence before it is spoken.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy and Alembic, pytest, LiveKit Agents
(`livekit.agents`, `livekit.plugins.openai`, `elevenlabs`), WhatsApp Cloud API.

**Spec:** `docs/superpowers/specs/2026-11-22-voice-note-calls-whatsapp-design.md`

## Global Constraints

- Run all commands from the repo root, with
  `export UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv"` for the API.
  Use the agent's own venv for `apps/agent`.
- Branch: `haya/voice-calls-whatsapp`. Commit as Haya only, with no AI
  co-author line (AGENTS.md). Do not push.
- Stage only the files each task names. The working tree holds unrelated
  uncommitted work: `journey_delivery.py` changes, caregiver dashboard files,
  `docker-compose.aws.yml`, `deploy.sh`.
- Synthetic patients and fictional medicine names in every test.
- Never log a token, a full phone number or a raw `wamid`.
- Change a prompt by adding a new file. `journey-draft-v4.txt` stays unchanged.
- Done per task: `uv run --directory apps/api pytest`, `ruff check .` and
  `ruff format --check .` all pass (and the same for `apps/agent` when it changed).
- Don't touch `apps/dashboard` or `packages/contracts`. Those are Retaj's and
  need a reviewed PR.

## Review Focus

1. A Meta status for a reminder run whose `provider_ref` is `"voiceId,reminderId"`.
   The failure of either ID must fail the run. (Task 2 test)
2. A `failed` status followed by a late `delivered` for the same message. The run
   stays `failed`. (Task 2 test)
3. An inbound message from the caregiver opens no window: Meta's window is per
   recipient, and the patient is the recipient. (Task 4 test)
4. The patient says "my chest hurts" as an aside while asking "what do you
   mean?". The classifier returns `red_flag` and the call transfers, with no
   clarification. (Task 7 test)
5. The responder answers but never presses 1, as voicemail would. The outcome
   is `failed`, never `transferred`. (Task 6 test)

---

### Task 1: Commit the deployed parser fix

**Files:** `apps/api/app/services/discharge_parser.py`,
`apps/api/tests/test_discharge_parser.py` (already changed and live on hawlak.app).

- [ ] **Step 1:** `git switch -c haya/voice-calls-whatsapp`
- [ ] **Step 2:** `uv run --directory apps/api pytest tests/test_discharge_parser.py -q`. Expected: 7 passed.
- [ ] **Step 3:** Commit both files: `Read numbered section headings in discharge PDFs`.

### Task 2: Failed Meta status fails the delivery run; hashed message IDs in logs

**Files:**
- Modify: `apps/api/app/services/inbound_workflow.py` (`apply_delivery_status`)
- Modify: `apps/api/app/routes/whatsapp_webhook.py` (status loop and every log line with a `wamid`)
- Create: `apps/api/app/log_ids.py`
- Test: `apps/api/tests/test_whatsapp_webhook.py`, `apps/api/tests/test_inbound_workflow.py`

**Interfaces:**
- Produces: `log_id(wa_message_id: str) -> str`, the first 12 hex characters of
  sha256. `apply_delivery_status(wa_message_id: str, status: str | None, error_code: int | None = None) -> None`.

- [ ] **Step 1: Write failing tests**
  - `test_failed_status_fails_the_delivery_run_and_raises_an_alert`. The run has
    `status="sent"` and `provider_ref="wamid.A"`. Applying `("wamid.A", "failed", 131047)`
    gives `run.status == "failed"` and `run.provider_ref == "wamid.A|meta:131047"`,
    plus one open alert with `type == "delivery_failed"` and `severity == "medium"`.
  - `test_failed_status_matches_either_id_of_a_reminder_run`: `provider_ref="wamid.V,wamid.R"`, failing `wamid.R`, gives a failed run.
  - `test_later_delivered_status_does_not_undo_a_failure`.
  - `test_webhook_logs_never_contain_a_raw_wamid`: caplog over a status webhook;
    the raw ID is absent and `log_id(raw)` is present.
- [ ] **Step 2:** Run the four tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Match a run with `provider_ref == id`, or with `id`
  as one of the comma parts (filter in Python over the case's `sent` runs, found
  through `provider_ref LIKE '%' || id || '%'`). Only `failed` changes a run.
  Alert idempotency key: `f"{run.id}:delivery_failed"`. Keep the `MessageLog`
  update as it is.
- [ ] **Step 4:** Run the API suite. Expected: all pass.
- [ ] **Step 5:** Commit: `Mark a delivery run failed when Meta reports it failed`.

### Task 3: Voice note without medicines (prompt v5 and guard)

**Files:**
- Create: `apps/api/app/prompts/journey-draft-v5.txt`
- Modify: `apps/api/app/services/journey_drafter.py` (`PROMPT_PATH`, `TEXT`, `TemplateJourneyDrafter.draft`, `guard_draft`)
- Test: `apps/api/tests/test_journey_drafter.py`

**Interfaces:**
- Produces: `guard_draft(draft, extraction, medications)`, same signature with
  new rules. A new `TEXT` key `"medicines_elsewhere"`:
  - en: `"Your medicines come in separate messages, with a photo request and reminders."`
  - ar: `"أدويتك بتوصلك في رسائل لحالها، مع طلب صور العلب والتذكيرات."`

- [ ] **Step 1: Write failing tests**
  - `test_template_voice_note_has_no_medicines_but_keeps_stopped_ones`. The
    voice script contains no `displayName` from `medications`. It contains the
    stopped medicine and `TEXT[lang]["medicines_elsewhere"]`. Reminder scripts
    still contain each `displayName`.
  - `test_guard_accepts_an_arabic_voice_note_for_an_english_document`. An
    English extraction, with an Arabic voice script that has every section
    number and no medicine name, passes.
  - `test_guard_rejects_a_voice_note_that_names_a_dispensed_medicine`: first word
    of `displayName`, case-insensitive. Raises `DraftRejected("medicine in the voice note")`.
  - `test_guard_rejects_a_voice_note_that_drops_an_instruction_number`. The
    sections hold "2 g/day" and the script has no "2". Raises
    `DraftRejected("instruction number missing from the voice note")`.
  - `test_guard_still_rejects_a_reminder_without_its_medicine_name`.
  - Update existing tests that expect medicines in the voice script.
- [ ] **Step 2:** Run. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - Write v5 from v4. voiceScript is 80–160 words, in this order: greeting;
    stopped medicines in one sentence; each section in everyday words with no
    medical terms ("hemodialysis" becomes "الغسيل الكلوي", kidney dialysis);
    warning signs with the number; "medicines come separately"; closing.
  - Drop rule 2's voiceScript part and the medicine items from rule 5.
  - The self-check says no dispensed medicine name appears in voiceScript.
  - Point `PROMPT_PATH` to v5.
  - Template drafter: replace the medicine lines with `medicines_elsewhere`.
  - Guard: remove the two voice-note medicine checks, add the two new ones, and
    keep invented numbers and reminder names.
  - "Instruction numbers" means `_numbers()` over all section items.
- [ ] **Step 4:** Run the API suite. Expected: all pass.
- [ ] **Step 5:** Commit: `Voice note carries instructions only; medicines go to reminders and photos`.

### Task 4: WhatsApp opener and held runs

**Files:**
- Create: `apps/api/alembic/versions/20261122_0006_whatsapp_opener_run.py` (adds `'whatsapp_opener'` to `ck_delivery_runs_kind`)
- Modify: `apps/api/app/models.py` (constraint), `apps/api/app/config.py`, `apps/api/app/services/care_journey_service.py` (approval runs), `apps/api/app/services/journey_delivery.py` (`deliver`, `dispatch_due`, `_payload`), `.env.example`
- Test: `apps/api/tests/test_care_journey.py`, `apps/api/tests/test_migrations.py`, new `apps/api/tests/test_whatsapp_window.py`

**Interfaces:**
- Produces settings `whatsapp_opener_template: str | None` and
  `whatsapp_reminder_template: str | None`, the same shape as
  `whatsapp_photo_request_template`.
- Produces `window_open(session, case_id: str, now: datetime) -> bool`: true when
  the patient's (not the caregiver's) latest inbound `MessageLog` is under 24
  hours old.
- Run kind `whatsapp_opener`, with content refs `"opener"` (due at approval) and
  `"opener:2"` (due at approval + 4 h).

- [ ] **Step 1: Write failing tests** (`test_whatsapp_window.py`, mock adapter)
  - `test_approval_creates_two_openers_when_a_template_is_set`, and none when it is unset (today's behaviour).
  - `test_voice_note_waits_until_the_patient_writes`. Window closed: the voice
    note stays `pending` after `dispatch_due`, and the opener is `sent`. Add a
    patient inbound message and dispatch again: the voice note is `sent`.
  - `test_photo_request_with_a_template_does_not_wait`.
  - `test_second_opener_is_skipped_once_the_window_is_open`: status `completed`, nothing sent.
  - `test_caregiver_message_does_not_open_the_window`.
  - `test_patient_not_reached_alert_after_24_hours`. The voice note is still held
    24 h after approval: one `patient_not_reached` alert with severity `high`,
    idempotent across cycles.
  - `test_closed_window_reminder_goes_as_the_reminder_template`, with values `[reminderScript]`. Open window: audio as today.
  - `test_migration_allows_the_opener_kind`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Held kinds are `discharge_voice_note` and `photo_request` (when it has no
    template), plus `medication_reminder` when the window is closed and no
    reminder template is set.
  - `dispatch_due` skips held runs while `window_open` is false, leaving them `pending`.
  - The inbound path needs no change: the worker polls due runs every 10 s.
  - Opener delivery: `send_template(phone, opener_template, language, [])`.
    When `values` is empty, send no body component.
- [ ] **Step 4:** Run the API suite, then
  `uv run --directory apps/api alembic upgrade head` against local Postgres.
  Expected: pass, and the migration applies.
- [ ] **Step 5:** Commit: `Open the WhatsApp window with an approved template before sending the voice note`.

### Task 5: Store call turns

**Files:**
- Create: `apps/api/alembic/versions/20261122_0007_call_turns.py`
- Modify: `apps/api/app/models.py` (`CallTurn`), `apps/api/app/routes/care_journeys.py`, `apps/api/app/services/care_journey_service.py`
- Modify: `apps/agent/src/hawlak_agent/outcome_client.py`
- Test: `apps/api/tests/test_call_outcomes.py`, `apps/agent/tests/test_outcome_client.py`

**Interfaces:**
- `CallTurn` has `id`, `run_id` (FK `delivery_runs`, cascade), `seq: int`,
  `speaker: Literal["agent","patient"]`, `text: str`, `answer_kind: str | None`,
  `guard: Literal["ok","replaced"] | None` and `created_at`.
- `POST /internal/call-runs/{run_id}/turns` uses the internal token and an
  `Idempotency-Key`. Body: `{"turns": [{seq, speaker, text, answerKind, guard}]}`.
  Returns 202. The same key and body are a no-op.
- `GET /workspace/cases/{case_id}/calls/{run_id}/turns` uses insurer
  workspace auth only and returns `{"data": [...]}` ordered by `seq`.
- Agent: `CallOutcomeClient.record_turns(run_id: str, turns: list[dict]) -> None`.

- [ ] **Step 1: Write failing tests.**
  - API: post, then get, round-trips.
  - Hospital and caregiver tokens get 403 (or the existing forbidden error).
  - A repeated post is a no-op.
  - Turn text never appears in logs (caplog).
  - Agent: `record_turns` posts the body with retries, like the other `record_*` methods.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, following `record_call_outcome` for auth and idempotency.
- [ ] **Step 4:** Run both suites. Expected: pass.
- [ ] **Step 5:** Commit: `Store follow-up call turns for the care team`.

### Task 6: Warm transfer with press-1 acceptance

**Files:**
- Create: `apps/agent/src/hawlak_agent/transfer.py`
- Modify: `apps/agent/src/hawlak_agent/livekit_worker.py` (`_transfer` uses it, and REFER is removed)
- Test: `apps/agent/tests/test_transfer.py`, `apps/agent/tests/test_livekit_worker.py`

**Interfaces:**
- `async def warm_transfer(sip: SipControl, *, room: str, responder_e164: str, trunk_id: str, say: Callable[[str], Awaitable[None]], language: str, question_number: int, answer_timeout: float = 30, accept_timeout: float = 30) -> bool`
- `SipControl` is a Protocol with:
  - `dial(room, to, identity) -> None`, which raises on no answer;
  - `wait_for_digit(identity, digit, timeout) -> bool`;
  - `remove(room, identity) -> None`.

  The LiveKit implementation uses `create_sip_participant(wait_until_answered=True)`,
  the room's `sip_dtmf_received` event and `remove_participant`.
- `TRANSFER_LINES = {"ar": {...}, "en": {...}}` with keys `responder` and `callback`:
  - responder, en: `"Hawlak follow-up call. The patient raised a concern at question {n}. Press 1 to take the call."`
  - responder, ar: `"مكالمة متابعة من حولك. المريض ذكر مشكلة عند السؤال {n}. اضغط 1 لاستلام المكالمة."`
  - callback, en: `"I couldn't reach the care team right now. They will call you back shortly."`
  - callback, ar: `"ما قدرت أوصل لفريق الرعاية الحين. بيتصلون عليك قريب إن شاء الله."`

- [ ] **Step 1: Write failing tests** with a fake `SipControl`:
  - `test_transfer_counts_only_after_the_responder_presses_1`: returns True, and the responder line was said.
  - `test_voicemail_without_a_key_press_is_not_a_transfer`: returns False, the responder is removed, and the callback line is said.
  - `test_no_answer_is_not_a_transfer`.
  - Worker test: `record_transferred` only on True, `record_failed` on False, and
    `delete_room` is not called on success (the patient and responder stay connected).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. On success the agent leaves the room with
  `ctx.room.disconnect()` after `session.aclose()`.
- [ ] **Step 4:** Run the agent suite. Expected: pass.
- [ ] **Step 5:** Commit: `Warm-transfer follow-up calls and count a transfer only when the responder accepts`.

### Task 7: Natural call agent inside approved content

**Files:**
- Modify: `apps/agent/src/hawlak_agent/conversation.py`, `classifier.py`, `livekit_worker.py`, `plan_client.py`
- Create: `apps/agent/src/hawlak_agent/speech_guard.py`
- Modify: `apps/api/app/services/care_journey_service.py` (`call_plan` adds approved facts)
- Test: `apps/agent/tests/test_conversation.py`, `test_classifier.py`, new `test_speech_guard.py`, `test_livekit_worker.py`; `apps/api/tests/test_call_outcomes.py`

**Interfaces:**
- `AnswerKind.QUESTION = "question"`, the classifier's new enum value. The prompt
  adds: "Return question when the caller asks something or does not understand,
  unless the reply also reports a warning sign."
- `CallActionKind.CLARIFY`. `CallConversation.record_answer(answer)`:
  - `CLEAR`: next question.
  - `QUESTION` or `UNCERTAIN`, first time on this question: `CLARIFY`, with `question_id` set.
  - Second time: `TRANSFER`.
  - `RED_FLAG` or `TRANSFER_REQUEST`: `TRANSFER` at once.
- `CallPlan.approved_facts: tuple[str, ...]` (alias `approvedFacts`): the approved
  voice script and reminder scripts. `GET /internal/call-plans/{id}` adds `approvedFacts`.
- `directive(action: CallAction, plan: CallPlan, patient_text: str) -> str`, the
  per-turn instruction for the model:
  - next question: "Acknowledge briefly, then ask: <approved prompt>".
  - `CLARIFY`: "Answer only from the approved facts, or say the care team will
    help; then ask again: <approved prompt>".
- `check_speech(sentence: str, plan: CallPlan) -> bool`. Every number must be in
  the plan text (scripts, questions, facts), and a sentence is at most 40 words.
- Opening, completion, transfer and callback lines stay verbatim with `session.say`.

- [ ] **Step 1: Write failing tests.**
  - The state machine table above, one test per row.
  - `test_cannot_complete_before_every_question_is_answered`.
  - The Review Focus #4 classifier case, with a fake opener returning `red_flag` for the mixed reply.
  - `check_speech` rejects "take 3 tablets" when 3 is not in the plan, and
    rejects 41 words.
  - Worker with a fake LLM:
    - a guarded sentence is replaced by the current approved prompt and logged as a `replaced` turn;
    - turns are sent through `record_turns` at the end;
    - the LLM is `openai.LLM` (chat), not `openai.responses.LLM`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - In `on_user_turn_completed`, classify, then call `record_answer`.
  - For a speak or clarify step, add the directive as a system message to
    `turn_ctx` and return, so LiveKit generates the reply. For a terminal step,
    keep today's `say` and `StopResponse`.
  - Agent instructions: the role, the dialect, "never give advice", and the
    approved facts.
  - Guard sentences in an overridden `tts_node`, buffering to sentence ends.
- [ ] **Step 4:** Run both suites. Expected: pass.
- [ ] **Step 5:** Commit: `Let the follow-up call agent talk naturally inside approved content`.

### Task 8: Rules, privacy doc, README, deploy and rehearse

**Files:** `AGENTS.md`, `apps/agent/README.md`, `docs/architecture/platform-data-privacy.md`
(rows 4, 9 and 10, the boundary table rows for call providers, caregiver and logs,
and the status table), `README.md` Status.

- [ ] **Step 1:** Edit AGENTS.md:
  - The exact-script rule gets the call-agent exception: approved content is the
    only source of facts, and the speech guard and code-owned progress apply.
  - Add the photo-reply style fixed lines for transfers.
  - Add the WhatsApp opener rule.
- [ ] **Step 2:** Edit the agent README "never generated by the model" paragraph
  and the privacy rows. Transcripts are stored per call, insurer workspace only.
- [ ] **Step 3:** Full checks: the API and agent suites, then `npm run typecheck && npm test && npm run build`. Expected: all pass.
- [ ] **Step 4:** Commit: `Update rules and privacy doc for natural calls and the WhatsApp opener`.
- [ ] **Step 5: Deploy only on Haya's go-ahead**, after the templates are approved and
  their names set in SSM `/hawlak/demo/env`. Build the release from this branch's
  commits (not the dirty tree). Run migrations, then rehearse on hawlak.app:
  - an opener arrives, and tapping it brings the voice note and photo request;
  - a call with a red-flag answer rings 8908, and pressing 1 connects;
  - a no-answer call plays the callback line and shows `failed` with an alert;
  - a deliberately failed message shows "تعذّر الإرسال" (could not send).

## Handoff to Retaj (not in this plan)

- A dashboard label for `whatsapp_opener` and `patient_not_reached`.
- A read-only call transcript under the call run, from `GET /workspace/cases/{case_id}/calls/{run_id}/turns`.
- The contract update in `packages/contracts`, as a PR reviewed by both.
