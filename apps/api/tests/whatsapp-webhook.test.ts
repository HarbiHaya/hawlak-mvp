import { createHmac } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import type { AppConfig } from "../src/config/env.js";

const config: AppConfig = {
  NODE_ENV: "test",
  PORT: 3000,
  META_GRAPH_API_VERSION: "v-test",
  WHATSAPP_PHONE_NUMBER_ID: "phone-id",
  WHATSAPP_ACCESS_TOKEN: "test-token",
  WHATSAPP_VERIFY_TOKEN: "test-verify-token-long-enough",
  META_APP_SECRET: "test-app-secret",
  WHATSAPP_TEST_RECIPIENT: "+966500000000",
};

const apps: ReturnType<typeof buildApp>[] = [];

afterEach(async () => {
  await Promise.all(apps.splice(0).map((app) => app.close()));
});

describe("WhatsApp webhook", () => {
  it("returns Meta's challenge for the configured verify token", async () => {
    const app = buildApp(config);
    apps.push(app);

    const response = await app.inject({
      method: "GET",
      url: "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=test-verify-token-long-enough&hub.challenge=12345",
    });

    expect(response.statusCode).toBe(200);
    expect(response.body).toBe("12345");
  });

  it("accepts a webhook only when the raw payload signature matches", async () => {
    const app = buildApp(config);
    apps.push(app);

    const payload = JSON.stringify({
      object: "whatsapp_business_account",
      entry: [{ changes: [{ value: { messages: [] } }] }],
    });
    const signature = createHmac("sha256", config.META_APP_SECRET)
      .update(payload)
      .digest("hex");

    const response = await app.inject({
      method: "POST",
      url: "/webhooks/whatsapp",
      headers: {
        "content-type": "application/json",
        "x-hub-signature-256": `sha256=${signature}`,
      },
      payload,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ received: true });
  });

  it("rejects an invalid webhook signature", async () => {
    const app = buildApp(config);
    apps.push(app);

    const response = await app.inject({
      method: "POST",
      url: "/webhooks/whatsapp",
      headers: {
        "content-type": "application/json",
        "x-hub-signature-256": "sha256=00",
      },
      payload: JSON.stringify({ entry: [] }),
    });

    expect(response.statusCode).toBe(401);
  });
});
