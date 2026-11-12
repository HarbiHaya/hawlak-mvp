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

## Operating

- Shell: `aws ssm start-session --target <instance-id> --profile hawlak`
- Logs: `cd /opt/hawlak/current && docker compose -f docker-compose.aws.yml logs -f api`
- Stop the instance when not demoing to save credits; the Elastic IP keeps the origin stable.
