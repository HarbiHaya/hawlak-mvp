import type { FastifyPluginAsync } from "fastify";
import type { AppConfig } from "../config/env.js";
import { WhatsAppClient } from "../services/whatsapp-client.js";

type RouteOptions = { config: AppConfig };

export const demoRoutes: FastifyPluginAsync<RouteOptions> = async (app, { config }) => {
  const client = new WhatsAppClient({
    graphApiVersion: config.META_GRAPH_API_VERSION,
    phoneNumberId: config.WHATSAPP_PHONE_NUMBER_ID,
    accessToken: config.WHATSAPP_ACCESS_TOKEN,
  });

  app.post("/internal/demo/send-text", async (_request, reply) => {
    const messageId = await client.sendText(
      config.WHATSAPP_TEST_RECIPIENT,
      "أهلًا من حولك. هذا اختبار الاتصال عبر واتساب.",
    );
    return reply.code(202).send({ messageId });
  });
};

