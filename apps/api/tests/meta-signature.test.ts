import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { verifyMetaSignature } from "../src/services/meta-signature.js";

describe("verifyMetaSignature", () => {
  it("accepts an authentic payload", () => {
    const body = Buffer.from('{"object":"whatsapp_business_account"}');
    const secret = "test-app-secret";
    const digest = createHmac("sha256", secret).update(body).digest("hex");

    expect(verifyMetaSignature(body, `sha256=${digest}`, secret)).toBe(true);
  });

  it("rejects a changed payload", () => {
    const original = Buffer.from('{"ok":true}');
    const changed = Buffer.from('{"ok":false}');
    const secret = "test-app-secret";
    const digest = createHmac("sha256", secret).update(original).digest("hex");

    expect(verifyMetaSignature(changed, `sha256=${digest}`, secret)).toBe(false);
  });
});

