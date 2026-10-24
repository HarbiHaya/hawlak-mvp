export type WhatsAppClientOptions = {
  graphApiVersion: string;
  phoneNumberId: string;
  accessToken: string;
};

type GraphResponse = {
  messages?: Array<{ id: string }>;
  id?: string;
  error?: { message?: string; code?: number };
};

export class WhatsAppClient {
  constructor(private readonly options: WhatsAppClientOptions) {}

  private get messagesUrl(): string {
    return `https://graph.facebook.com/${this.options.graphApiVersion}/${this.options.phoneNumberId}/messages`;
  }

  private async graphRequest(url: string, init: RequestInit): Promise<GraphResponse> {
    const response = await fetch(url, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.options.accessToken}`,
        ...(init.headers ?? {}),
      },
    });

    const body = (await response.json()) as GraphResponse;
    if (!response.ok) {
      throw new Error(`Meta API ${response.status}: ${body.error?.message ?? "unknown error"}`);
    }
    return body;
  }

  async sendText(to: string, text: string): Promise<string> {
    const body = await this.graphRequest(this.messagesUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        recipient_type: "individual",
        to,
        type: "text",
        text: { preview_url: false, body: text },
      }),
    });

    const messageId = body.messages?.[0]?.id;
    if (!messageId) throw new Error("Meta accepted the request without returning a message ID");
    return messageId;
  }

  async uploadAudio(audio: Uint8Array, filename: string): Promise<string> {
    const form = new FormData();
    const audioBuffer = Uint8Array.from(audio).buffer;
    form.append("messaging_product", "whatsapp");
    form.append("type", "audio/ogg");
    form.append("file", new Blob([audioBuffer], { type: "audio/ogg" }), filename);

    const url = `https://graph.facebook.com/${this.options.graphApiVersion}/${this.options.phoneNumberId}/media`;
    const body = await this.graphRequest(url, { method: "POST", body: form });
    if (!body.id) throw new Error("Meta accepted the media upload without returning a media ID");
    return body.id;
  }

  async sendAudio(to: string, mediaId: string): Promise<string> {
    const body = await this.graphRequest(this.messagesUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        recipient_type: "individual",
        to,
        type: "audio",
        audio: { id: mediaId },
      }),
    });

    const messageId = body.messages?.[0]?.id;
    if (!messageId) throw new Error("Meta accepted the request without returning a message ID");
    return messageId;
  }
}

