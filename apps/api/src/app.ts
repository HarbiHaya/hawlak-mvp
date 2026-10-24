import Fastify, { type FastifyInstance } from "fastify";
import type { AppConfig } from "./config/env.js";
import { demoRoutes } from "./routes/demo.js";
import { healthRoutes } from "./routes/health.js";
import { whatsappWebhookRoutes } from "./routes/whatsapp-webhook.js";

declare module "fastify" {
  interface FastifyRequest {
    rawBody: Buffer;
  }
}

export function buildApp(config: AppConfig): FastifyInstance {
  const app = Fastify({ logger: true });

  app.removeContentTypeParser("application/json");
  app.addContentTypeParser(
    "application/json",
    { parseAs: "buffer" },
    (request, body, done) => {
      try {
        const rawBody = body as Buffer;
        request.rawBody = rawBody;
        const parsed = JSON.parse(rawBody.toString("utf8"));
        done(null, parsed);
      } catch (error) {
        done(error as Error, undefined);
      }
    },
  );

  app.addHook("preValidation", async (request) => {
    if (!request.rawBody) {
      request.rawBody = Buffer.alloc(0);
    }
  });

  app.register(healthRoutes);
  app.register(whatsappWebhookRoutes, { config });
  app.register(demoRoutes, { config });

  return app;
}

