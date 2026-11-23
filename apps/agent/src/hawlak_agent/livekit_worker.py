from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import re
from collections.abc import AsyncIterable, AsyncIterator, Coroutine
from typing import Any

from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    ChatMessage,
    JobContext,
    cli,
    get_job_context,
)
from livekit.agents.llm import StopResponse
from livekit.plugins import elevenlabs, openai

from .classifier import AnswerClassifier, ClassificationError, OpenAIAnswerClassifier
from .conversation import AnswerKind, CallAction, CallActionKind, CallConversation, CallPlan
from .outcome_client import CallOutcomeClient
from .plan_client import ApprovedPlanClient
from .settings import AgentSettings
from .speech_guard import agent_instructions, check_speech, directive
from .transfer import CareTeamHandoff

logger = logging.getLogger("hawlak-call-agent")
settings = AgentSettings.from_env()
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")
# Context for speech-to-text: short phone replies in the patient's language.
STT_PROMPTS = {
    "ar": "مكالمة متابعة طبية باللهجة السعودية بعد الخروج من المستشفى. "
    "الردود قصيرة غالباً مثل: لا، إيه، نعم، لا الحمد لله، ما فهمت.",
    "en": "A medical follow-up phone call after hospital discharge. Replies are often short, "
    "like yes, no, I'm fine, sorry what.",
}


class HawlakFollowUpAgent(Agent):
    """Code picks every step; the model phrases it, and the speech guard checks each sentence."""

    def __init__(
        self,
        *,
        plan: CallPlan,
        classifier: AnswerClassifier,
        participant_identity: str,
        outcome_client: CallOutcomeClient,
    ) -> None:
        super().__init__(
            instructions=agent_instructions(plan),
            llm=openai.LLM(
                model=settings.openai_llm_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            ),
        )
        self.conversation = CallConversation(plan)
        self._plan = plan
        self.classifier = classifier
        self.participant_identity = participant_identity
        self.outcome_client = outcome_client
        self._outcome_tasks: set[asyncio.Task[None]] = set()
        self._turns: list[dict[str, Any]] = []
        # Approved lines spoken word for word (scripts, transfer lines); the guard lets them pass.
        self._verbatim: set[str] = set()
        # The transfer that has started but not been reported yet; reported failed on hang-up.
        self._escalation: CallAction | None = None

    async def begin(self) -> None:
        await self._say(self.conversation.start().spoken_text)
        await self._say(self.conversation.next_question().spoken_text)

    async def _say(self, text: str) -> None:
        self._verbatim.add(text)
        await self.session.say(text, allow_interruptions=False)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        patient_text = (new_message.text_content or "").strip()
        answer = await self._classify(patient_text)
        self._add_turn("patient", patient_text, answerKind=answer.value)

        action = self.conversation.record_answer(answer)
        if action.kind in {CallActionKind.SPEAK, CallActionKind.CLARIFY}:
            # The model replies to this turn; the directive fixes what it must ask.
            turn_ctx.add_message(role="system", content=directive(action))
            return

        if action.kind is CallActionKind.TRANSFER:
            # Code decided; LiveKit's warm transfer runs in its own agent from here on.
            self._escalation = action
            self.session.update_agent(
                CareTeamHandoff(
                    self, action, sip_trunk_id=settings.livekit_sip_outbound_trunk_id, llm=self.llm
                )
            )
            raise StopResponse()

        await self._say(action.spoken_text)
        await self.finish(action)
        raise StopResponse()

    async def _classify(self, patient_text: str) -> AnswerKind:
        if not patient_text:
            return AnswerKind.NOT_HEARD
        try:
            return await self.classifier.classify(
                patient_text, question=self.conversation.current_question
            )
        except ClassificationError:
            return AnswerKind.UNCERTAIN

    def tts_node(self, text: AsyncIterable[str], model_settings):
        return Agent.default.tts_node(self, self._guarded(text), model_settings)

    def _allowed(self, sentence: str) -> bool:
        sentence = sentence.strip()
        return any(sentence in line for line in self._verbatim) or check_speech(
            sentence, self._plan
        )

    async def _guarded(self, text: AsyncIterable[str]) -> AsyncIterator[str]:
        """Speak sentence by sentence; the first one that fails becomes the approved question.

        ponytail: the chat history keeps the model's own wording, not the replacement.
        """
        spoken: list[str] = []
        guard = "ok"
        buffer = ""
        try:
            async for chunk in text:
                buffer += chunk
                *ready, buffer = _SENTENCE_END.split(buffer)
                for sentence in ready:
                    if not self._allowed(sentence):
                        guard = "replaced"
                        break
                    spoken.append(sentence)
                    yield sentence + " "
                if guard == "replaced":
                    break
            if guard == "ok" and buffer.strip():
                if self._allowed(buffer):
                    spoken.append(buffer)
                    yield buffer
                else:
                    guard = "replaced"
            if guard == "replaced":
                logger.warning("speech guard replaced a generated sentence")
                if fallback := self.conversation.current_question:
                    spoken.append(fallback)
                    yield fallback
        finally:
            if spoken:
                self._add_turn("agent", " ".join(s.strip() for s in spoken), guard=guard)

    def _add_turn(self, speaker: str, text: str, **extra: str) -> None:
        self._turns.append(
            {"seq": len(self._turns) + 1, "speaker": speaker, "text": text[:2000], **extra}
        )

    async def send_turns(self) -> None:
        """Store the transcript for the care team; the API skips turns it already has."""
        if not self._turns:
            return
        try:
            await self.outcome_client.record_turns(self._plan.id, list(self._turns))
        except Exception as exc:
            logger.error("call turns reporting failed", extra={"error_type": type(exc).__name__})

    async def finish(self, action: CallAction, *, transferred: bool = False) -> None:
        """Report the outcome and store the transcript. A transferred call stays open for the
        patient and the care team; any other call ends here."""
        self._escalation = None
        if action.kind is CallActionKind.COMPLETE:
            report = self.outcome_client.record_completed(self._plan.id)
        else:
            if action.question_id is None or action.answer_kind is None:
                raise ValueError("transfer action is missing its escalation outcome")
            record = (
                self.outcome_client.record_transferred
                if transferred
                else self.outcome_client.record_failed
            )
            report = record(
                self._plan.id, question_id=action.question_id, answer_kind=action.answer_kind
            )
        outcome_task = self._start_outcome_task(report)
        if transferred:
            await self._wait_for_outcome(outcome_task)
            await self.send_turns()
            return
        try:
            await self._attempt_end_call()
        finally:
            await self.send_turns()
            await self._wait_for_outcome(outcome_task)

    async def on_shutdown(self) -> None:
        """The patient hung up: a transfer still in progress counts as failed."""
        if (action := self._escalation) is not None:
            self._escalation = None
            with contextlib.suppress(Exception):
                await self.outcome_client.record_failed(
                    self._plan.id, question_id=action.question_id, answer_kind=action.answer_kind
                )
        await self.send_turns()

    async def _attempt_end_call(self) -> None:
        try:
            await self._end_call()
        except Exception as exc:
            logger.error(
                "room teardown failed",
                extra={"error_type": type(exc).__name__},
            )

    def _start_outcome_task(
        self,
        report: Coroutine[Any, Any, None],
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(report)
        self._outcome_tasks.add(task)
        task.add_done_callback(self._outcome_finished)
        return task

    def _outcome_finished(self, task: asyncio.Task[None]) -> None:
        self._outcome_tasks.discard(task)
        if task.cancelled():
            return
        if exc := task.exception():
            logger.error(
                "call outcome reporting failed",
                extra={"error_type": type(exc).__name__},
            )

    @staticmethod
    async def _wait_for_outcome(task: asyncio.Task[None]) -> None:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _end_call(self) -> None:
        ctx = get_job_context()
        await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


server = AgentServer()


@server.rtc_session(agent_name=settings.agent_name)
async def outbound_follow_up(ctx: JobContext) -> None:
    await ctx.connect()
    call_plan_id = settings.parse_job_metadata(ctx.job.metadata)
    plan = ApprovedPlanClient(
        settings.hawlak_api_base_url,
        settings.hawlak_internal_api_token,
    ).fetch(call_plan_id)
    identity_digest = hashlib.sha256(plan.id.encode()).hexdigest()[:20]
    participant_identity = f"patient-{identity_digest}"

    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=settings.livekit_sip_outbound_trunk_id,
                sip_call_to=plan.phone_e164,
                participant_identity=participant_identity,
                participant_name=plan.participant_label,
                wait_until_answered=True,
            )
        )
        await ctx.wait_for_participant(identity=participant_identity)
    except Exception as exc:
        logger.error("outbound call failed", extra={"error_type": type(exc).__name__})
        ctx.shutdown()
        return

    classifier = OpenAIAnswerClassifier(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_classifier_model,
    )
    agent = HawlakFollowUpAgent(
        plan=plan,
        classifier=classifier,
        participant_identity=participant_identity,
        outcome_client=CallOutcomeClient(
            settings.hawlak_api_base_url,
            settings.hawlak_internal_api_token,
        ),
    )
    language = plan.language.split("-")[0]
    session = AgentSession(
        stt=openai.STT(
            model=settings.openai_stt_model,
            language=language,
            prompt=STT_PROMPTS.get(language, STT_PROMPTS["en"]),
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        ),
        tts=elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model_id,
            language=language,
        ),
        turn_handling={
            # The transcript arrives after the pause; wait for it before taking the turn.
            "endpointing": {"min_delay": 0.8},
            # Code adds the step for each reply, so a reply drafted early is always thrown away.
            "preemptive_generation": {"enabled": False},
        },
    )
    ctx.add_shutdown_callback(agent.on_shutdown)  # a patient who hangs up mid-call or mid-transfer
    await session.start(agent=agent, room=ctx.room)
    await agent.begin()


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
