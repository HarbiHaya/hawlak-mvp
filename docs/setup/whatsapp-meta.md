# Configure the WhatsApp layer with Meta’s test number

This setup is for a synthetic Medathon demo. Do not use real patient data.

## 1. Create the Meta application

1. Open [Meta for Developers](https://developers.facebook.com/).
2. Create an app using a business-capable app type.
3. Add the **WhatsApp** product.
4. Open **WhatsApp → API Setup**.

Meta creates a test WhatsApp Business account and shows a test sender number. You do not need to buy a sender number for this prototype.

## 2. Add the test recipient

1. In the API Setup page, add Haya’s personal WhatsApp number as a recipient.
2. Enter the verification code received on that phone.
3. Keep the number in international E.164 format, for example `+9665XXXXXXXX`.

The Meta test number can send only to the verified recipients configured for the test environment.

## 3. Copy the required values

Copy `.env.example` to `.env`, then fill:

```dotenv
META_GRAPH_API_VERSION=<version shown in the Meta dashboard>
WHATSAPP_PHONE_NUMBER_ID=<test sender phone-number ID>
WHATSAPP_ACCESS_TOKEN=<temporary access token>
WHATSAPP_VERIFY_TOKEN=<a long random string you create>
META_APP_SECRET=<Settings → Basic → App secret>
WHATSAPP_TEST_RECIPIENT=+9665XXXXXXXX
INTERNAL_API_TOKEN=<a separate random string of at least 24 characters>
DASHBOARD_ORIGIN=http://localhost:5173
```

Do not commit `.env`. The temporary developer token is suitable for setup only and expires. Replace it with an appropriate system-user token before any sustained pilot.

## 4. Start the local API and isolated webhook

Keep the internal API local on port 3000:

```bash
npm run dev:api
```

In a second terminal, start the webhook-only app on port 3001:

```bash
npm run dev:webhook
```

The internal API contains authenticated demo and future dashboard routes. Do
not expose port 3000 through a tunnel. The port-3001 app contains only the Meta
webhook routes.

Confirm:

```bash
curl http://localhost:3000/health
```

Expose only the webhook app using an HTTPS tunnel, for example:

```bash
cloudflared tunnel --url http://localhost:3001
```

or:

```bash
ngrok http 3001
```

Use the generated HTTPS URL as `PUBLIC_BASE_URL`.

## 5. Register the webhook

In **WhatsApp → Configuration**:

1. Set callback URL to `https://YOUR-TUNNEL/webhooks/whatsapp`.
2. Enter exactly the same value as `WHATSAPP_VERIFY_TOKEN`.
3. Complete verification. Meta calls the GET route and expects the challenge string.
4. Subscribe the WhatsApp Business Account to the `messages` field.

The POST route verifies `X-Hub-Signature-256` using `META_APP_SECRET`. Never disable this check for a demo.

Confirm the tunnel does not expose internal routes:

```bash
curl -o /dev/null -w '%{http_code}\n' -X POST https://YOUR-TUNNEL/internal/demo/send-text
```

The expected status is `404`.

## 6. Send the first test message

Use Meta’s API Setup page to send the provided `hello_world` template to the verified recipient. Reply to it from the recipient phone to open the customer-service conversation.

Then test Hawlak’s outbound connection:

```bash
set -a
source .env
set +a
curl -X POST http://localhost:3000/internal/demo/send-text \
  -H "Authorization: Bearer $INTERNAL_API_TOKEN"
```

Expected response:

```json
{"messageId":"wamid...."}
```

## 7. Test inbound delivery

From the verified recipient phone:

1. Reply with a text message.
2. Send one synthetic medicine-box photo.
3. Watch the API logs for `WhatsApp inbound message accepted`.
4. Confirm the log contains a masked sender suffix, message ID, type, and media ID—never the token or full phone number.

## 8. Test the eventual voice-note flow

The final API sequence will be:

1. Send the AI-voice disclosure text.
2. Upload the approved `.ogg`/Opus file to `/{PHONE_NUMBER_ID}/media`.
3. Send an audio message referencing the returned media ID.
4. Send: `صور لنا علبة كل دواء عندك، وحدة وحدة.`
5. Receive images through the webhook.
6. Store each image once using the WhatsApp message ID as the idempotency key.
7. Emit `pharmacist_review_requested` after the expected count or the patient sends `تم`.

## 9. Demo preflight

- [ ] Temporary access token is still valid.
- [ ] Test recipient remains verified.
- [ ] Tunnel URL matches Meta configuration.
- [ ] Port 3000 remains local and the public tunnel targets only port 3001.
- [ ] The public tunnel returns 404 for `/internal/demo/send-text`.
- [ ] Webhook verification succeeds.
- [ ] `messages` subscription is enabled.
- [ ] Recipient has replied to the latest template message.
- [ ] Text send returns a WhatsApp message ID.
- [ ] Inbound image produces one webhook log.
- [ ] Replaying the same webhook does not create a duplicate once persistence is added.

## Official references

- [Meta’s official WhatsApp Business Platform workspace](https://www.postman.com/meta/whatsapp-business-platform/overview)
- [Meta’s official WhatsApp Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api)

