from __future__ import annotations

import hashlib
import logging

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
from .conversation import AnswerKind, CallActionKind, CallConversation, CallPlan
from .plan_client import ApprovedPlanClient
from .settings import AgentSettings

logger = logging.getLogger("hawlak-call-agent")
settings = AgentSettings.from_env()


class HawlakFollowUpAgent(Agent):
    """A voice shell around the approved deterministic conversation state machine."""

    def __init__(
        self,
        *,
        plan: CallPlan,
        classifier: AnswerClassifier,
        participant_identity: str,
    ) -> None:
        super().__init__(
            instructions=(
                "Do not produce patient-facing speech. Hawlak speaks only exact approved "
                "scripts. User turns are handled by the deterministic call workflow."
            ),
            llm=openai.responses.LLM(
                model=settings.openai_llm_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            ),
        )
        self.conversation = CallConversation(plan)
        self.classifier = classifier
        self.participant_identity = participant_identity

    async def begin(self) -> None:
        await self.session.say(
            self.conversation.start().spoken_text,
            allow_interruptions=False,
        )
        await self.session.say(
            self.conversation.next_question().spoken_text,
            allow_interruptions=False,
        )

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        del turn_ctx
        try:
            answer = await self.classifier.classify(new_message.text_content or "")
        except ClassificationError:
            answer = AnswerKind.UNCERTAIN

        action = self.conversation.record_answer(answer)
        await self.session.say(action.spoken_text, allow_interruptions=False)

        if action.kind is CallActionKind.TRANSFER:
            await self._transfer(action.transfer_to)
        elif action.kind is CallActionKind.COMPLETE:
            await self._end_call()
        raise StopResponse()

    async def _transfer(self, transfer_to: str | None) -> None:
        if not transfer_to:
            await self._end_call()
            return
        ctx = get_job_context()
        await ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=ctx.room.name,
                participant_identity=self.participant_identity,
                transfer_to=f"tel:{transfer_to}",
            )
        )

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
    )
    session = AgentSession(
        stt=openai.STT(
            model=settings.openai_stt_model,
            language=plan.language.split("-")[0],
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        ),
        tts=elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model_id,
            language=plan.language.split("-")[0],
        ),
    )
    await session.start(agent=agent, room=ctx.room)
    await agent.begin()


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
