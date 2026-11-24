# AWS demo deployment

One EC2 instance (`hawlak-demo`, m7i-flex.large, Amazon Linux 2023) runs
`docker-compose.aws.yml`. CloudFront serves it over HTTPS; the instance accepts
port 80 from CloudFront only. There is no SSH: use Session Manager.

| Piece | Where |
|---|---|
| Dashboard and API | CloudFront domain printed by `provision.sh` (`/api/*`, `/webhooks/*`) |
| Uploaded PDFs and images | S3 `hawlak-demo-files-<account>-eu-north-1`, through the instance role |
| Secrets (`.env`) | SSM Parameter Store SecureString `/hawlak/demo/env` |
| Releases | S3 `hawlak-demo-deploy-<account>-eu-north-1/deployments/` |

```bash
deploy/aws/provision.sh   # once; safe to re-run
deploy/aws/deploy.sh      # every release: ships the working tree and rebuilds
```

## Going live

The stack runs in mock mode until real provider keys exist: runs are marked
"Simulated — not actually sent" and nothing reaches a phone.

1. Put the real values in the local `.env`: `META_GRAPH_API_VERSION`,
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `META_APP_SECRET`,
   `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, then
   `DEMO_PROVIDER_MODE=live`. For calls also the four `LIVEKIT_*` values.
2. `deploy/aws/sync_keys.sh --check` lists what is still missing (names only).
3. `deploy/aws/sync_keys.sh` copies the keys into SSM and redeploys. When the LiveKit
   keys are present it also starts the call agent.
4. In Meta's app settings set the webhook URL to `https://<cloudfront-domain>/webhooks/whatsapp`
   with the same `WHATSAPP_VERIFY_TOKEN`.

WhatsApp only delivers free-form voice notes inside the 24-hour window after the
patient last messaged the business number. For a demo, send any message from the test
phone to the business number first; production needs an approved message template.

## Monitoring

```bash
ALERT_EMAIL=you@example.com deploy/aws/monitoring.sh   # once; safe to re-run
deploy/aws/deploy.sh                                   # switches containers to the CloudWatch log driver
```

| Piece | What it watches |
|---|---|
| Log group `/hawlak/demo` (14 days) | One stream per container. Postgres logs stay on the instance |
| Alarm `hawlak-demo-errors` | 5+ ERROR, CRITICAL or Traceback lines in 5 minutes |
| Alarm `hawlak-demo-delivery-failed` | Any failed WhatsApp send or call dispatch (`Delivery run failed` log line) |
| Alarm `hawlak-demo-instance-status` | EC2 status check failing for 2 minutes |
| Alarm `hawlak-demo-cpu-high` | CPU at 85%+ for 15 minutes |
| Dashboard `hawlak-demo` | Alarm states, error and failure counts, CPU, and the latest 50 error lines |

Alarms email the SNS topic `hawlak-demo-alerts`; confirm the subscription email first.
Disk space is not watched (that needs the CloudWatch agent). An outside uptime check on
`https://<domain>/api/health` catches a stopped instance or a CloudFront problem.

## Operating

- Shell: `aws ssm start-session --target <instance-id> --profile hawlak`
- Logs: CloudWatch Logs `/hawlak/demo`, or on the instance
  `cd /opt/hawlak/current && docker compose -f docker-compose.aws.yml logs -f api`
- Stop the instance when not demoing to save credits; the Elastic IP keeps the origin stable.
