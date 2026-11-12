#!/usr/bin/env bash
# Copy provider keys (WhatsApp, OpenAI, ElevenLabs, LiveKit and the provider mode) from the
# local .env into SSM /hawlak/demo/env, keep the server's own secrets, then redeploy.
# Refuses live mode while a required key is missing or still a placeholder (names only printed).
# Usage: deploy/aws/sync_keys.sh [--check]
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_PROFILE="${AWS_PROFILE:-hawlak}" AWS_REGION="${AWS_REGION:-eu-north-1}" AWS_PAGER=""
PARAM=/hawlak/demo/env

CURRENT=$(aws ssm get-parameter --name "$PARAM" --with-decryption --query Parameter.Value --output text)
MERGED=$(CURRENT="$CURRENT" python3 - .env <<'PY'
import os, re, sys

SYNCED = ("META_", "WHATSAPP_", "TWILIO_", "OPENAI_", "ELEVENLABS_", "LIVEKIT_",
          "DEMO_PROVIDER_MODE", "HAWLAK_AGENT_MODE")
LIVE = ["META_GRAPH_API_VERSION", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN",
        "META_APP_SECRET", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"]
CALLS = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_SIP_OUTBOUND_TRUNK_ID"]
PLACEHOLDER = re.compile(r"replace|change|example|your|xxx|placeholder|todo", re.I)


def parse(text):
    pairs = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            pairs[key.strip()] = value
    return pairs


def missing(env, keys):
    return [k for k in keys if not env.get(k) or PLACEHOLDER.search(env[k])]


env = parse(os.environ["CURRENT"])
env.update({k: v for k, v in parse(open(sys.argv[1]).read()).items() if k.startswith(SYNCED)})
live_gaps, call_gaps = missing(env, LIVE), missing(env, CALLS)
print("Live messaging keys missing: " + (", ".join(live_gaps) or "none"), file=sys.stderr)
print("Live call keys missing: " + (", ".join(call_gaps) or "none"), file=sys.stderr)
if env.get("DEMO_PROVIDER_MODE") == "live" and live_gaps:
    sys.exit("Refusing DEMO_PROVIDER_MODE=live until the messaging keys above are set in .env")
if env.get("DEMO_PROVIDER_MODE") == "live" and not call_gaps:
    env["HAWLAK_AGENT_MODE"] = "live"
    env["HAWLAK_AGENT_CONTROL_URL"] = "http://agent:3100"  # deploy.sh then starts the voice profile
else:
    env.pop("HAWLAK_AGENT_CONTROL_URL", None)
print("\n".join(f"{k}={v}" for k, v in env.items()))
PY
)
[ "${1:-}" = "--check" ] && exit 0
aws ssm put-parameter --name "$PARAM" --type SecureString --overwrite --value "$MERGED" >/dev/null
echo "Updated $PARAM (mode: $(grep '^DEMO_PROVIDER_MODE=' <<<"$MERGED" | cut -d= -f2))"
deploy/aws/deploy.sh
