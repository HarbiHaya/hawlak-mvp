#!/usr/bin/env bash
# Run the script on stdin on the instance through Session Manager, wait, print its output.
# Usage: deploy/aws/ssm_run.sh INSTANCE_ID "comment" < script.sh
set -euo pipefail
INSTANCE="$1" COMMENT="$2"
PARAMS=$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()], "executionTimeout": ["3600"]}))')
ID=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --comment "$COMMENT" --timeout-seconds 600 --parameters "$PARAMS" --query Command.CommandId --output text)
while :; do
  sleep 5
  STATUS=$(aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending|InProgress|Delayed) continue ;; esac
  break
done
aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text | tail -40
[ "$STATUS" = "Success" ] || { echo "Remote command $STATUS" >&2; exit 1; }
