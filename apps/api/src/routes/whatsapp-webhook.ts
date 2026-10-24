import type { FastifyPluginAsync } from "fastify";
import type { AppConfig } from "../config/env.js";
import { verifyMetaSignature } from "../services/meta-signature.js";

type RouteOptions = { config: AppConfig };

type MetaWebhook = {
  entry?: Array<{
    changes?: Array<{
      value?: {
        messages?: Array<{
          id: string;
          from: string;
          type: string;
          text?: { body?: string };
          image?: { id?: string; mime_type?: string };
        }>;
        statuses?: Array<{ id: string; status: string }>;
      };
    }>;
  }>;
};

export const whatsappWebhookRoutes: FastifyPluginAsync<RouteOptions> = async (
  app,
  { config },
) => {
  app.get("/webhooks/whatsapp", async (request, reply) => {
    const query = request.query as Record<string, string | undefined>;
    if (
      query["hub.mode"] === "subscribe" &&
      query["hub.verify_token"] === config.WHATSAPP_VERIFY_TOKEN &&
      query["hub.challenge"]
    ) {
      return reply.type("text/plain").send(query["hub.challenge"]);
    }
    return reply.code(403).send({ error: "webhook_verification_failed" });
  });

  app.post("/webhooks/whatsapp", async (request, reply) => {
    const rawBody = request.rawBody;
    const signature = request.headers["x-hub-signature-256"] as string | undefined;

    if (!verifyMetaSignature(rawBody, signature, config.META_APP_SECRET)) {
      return reply.code(401).send({ error: "invalid_webhook_signature" });
    }

    const payload = request.body as MetaWebhook;
    const values = payload.entry?.flatMap((entry) => entry.changes ?? []).map((change) => change.value);
    const messages = values?.flatMap((value) => value?.messages ?? []) ?? [];
    const statuses = values?.flatMap((value) => value?.statuses ?? []) ?? [];

    for (const message of messages) {
      request.log.info(
        {
          whatsappMessageId: message.id,
          senderSuffix: message.from.slice(-4),
          messageType: message.type,
          mediaId: message.image?.id,
        },
        "WhatsApp inbound message accepted",
      );
      // Next milestone: persist with wa_message_id UNIQUE, then download image media.
    }

    for (const status of statuses) {
      request.log.info(
        { whatsappMessageId: status.id, deliveryStatus: status.status },
        "WhatsApp delivery status accepted",
      );
    }

    return reply.code(200).send({ received: true });
  });
};

