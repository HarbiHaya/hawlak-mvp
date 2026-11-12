# ADR 0003: Separate demo and Saudi production provider profiles

**Status:** Accepted
**Date:** 12 November 2026

## Context

The Medathon demonstration must place a real conversational call and send a real WhatsApp voice note. External providers make that achievable in the available time. A production Hawlak deployment processes health-related conversations and must meet the approved Saudi hosting, transfer, security, and clinical-governance design.

Using the same provider configuration for both environments would create two risks:

1. The demo could be blocked by production procurement and infrastructure.
2. External demo processors could accidentally remain enabled in a Saudi production deployment.

## Decision

Hawlak uses one domain workflow with two explicit provider profiles.

### `demo_external`

- GCP application runtime
- LiveKit conversational agent
- OpenAI conversation model
- tested demo speech recognition
- ElevenLabs Arabic TTS
- one Twilio or Telnyx SIP trunk
- Twilio Sandbox or Meta test sender
- synthetic data only

### `production_saudi`

- Saudi-hosted application, clinical data, LiveKit Server, LiveKit SIP, and agent workers
- locally deployed LLM, speech-to-text, and Arabic TTS models
- enterprise SIP or PRI service from stc, Zain, or another approved local carrier
- governed Meta boundary for minimum WhatsApp content

Provider behavior is accessed through typed seams. The clinical conversation state machine, approvals, call-plan versions, audit events, and transfer rules do not depend on a specific provider.

The process must fail startup when `production_saudi` resolves to an external demo model, speech, storage, or telephone adapter. There is no silent external fallback in production.

## Consequences

- The hackathon can demonstrate real calling without claiming production residency.
- Provider replacement remains localized to adapters.
- The team must test Saudi carrier interoperability, caller ID, SIP authentication, network connectivity, and transfer behavior before a pilot.
- Production needs a Saudi infrastructure and model-serving workstream.
- Demo findings about latency and Arabic quality are useful, but they do not validate the production provider stack.
