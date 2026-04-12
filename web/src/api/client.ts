import type { GalleryItem, ProfileSummary, ReplyResponse } from "../types/api";

const API_BASE = (import.meta.env.VITE_NELLIE_API_BASE as string | undefined)?.replace(/\/+$/, "") || "/v1";
const STT_BASE = (import.meta.env.VITE_NELLIE_STT_BASE as string | undefined)?.replace(/\/+$/, "") || "/stt";

function withUser(path: string, userId: string): string {
  const url = new URL(`${API_BASE}${path}`);
  url.searchParams.set("user_id", userId);
  return url.toString();
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchProfileSummary(userId: string): Promise<ProfileSummary> {
  return getJson<ProfileSummary>(withUser("/profile-summary", userId));
}

export async function fetchGalleryCatalog(userId: string): Promise<GalleryItem[]> {
  const payload = await getJson<{ items: GalleryItem[] }>(withUser("/gallery/catalog", userId));
  return payload.items ?? [];
}

export async function fetchUnlockedGallery(userId: string): Promise<GalleryItem[]> {
  const payload = await getJson<{ items: GalleryItem[] }>(withUser("/gallery/unlocked", userId));
  return payload.items ?? [];
}

export async function sendReply(input: {
  userId: string;
  sessionId: string;
  text: string;
}): Promise<ReplyResponse> {
  return postJson<ReplyResponse>("/chat/reply", {
    user_id: input.userId,
    session_id: input.sessionId,
    text: input.text,
    user_text: input.text,
  });
}

export async function transcribePcmAudio(input: { pcm16: Int16Array; language?: string }): Promise<string> {
  const pcmBytes = new Uint8Array(input.pcm16.byteLength);
  pcmBytes.set(new Uint8Array(input.pcm16.buffer, input.pcm16.byteOffset, input.pcm16.byteLength));
  const body = new Blob([pcmBytes], {
    type: "application/octet-stream",
  });
  const response = await fetch(`${STT_BASE}/transcribe`, {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Audio-Format": "pcm_s16le",
      "X-Audio-Sample-Rate": "16000",
      "X-Audio-Channels": "1",
      ...(input.language && input.language !== "auto" ? { "X-STT-Language": input.language } : {}),
    },
    body,
  });
  if (!response.ok) {
    let detail = `STT request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string; error?: string };
      detail = payload.detail || payload.error || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  const payload = (await response.json()) as { text?: string };
  const text = String(payload.text || "").trim();
  if (!text) {
    throw new Error("STT returned an empty transcript.");
  }
  return text;
}

export async function fetchTtsAudio(input: { text: string }): Promise<Blob> {
  const response = await fetch(`${API_BASE}/tts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text: input.text }),
  });
  if (!response.ok) {
    let detail = `TTS request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { error?: string };
      detail = payload.error || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return await response.blob();
}
