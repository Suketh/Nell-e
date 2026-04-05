import { NELLIE_API_BASE, NELLIE_STT_BASE } from "@/src/config/env";
import type { FeatureAccessState, GalleryItem, ProfileSummary, ReplyResponse, VoiceProfile } from "@/src/types/api";

function withUser(path: string, userId: string): string {
  const url = new URL(`${NELLIE_API_BASE}${path}`);
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
  const response = await fetch(`${NELLIE_API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

export async function fetchFeatureAccess(userId: string): Promise<FeatureAccessState> {
  const payload = await getJson<{ feature_access: FeatureAccessState }>(withUser("/features", userId));
  return payload.feature_access;
}

export async function updateFeatureAccess(userId: string, featureId: string, enabled: boolean): Promise<FeatureAccessState> {
  const payload = await postJson<{ feature_access: FeatureAccessState }>("/features/update", {
    user_id: userId,
    feature_id: featureId,
    enabled,
  });
  return payload.feature_access;
}

export async function postDiagnosticEvent(
  userId: string,
  sessionId: string,
  event: Record<string, unknown>,
): Promise<void> {
  await postJson<{ ok: boolean }>("/diagnostics/event", {
    user_id: userId,
    session_id: sessionId,
    event,
  });
}

export async function adminSetLevel(userId: string, level: number): Promise<ProfileSummary> {
  return postJson<ProfileSummary>("/admin/progression", {
    user_id: userId,
    action: "set_level",
    level,
  });
}

export async function adminResetProgress(userId: string): Promise<ProfileSummary> {
  return postJson<ProfileSummary>("/admin/progression", {
    user_id: userId,
    action: "reset",
  });
}

export async function adminSetAllFeatures(userId: string, enabled: boolean): Promise<FeatureAccessState> {
  const payload = await postJson<{ feature_access: FeatureAccessState }>("/admin/features/all", {
    user_id: userId,
    enabled,
  });
  return payload.feature_access;
}

export async function sendReply(input: { userId: string; sessionId: string; text: string }): Promise<ReplyResponse> {
  return postJson<ReplyResponse>("/chat/reply", {
    user_id: input.userId,
    session_id: input.sessionId,
    text: input.text,
    user_text: input.text,
  });
}

const BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let output = "";
  for (let index = 0; index < bytes.length; index += 3) {
    const a = bytes[index] ?? 0;
    const b = bytes[index + 1] ?? 0;
    const c = bytes[index + 2] ?? 0;
    const chunk = (a << 16) | (b << 8) | c;
    output += BASE64_ALPHABET[(chunk >> 18) & 63];
    output += BASE64_ALPHABET[(chunk >> 12) & 63];
    output += index + 1 < bytes.length ? BASE64_ALPHABET[(chunk >> 6) & 63] : "=";
    output += index + 2 < bytes.length ? BASE64_ALPHABET[chunk & 63] : "=";
  }
  return output;
}

export function buildTtsUrl(text: string, userId?: string): string {
  const url = new URL(`${NELLIE_API_BASE}/tts`);
  url.searchParams.set("text", text);
  if (userId) {
    url.searchParams.set("user_id", userId);
  }
  return url.toString();
}

export async function fetchTtsAudioDataUri(text: string, userId?: string): Promise<{ uri: string; fetchMs: number }> {
  const startedAt = Date.now();
  const response = await fetch(`${NELLIE_API_BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      user_id: userId,
    }),
  });
  if (!response.ok) {
    throw new Error(`TTS failed: ${response.status}`);
  }
  const audioBuffer = await response.arrayBuffer();
  const mimeType = String(response.headers.get("Content-Type") || "audio/wav");
  return {
    uri: `data:${mimeType};base64,${arrayBufferToBase64(audioBuffer)}`,
    fetchMs: Date.now() - startedAt,
  };
}

export async function selectVoiceProfile(userId: string, voiceProfileId: string): Promise<ProfileSummary> {
  return postJson<ProfileSummary>("/voice-profile/select", {
    user_id: userId,
    voice_profile_id: voiceProfileId,
  });
}

const MOOD_ALIASES: Record<string, string> = {
  curious: "thoughtful",
  calm: "neutral",
  content: "happy",
  confused: "thoughtful",
  upset: "sad",
  frustrated: "annoyed",
  sleepy: "tired",
};

function normalizeMood(mood?: string): string {
  const value = (mood || "thoughtful").trim().toLowerCase();
  const normalized = MOOD_ALIASES[value] || value;
  return ["angry", "annoyed", "happy", "neutral", "sad", "thoughtful", "tired"].includes(normalized) ? normalized : "thoughtful";
}

export function buildMoodPortraitUrl(mood?: string): string {
  const normalized = normalizeMood(mood);
  return `${NELLIE_API_BASE}/assets/moods/${normalized}.png`;
}

export function buildGalleryAssetUrl(item: { filename?: string; image_path?: string; path?: string }): string | null {
  const filename = String(item.filename || item.image_path || item.path || "").trim();
  if (!filename) {
    return null;
  }
  const basename = filename.split(/[\\/]/).pop();
  if (!basename) {
    return null;
  }
  return `${NELLIE_API_BASE}/assets/gallery/${encodeURIComponent(basename)}`;
}

export async function transcribeAudioFile(fileUri: string, language = "auto"): Promise<string> {
  const formData = new FormData();
  formData.append("file", {
    uri: fileUri,
    name: "recording.m4a",
    type: "audio/mp4",
  } as never);

  const response = await fetch(`${NELLIE_STT_BASE}/transcribe`, {
    method: "POST",
    headers: {
      "X-STT-Language": language,
    },
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`STT failed: ${response.status}`);
  }
  const payload = (await response.json()) as { text?: string };
  return String(payload.text || "").trim();
}
