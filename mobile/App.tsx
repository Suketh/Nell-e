import { useEffect, useMemo, useState } from "react";
import { Image, Modal, Pressable, SafeAreaView, ScrollView, StatusBar, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from "react-native";
import Constants from "expo-constants";
import { Composer } from "./src/components/Composer";
import { FeatureAccessPanel } from "./src/components/FeatureAccessPanel";
import { MessageList } from "./src/components/MessageList";
import { MoodAvatar } from "./src/components/MoodAvatar";
import { ProfileBadge } from "./src/components/ProfileBadge";
import { BondCard } from "./src/components/BondCard";
import { GalleryGrid } from "./src/components/GalleryGrid";
import { adminResetProgress, adminSetAllFeatures, adminSetLevel, buildGalleryAssetUrl, fetchFeatureAccess, fetchGalleryCatalog, fetchProfileSummary, fetchTtsAudioDataUri, fetchUnlockedGallery, postDiagnosticEvent, selectVoiceProfile, sendReply, transcribeAudioFile, updateFeatureAccess } from "./src/api/client";
import { playRemoteAudio } from "./src/audio/player";
import { startNativeRecording, stopNativeRecording } from "./src/audio/recorder";
import { clearAuthSession, loadAuthSession, loginLocally } from "./src/store/auth";
import { createMobileProfile, loadActivePersonaId, loadActiveUserId, loadProfiles, saveActivePersonaId, saveActiveUserId, saveProfiles } from "./src/store/profile";
import { loadDiagnosticsEnabled, saveDiagnosticsEnabled } from "./src/store/diagnostics";
import { randomSessionId } from "./src/store/session";
import type { ChatMessage, FeatureAccessItem, FeatureAccessState, GalleryItem, MobileProfile, NelliePreference, PersonaProfile, ProfileSummary, VoiceProfile } from "./src/types/api";

type ScreenTab = "chat" | "gallery" | "bond" | "settings";
type VoicePhase = "idle" | "listening" | "transcribing" | "replying" | "generating_voice" | "playing";
type PresenceState = "idle" | "listening" | "thinking" | "speaking";
const MOOD_OPTIONS = ["happy", "neutral", "thoughtful", "sad", "annoyed", "angry", "tired"] as const;
type ReplyPlaybackPayload = {
  replyText: string;
  spokenReplyText: string;
  embeddedAudioUri?: string;
  embeddedTtsMs?: number;
  embeddedCacheHit?: boolean;
  ttsError?: string;
};

function buildSpokenReply(text: string): string {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  if (!compact) {
    return "";
  }
  const sentences = compact.match(/[^.!?]+[.!?]?/g) || [compact];
  const first = (sentences[0] || compact).trim();
  const second = (sentences[1] || "").trim();
  if (first.length >= 120 || !second) {
    return first.length <= 170 ? first : `${first.slice(0, 167).trimEnd()}...`;
  }
  const paired = `${first} ${second}`.trim();
  if (paired.length <= 150) {
    return paired;
  }
  return first.length <= 170 ? first : `${first.slice(0, 167).trimEnd()}...`;
}

function personaIntroCopy(persona: PersonaProfile): string {
  const id = String(persona.id || "").toLowerCase();
  if (id === "rolf") {
    return "A dry, steady male wizard voice with practical warmth. His path starts with voice and memory before gallery.";
  }
  if (id === "nellie") {
    return "A warmer voice-first companion with mood, memory, progression, and gallery beats.";
  }
  return persona.description || "A separate companion profile with its own memory, voice, and progression.";
}

function voicePhaseCopy(phase: VoicePhase, personaName: string): { label: string; detail: string } {
  if (phase === "listening") {
    return {
      label: "Listening now",
      detail: "Speak naturally. The recording is still on until you stop it.",
    };
  }
  if (phase === "transcribing") {
    return {
      label: "Turning voice into text",
      detail: "Your recording is being transcribed before it is sent to the companion.",
    };
  }
  if (phase === "replying") {
    return {
      label: `${personaName} is thinking`,
      detail: "The text reply is being prepared first, so the conversation should not feel stuck on voice generation.",
    };
  }
  if (phase === "generating_voice") {
    return {
      label: "Generating voice",
      detail: "The text reply is ready. The voice can take a little longer, especially for longer answers.",
    };
  }
  if (phase === "playing") {
    return {
      label: "Voice is playing",
      detail: "The generated voice is ready. Longer replies may take longer before this step begins.",
    };
  }
  return {
    label: "Voice ready",
    detail: "Use text for precision, or voice when you want the exchange to feel more direct.",
  };
}

function voiceUnavailableHint(error: unknown, fallback = "Voice playback failed."): string {
  const text = error instanceof Error ? error.message : fallback;
  const normalized = text.toLowerCase();
  if (normalized.includes("tts") || normalized.includes("voice")) {
    return `Voice unavailable. Text reply is ready. ${text}`;
  }
  return text;
}

function mergeSummary(current: ProfileSummary | null, incoming: Partial<ProfileSummary> | null | undefined, userId: string, sessionId = ""): ProfileSummary | null {
  if (!incoming) {
    return current;
  }
  const base: ProfileSummary = current || {
    user_id: userId,
    session_id: sessionId,
    progress: {
      xp: 0,
      level: 0,
      stage: "Anonymous",
    },
    gallery_unlock_count: 0,
  };
  return {
    ...base,
    ...incoming,
    user_id: incoming.user_id || base.user_id || userId,
    session_id: incoming.session_id || base.session_id || sessionId,
    progress: incoming.progress || base.progress,
    feature_access: incoming.feature_access ?? base.feature_access,
    gallery_unlock_count:
      typeof incoming.gallery_unlock_count === "number" ? incoming.gallery_unlock_count : base.gallery_unlock_count,
    latest_unlock: incoming.latest_unlock ?? base.latest_unlock,
    enabled_feature_labels: incoming.enabled_feature_labels ?? base.enabled_feature_labels,
    available_feature_labels: incoming.available_feature_labels ?? base.available_feature_labels,
    next_feature_unlock: incoming.next_feature_unlock ?? base.next_feature_unlock,
    stage_copy: incoming.stage_copy ?? base.stage_copy,
    practical_focus: incoming.practical_focus ?? base.practical_focus,
    suggested_prompts: incoming.suggested_prompts ?? base.suggested_prompts,
    nellie_preferences: incoming.nellie_preferences ?? base.nellie_preferences,
    voice_profiles: incoming.voice_profiles ?? base.voice_profiles,
    selected_voice_profile: incoming.selected_voice_profile ?? base.selected_voice_profile,
    persona_id: incoming.persona_id ?? base.persona_id,
    persona_profiles: incoming.persona_profiles ?? base.persona_profiles,
    selected_persona: incoming.selected_persona ?? base.selected_persona,
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ScreenTab>("chat");
  const [profiles, setProfiles] = useState<MobileProfile[]>([]);
  const [activeUserId, setActiveUserId] = useState("guest");
  const [activePersonaId, setActivePersonaId] = useState("nellie");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUserId, setAuthUserId] = useState("guest");
  const [authPersonaId, setAuthPersonaId] = useState("nellie");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [newProfileName, setNewProfileName] = useState("");
  const [summary, setSummary] = useState<ProfileSummary | null>(null);
  const [featureAccess, setFeatureAccess] = useState<FeatureAccessState | null>(null);
  const [catalog, setCatalog] = useState<GalleryItem[]>([]);
  const [unlocked, setUnlocked] = useState<GalleryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceBusy, setIsVoiceBusy] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [voiceHint, setVoiceHint] = useState("Mobile shell is live. Voice-to-voice is the next bridge.");
  const [voiceDraft, setVoiceDraft] = useState("");
  const [voiceDraftVisible, setVoiceDraftVisible] = useState(false);
  const [selectedGalleryItem, setSelectedGalleryItem] = useState<GalleryItem | null>(null);
  const [pendingFeatureId, setPendingFeatureId] = useState<string | null>(null);
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(false);
  const [adminBusy, setAdminBusy] = useState(false);
  const [adminMoodPreview, setAdminMoodPreview] = useState<string | null>(null);
  const [sessionId] = useState(() => randomSessionId());

  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.userId === activeUserId) || { userId: "guest", displayName: "Guest", badgeColor: "#f2c14e" },
    [profiles, activeUserId],
  );
  const isAdminProfile = Boolean(activeProfile?.isAdmin || activeProfile?.userId === "admin-mobile");
  const isExpoGo = Constants.executionEnvironment === "storeClient";
  const unsupportedFeatureIds = useMemo(
    () => (isExpoGo ? new Set(["device_timers", "device_alarms"]) : new Set<string>()),
    [isExpoGo],
  );
  const voiceProfiles = summary?.voice_profiles ?? [];
  const selectedVoiceProfile = summary?.selected_voice_profile ?? null;
  const personaProfiles: PersonaProfile[] = summary?.persona_profiles?.length
    ? summary.persona_profiles
    : [
        { id: "nellie", name: "Nellie", description: "Warm, nerdy, voice-first companion." },
        { id: "rolf", name: "Rolf", description: "Male wizard companion with dry practical warmth." },
      ];
  const activePersona = personaProfiles.find((persona) => persona.id === activePersonaId) || personaProfiles[0];
  const authPersona = personaProfiles.find((persona) => persona.id === authPersonaId) || personaProfiles[0];
  const presenceState: PresenceState =
    voicePhase === "listening"
      ? "listening"
      : voicePhase === "transcribing" || voicePhase === "replying" || voicePhase === "generating_voice"
        ? "thinking"
        : voicePhase === "playing"
          ? "speaking"
          : "idle";
  const voicePhaseLabel = voicePhaseCopy(voicePhase, activePersona?.name || "Nellie");

  useEffect(() => {
    async function boot() {
      const loadedProfiles = await loadProfiles();
      const storedUser = await loadActiveUserId();
      const storedPersona = await loadActivePersonaId();
      const storedDiagnostics = await loadDiagnosticsEnabled();
      const session = await loadAuthSession();
      const nextUserId = session?.userId || storedUser || loadedProfiles[0]?.userId || "guest";
      const nextPersonaId = storedPersona || "nellie";
      setProfiles(loadedProfiles);
      setAuthUserId(nextUserId);
      setAuthPersonaId(nextPersonaId);
      setActiveUserId(nextUserId);
      setActivePersonaId(nextPersonaId);
      setDiagnosticsEnabled(storedDiagnostics);
      if (session?.userId) {
        setIsAuthenticated(true);
        await refreshForUser(nextUserId, nextPersonaId);
      }
    }

    void boot();
  }, []);

  async function refreshForUser(userId: string, personaId = activePersonaId) {
    const startedAt = Date.now();
    try {
      const [nextSummary, nextCatalog, nextUnlocked] = await Promise.all([
        fetchProfileSummary(userId, personaId),
        fetchGalleryCatalog(userId, personaId),
        fetchUnlockedGallery(userId, personaId),
      ]);
      setSummary(nextSummary);
      setFeatureAccess(nextSummary.feature_access ?? (await fetchFeatureAccess(userId, personaId)));
      setCatalog(nextCatalog);
      setUnlocked(nextUnlocked);
      void logDiagnostic("refresh_profile", { ok: true, ms: Date.now() - startedAt });
    } catch (error) {
      const text = error instanceof Error ? error.message : "Could not reach the companion service.";
      setVoiceHint(text);
      void logDiagnostic("refresh_profile", { ok: false, ms: Date.now() - startedAt, error: text });
    }
  }

  async function logDiagnostic(type: string, payload: Record<string, unknown> = {}) {
    if (!diagnosticsEnabled) {
      return;
    }
    try {
      await postDiagnosticEvent(activeUserId, activePersonaId, sessionId, {
        type,
        platform: "expo-mobile",
        ts: Date.now(),
        ...payload,
      });
    } catch {
      // diagnostics must never break the app flow
    }
  }

  async function handleSend(text: string, options?: { includeTtsAudio?: boolean }): Promise<ReplyPlaybackPayload | null> {
    const startedAt = Date.now();
    setIsSending(true);
    setMessages((current) => [...current, { id: `${Date.now()}-user`, role: "user", text }]);
    const enabledFeatureIds = new Set(featureAccess?.enabled_ids ?? []);
    let phoneActionLine = "";
    try {
      let phoneAction = null;
      const canRunPhoneActions = !isExpoGo && (enabledFeatureIds.has("device_timers") || enabledFeatureIds.has("device_alarms"));
      if (canRunPhoneActions) {
        const module = await import("./src/device/phone_actions");
        phoneAction = await module.maybeRunPhoneAction(text, enabledFeatureIds);
      }
      if (phoneAction) {
        phoneActionLine = phoneAction.spoken;
        setVoiceHint(phoneAction.hint);
      }
      const response = await sendReply({ userId: activeUserId, personaId: activePersonaId, sessionId, text, includeTtsAudio: options?.includeTtsAudio });
      setSummary((current) =>
        mergeSummary(
          current,
          {
            user_id: activeUserId,
            session_id: sessionId,
            progress: response.progress,
            feature_access: response.feature_access,
            gallery_unlock_count: response.gallery_unlock_count,
            latest_unlock: response.latest_unlock,
            enabled_feature_labels: response.enabled_feature_labels,
            available_feature_labels: response.available_feature_labels,
            next_feature_unlock: response.next_feature_unlock,
            stage_copy: response.stage_copy,
            practical_focus: response.practical_focus,
            suggested_prompts: response.suggested_prompts,
            nellie_preferences: response.nellie_preferences,
          },
          activeUserId,
          sessionId,
        ),
      );
      if (response.feature_access) {
        setFeatureAccess(response.feature_access);
      }
      const replyText = phoneActionLine ? `${response.reply}\n\n${phoneActionLine}` : response.reply;
      const spokenReplyText = String(response.spoken_reply || "").trim() || buildSpokenReply(replyText);
      const embeddedAudioUri = response.tts_audio_base64
        ? `data:${response.tts_audio_content_type || "audio/wav"};base64,${response.tts_audio_base64}`
        : undefined;
      const embeddedTtsError = String(response.tts_error?.message || "").trim();
      if (embeddedTtsError && options?.includeTtsAudio) {
        setVoiceHint(embeddedTtsError);
      }
      setMessages((current) => [
        ...current,
        { id: `${Date.now()}-assistant`, role: "assistant", text: replyText, spokenText: spokenReplyText, mood: response.mood },
      ]);
      const hasNewUnlock = Boolean(response.new_unlock && Object.keys(response.new_unlock).length);
      if (hasNewUnlock) {
        void refreshForUser(activeUserId, activePersonaId);
      }
      void logDiagnostic("chat_reply", {
        ok: true,
        ms: Date.now() - startedAt,
        mood: response.mood,
        text_chars: text.length,
        reply_chars: replyText.length,
        phone_action: Boolean(phoneActionLine),
        embedded_tts: Boolean(embeddedAudioUri),
        embedded_tts_error: embeddedTtsError || undefined,
      });
      return {
        replyText,
        spokenReplyText,
        embeddedAudioUri,
        embeddedTtsMs: response.tts_meta?.tts_ms,
        embeddedCacheHit: response.tts_meta?.cache_hit,
        ttsError: embeddedTtsError || undefined,
      };
    } catch (error) {
      const text = error instanceof Error ? error.message : "Reply failed.";
      setMessages((current) => [...current, { id: `${Date.now()}-error`, role: "assistant", text, mood: "annoyed" }]);
      void logDiagnostic("chat_reply", { ok: false, ms: Date.now() - startedAt, error: text });
      return null;
    } finally {
      setIsSending(false);
    }
  }

  async function handlePlayLastReply() {
    const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
    const personaName = activePersona?.name || "Nellie";
    if (!lastAssistant) {
      setVoiceHint(`No ${personaName} reply to play yet.`);
      return;
    }
    const startedAt = Date.now();
    setIsPlayingVoice(true);
    try {
      const spokenText = String(lastAssistant.spokenText || "").trim() || buildSpokenReply(lastAssistant.text);
      setVoicePhase("generating_voice");
      setVoiceHint(`Generating ${personaName}'s voice...`);
      const audio = await fetchTtsAudioDataUri(spokenText, activeUserId, activePersonaId);
      setVoicePhase("playing");
      setVoiceHint(`Playing ${personaName}'s voice...`);
      const playback = await playRemoteAudio(audio.uri);
      setVoiceHint("Voice playback finished.");
      void logDiagnostic("tts_play", {
        ok: true,
        ms: Date.now() - startedAt,
        chars: spokenText.length,
        tts_fetch_ms: audio.fetchMs,
        audio_load_ms: playback.loadMs,
        audio_play_ms: playback.playMs,
      });
    } catch (error) {
      const text = voiceUnavailableHint(error, "Voice playback failed.");
      setVoiceHint(text);
      void logDiagnostic("tts_play", { ok: false, ms: Date.now() - startedAt, error: text });
    } finally {
      setIsPlayingVoice(false);
      setVoicePhase("idle");
    }
  }

  async function playReplyAudio(payload: ReplyPlaybackPayload): Promise<{ totalMs: number; fetchMs: number; loadMs: number; playMs: number; cacheHit?: boolean }> {
    const startedAt = Date.now();
    const personaName = activePersona?.name || "Nellie";
    if (payload.embeddedAudioUri) {
      setVoicePhase("playing");
      setVoiceHint(`Playing ${personaName}'s voice...`);
      const playback = await playRemoteAudio(payload.embeddedAudioUri);
      return {
        totalMs: Date.now() - startedAt,
        fetchMs: payload.embeddedTtsMs ?? 0,
        loadMs: playback.loadMs,
        playMs: playback.playMs,
        cacheHit: payload.embeddedCacheHit,
      };
    }
    if (payload.ttsError) {
      throw new Error(payload.ttsError);
    }
    setVoicePhase("generating_voice");
    setVoiceHint(`Generating ${personaName}'s voice...`);
    const audio = await fetchTtsAudioDataUri(payload.spokenReplyText, activeUserId, activePersonaId);
    setVoicePhase("playing");
    setVoiceHint(`Playing ${personaName}'s voice...`);
    const playback = await playRemoteAudio(audio.uri);
    return {
      totalMs: Date.now() - startedAt,
      fetchMs: audio.fetchMs,
      loadMs: playback.loadMs,
      playMs: playback.playMs,
    };
  }

  function startReplyAudioInBackground(
    payload: ReplyPlaybackPayload,
    diagnosticType: "voice_review_send" | "voice_roundtrip",
    diagnosticPayload: Record<string, unknown>,
  ) {
    setIsPlayingVoice(true);
    void (async () => {
      try {
        const playback = await playReplyAudio(payload);
        setVoiceHint("Voice reply complete.");
        void logDiagnostic(diagnosticType, {
          ok: true,
          ...diagnosticPayload,
          spoken_chars: payload.spokenReplyText.length,
          tts_ms: playback.totalMs,
          tts_fetch_ms: playback.fetchMs,
          audio_load_ms: playback.loadMs,
          audio_play_ms: playback.playMs,
          cache_hit: playback.cacheHit,
        });
      } catch (error) {
        const text = voiceUnavailableHint(error, "Voice playback failed.");
        setVoiceHint(text);
        void logDiagnostic(diagnosticType, { ok: false, ...diagnosticPayload, error: text });
      } finally {
        setIsPlayingVoice(false);
        setVoicePhase("idle");
      }
    })();
  }

  async function handleVoiceDraftSend() {
    const transcript = voiceDraft.trim();
    if (!transcript) {
      setVoiceHint("Edit the question first, or try recording again.");
      return;
    }
    setVoiceDraftVisible(false);
    setIsVoiceBusy(true);
    let voiceContinuesInBackground = false;
    try {
      const personaName = activePersona?.name || "Nellie";
      setVoicePhase("replying");
      setVoiceHint(`Sending corrected question to ${personaName}...`);
      const replyPayload = await handleSend(transcript, { includeTtsAudio: false });
      if (replyPayload) {
        voiceContinuesInBackground = true;
        startReplyAudioInBackground(replyPayload, "voice_review_send", {
          transcript_chars: transcript.length,
        });
      }
    } catch (error) {
      const text = voiceUnavailableHint(error, "Voice review send failed.");
      setVoiceHint(text);
      void logDiagnostic("voice_review_send", { ok: false, error: text });
    } finally {
      setIsVoiceBusy(false);
      if (!voiceContinuesInBackground) {
        setVoicePhase("idle");
      }
      setVoiceDraft("");
    }
  }

  function handleVoiceDraftRetry() {
    setVoiceDraft("");
    setVoiceDraftVisible(false);
    setVoicePhase("idle");
    setVoiceHint("Try recording that again.");
    void logDiagnostic("voice_review_retry", { ok: true });
  }

  async function handleVoiceShell() {
    const voiceStartedAt = Date.now();
    let voiceContinuesInBackground = false;
    try {
      if (!isRecording) {
        await startNativeRecording();
        setIsRecording(true);
        setVoicePhase("listening");
        setVoiceHint("Listening...");
        void logDiagnostic("voice_start", { ok: true });
        return;
      }
      setIsVoiceBusy(true);
      const uri = await stopNativeRecording();
      setIsRecording(false);
      if (!uri) {
        setVoicePhase("idle");
        setVoiceHint("Recording stopped.");
        return;
      }
      setVoicePhase("transcribing");
      setVoiceHint("Transcribing...");
      const sttStartedAt = Date.now();
      const transcript = await transcribeAudioFile(uri, "auto");
      if (!transcript) {
        setVoicePhase("idle");
        setVoiceHint("I couldn't hear enough to transcribe that.");
        void logDiagnostic("voice_transcribe", { ok: false, ms: Date.now() - sttStartedAt, reason: "empty_transcript" });
        return;
      }
      void logDiagnostic("voice_transcribe", { ok: true, ms: Date.now() - sttStartedAt, chars: transcript.length });
      const personaName = activePersona?.name || "Nellie";
      setVoicePhase("replying");
      setVoiceHint(`Sending to ${personaName}...`);
      const replyPayload = await handleSend(transcript, { includeTtsAudio: false });
      if (replyPayload) {
        voiceContinuesInBackground = true;
        startReplyAudioInBackground(replyPayload, "voice_roundtrip", {
          total_ms: Date.now() - voiceStartedAt,
          transcript_chars: transcript.length,
        });
      }
      return;
    } catch (error) {
      setIsRecording(false);
      const text = voiceUnavailableHint(error, "Native recording failed.");
      setVoiceHint(text);
      void logDiagnostic("voice_roundtrip", { ok: false, total_ms: Date.now() - voiceStartedAt, error: text });
    } finally {
      setIsVoiceBusy(false);
      if (!voiceContinuesInBackground) {
        setVoicePhase("idle");
      }
    }
  }

  const currentMood = adminMoodPreview || messages[messages.length - 1]?.mood || "thoughtful";
  const level = summary?.progress.level ?? 0;
  const xp = summary?.progress.xp ?? 0;
  const xpIntoLevel = Math.max(0, summary?.progress.xp_into_level ?? 0);
  const xpForNextLevel = Math.max(0, summary?.progress.xp_for_next_level ?? 0);
  const xpToNextLevel = Math.max(0, summary?.progress.xp_to_next_level ?? 0);
  const heroProgress = xpForNextLevel > 0 ? Math.max(0, Math.min(1, xpIntoLevel / xpForNextLevel)) : 1;
  const nextGallery = summary?.progress && typeof summary.progress.next_gallery_unlock === "object" ? summary.progress.next_gallery_unlock : null;
  const nextTool = summary?.progress && typeof summary.progress.next_tool_unlock === "object" ? summary.progress.next_tool_unlock : null;
  const journeyCopy = summary?.stage_copy || journeyDescription(summary?.progress.stage || "Anonymous", activePersona?.name || "Your companion");
  const practicalFocus =
    summary?.practical_focus || `As ${activePersona?.name || "your companion"} levels up, the bond should translate into more useful things they can actually do for you.`;
  const enabledFeatureLabels = summary?.enabled_feature_labels ?? [];
  const availableFeatureLabels = summary?.available_feature_labels ?? [];
  const nextFeatureUnlock = summary?.next_feature_unlock ?? null;
  const suggestedPrompts = summary?.suggested_prompts ?? [];
  const nelliePreferences = summary?.nellie_preferences ?? [];
  const unlockedItems = useMemo(
    () => unlocked.filter((item) => item && (item.image_path || item.filename || item.path)),
    [unlocked],
  );
  const lockedCount = Math.max(0, catalog.length - unlockedItems.length);
  const galleryAvailable = catalog.length > 0 || unlockedItems.length > 0 || Boolean(nextGallery);
  const selectedGalleryImageUrl = selectedGalleryItem ? buildGalleryAssetUrl(selectedGalleryItem) : null;

  async function handleComposerSend(text: string): Promise<void> {
    await handleSend(text);
  }

  async function handleFeatureToggle(item: FeatureAccessItem, enabled: boolean): Promise<void> {
    setPendingFeatureId(item.id);
    try {
      const nextFeatureAccess = await updateFeatureAccess(activeUserId, activePersonaId, item.id, enabled);
      setFeatureAccess(nextFeatureAccess);
      setVoiceHint(enabled ? `${item.label} is now enabled for ${activePersona?.name || "this persona"}.` : `${item.label} is now disabled for ${activePersona?.name || "this persona"}.`);
      void logDiagnostic("feature_toggle", { feature_id: item.id, enabled });
      await refreshForUser(activeUserId, activePersonaId);
    } catch (error) {
      setVoiceHint(error instanceof Error ? error.message : "Feature update failed.");
    } finally {
      setPendingFeatureId(null);
    }
  }

  async function handleDiagnosticsToggle(enabled: boolean) {
    setDiagnosticsEnabled(enabled);
    await saveDiagnosticsEnabled(enabled);
    setVoiceHint(enabled ? "Diagnostics enabled for this phone." : "Diagnostics disabled for this phone.");
    if (enabled) {
      void postDiagnosticEvent(activeUserId, activePersonaId, sessionId, {
        type: "diagnostics_enabled",
        platform: "expo-mobile",
        ts: Date.now(),
      });
    }
  }

  async function handleVoiceProfileSelect(profile: VoiceProfile) {
    try {
      const nextSummary = await selectVoiceProfile(activeUserId, activePersonaId, profile.id);
      setSummary((current) => mergeSummary(current, nextSummary, activeUserId, sessionId));
      setVoiceHint(`${profile.label} is now ${activePersona?.name || "this persona"}'s active voice for this profile.`);
      void logDiagnostic("voice_profile_selected", { profile_id: profile.id });
    } catch (error) {
      setVoiceHint(error instanceof Error ? error.message : "Voice profile update failed.");
    }
  }

  async function handleProfileSwitch(userId: string) {
    if (userId === activeUserId) {
      return;
    }
    await clearAuthSession();
    setIsAuthenticated(false);
    setAuthPassword("");
    setAuthError("");
    setAuthUserId(userId);
    setActiveUserId(userId);
    await saveActiveUserId(userId);
    setVoiceHint(`Switched to ${profiles.find((item) => item.userId === userId)?.displayName || userId}. Sign in to continue.`);
  }

  async function handlePersonaSwitch(personaId: string) {
    if (personaId === activePersonaId) {
      return;
    }
    setActivePersonaId(personaId);
    setAuthPersonaId(personaId);
    await saveActivePersonaId(personaId);
    setMessages([]);
    setSummary(null);
    setFeatureAccess(null);
    setCatalog([]);
    setUnlocked([]);
    await refreshForUser(activeUserId, personaId);
    const persona = personaProfiles.find((item) => item.id === personaId);
    setVoiceHint(`Switched to ${persona?.name || personaId}. This bond has its own level and memory.`);
  }

  async function handleCreateProfile() {
    const profile = createMobileProfile(newProfileName, profiles);
    const nextProfiles = [...profiles, profile];
    setProfiles(nextProfiles);
    await saveProfiles(nextProfiles);
    setAuthUserId(profile.userId);
    setNewProfileName("");
    setAuthPassword("");
    setAuthError("Profile created. Choose a password and a persona to enter.");
  }

  function handleAdminMoodPreview(mood: string | null) {
    setAdminMoodPreview(mood);
    setVoiceHint(mood ? `Admin previewing ${activePersona?.name || "persona"} mood: ${mood}.` : "Admin mood preview cleared.");
  }

  async function handleLogin() {
    try {
      const session = await loginLocally(authUserId, authPassword);
      setIsAuthenticated(true);
      setAuthError("");
      setActiveUserId(session.userId);
      setActivePersonaId(authPersonaId);
      await saveActiveUserId(session.userId);
      await saveActivePersonaId(authPersonaId);
      await refreshForUser(session.userId, authPersonaId);
      const persona = personaProfiles.find((item) => item.id === authPersonaId);
      setVoiceHint(`Logged in as ${profiles.find((item) => item.userId === session.userId)?.displayName || session.userId} with ${persona?.name || authPersonaId}.`);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Login failed.");
    }
  }

  async function handleLogout() {
    await clearAuthSession();
    setIsAuthenticated(false);
    setAuthPassword("");
    setAuthError("");
    setMessages([]);
    setSummary(null);
    setFeatureAccess(null);
    setCatalog([]);
    setUnlocked([]);
    setVoiceHint("Signed out.");
  }

  async function handleAdminSetLevel(levelTarget: number) {
    setAdminBusy(true);
    try {
      const nextSummary = await adminSetLevel(activeUserId, activePersonaId, levelTarget);
      setSummary(nextSummary);
      setFeatureAccess(nextSummary.feature_access ?? null);
      await refreshForUser(activeUserId, activePersonaId);
      setVoiceHint(`Admin set level to ${levelTarget}.`);
    } catch (error) {
      setVoiceHint(error instanceof Error ? error.message : "Admin level update failed.");
    } finally {
      setAdminBusy(false);
    }
  }

  async function handleAdminReset() {
    setAdminBusy(true);
    try {
      const nextSummary = await adminResetProgress(activeUserId, activePersonaId);
      setSummary(nextSummary);
      setFeatureAccess(nextSummary.feature_access ?? null);
      await refreshForUser(activeUserId, activePersonaId);
      setVoiceHint("Admin reset this profile back to level 0.");
    } catch (error) {
      setVoiceHint(error instanceof Error ? error.message : "Admin reset failed.");
    } finally {
      setAdminBusy(false);
    }
  }

  async function handleAdminSetAllFeatures(enabled: boolean) {
    setAdminBusy(true);
    try {
      const nextFeatureAccess = await adminSetAllFeatures(activeUserId, activePersonaId, enabled);
      setFeatureAccess(nextFeatureAccess);
      setVoiceHint(enabled ? "Admin enabled all unlocked features." : "Admin disabled all unlocked features.");
      await refreshForUser(activeUserId, activePersonaId);
    } catch (error) {
      setVoiceHint(error instanceof Error ? error.message : "Admin feature update failed.");
    } finally {
      setAdminBusy(false);
    }
  }

  if (!isAuthenticated) {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar barStyle="light-content" />
        <View style={styles.loginShell}>
          <View style={styles.loginAmbient} />
          <View style={styles.loginPanel}>
            <Text style={styles.eyebrow}>Nellie Mobile</Text>
            <Text style={styles.loginTitle}>Enter the bond</Text>
            <Text style={styles.loginCopy}>
              Create a local profile, choose who you want to travel with, and start at level 0. Memory, voice, and progression stay tied to that profile and persona.
            </Text>
            <View style={styles.loginPresenceCard}>
              <Text style={styles.loginPresenceEyebrow}>Before you enter</Text>
              <Text style={styles.loginPresenceTitle}>Text appears first. Voice may take a moment.</Text>
              <Text style={styles.loginPresenceCopy}>
                The app shows when your companion is listening, thinking, generating voice, or when something failed. If voice is slow, the answer should still be readable.
              </Text>
            </View>
            <Text style={styles.sectionEyebrow}>Step 1 - Choose or create profile</Text>
            <View style={styles.profileRow}>
              {profiles.map((profile) => (
                <TouchableOpacity
                  key={profile.userId}
                  style={[styles.profileChip, profile.userId === authUserId ? styles.profileChipActive : null]}
                  onPress={() => setAuthUserId(profile.userId)}
                >
                  <View style={[styles.profileChipDot, { backgroundColor: profile.badgeColor }]} />
                  <Text style={styles.profileChipText}>{profile.displayName}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput
              value={newProfileName}
              onChangeText={setNewProfileName}
              placeholder="Create profile name"
              placeholderTextColor="#7d8794"
              style={styles.loginInput}
            />
            <TouchableOpacity style={styles.secondaryButton} onPress={handleCreateProfile}>
              <Text style={styles.secondaryButtonText}>Create profile</Text>
            </TouchableOpacity>
            <Text style={styles.sectionEyebrow}>Step 2 - Choose companion</Text>
            <View style={styles.personaCardRow}>
              {personaProfiles.map((persona) => (
                <TouchableOpacity
                  key={persona.id}
                  style={[styles.personaCard, persona.id === authPersonaId ? styles.personaCardActive : null]}
                  onPress={() => setAuthPersonaId(persona.id)}
                >
                  <View style={[styles.profileChipDot, { backgroundColor: persona.id === "rolf" ? "#5db7de" : "#ff7b54" }]} />
                  <Text style={styles.personaCardTitle}>{persona.name || persona.label || persona.id}</Text>
                  <Text style={styles.personaCardCopy}>{personaIntroCopy(persona)}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={styles.loginPresenceCard}>
              <Text style={styles.loginPresenceEyebrow}>Step 3 - Start at level 0</Text>
              <Text style={styles.loginPresenceTitle}>{authPersona?.name || "This companion"} begins carefully.</Text>
              <Text style={styles.loginPresenceCopy}>
                Level 0 means a new bond: less assumed history, separate memory, and separate voice settings for this profile.
              </Text>
            </View>
            <TextInput
              value={authPassword}
              onChangeText={setAuthPassword}
              secureTextEntry
              placeholder="Password"
              placeholderTextColor="#7d8794"
              style={styles.loginInput}
            />
            <Text style={styles.loginHint}>
              {authUserId === "admin-mobile"
                ? "Admin default password: nellie"
                : authUserId === "guest"
                  ? "Guest default password: guest"
                  : "New local profiles save the first password you enter."}
            </Text>
            {authError ? <Text style={styles.loginError}>{authError}</Text> : null}
            <TouchableOpacity style={styles.loginButton} onPress={handleLogin}>
              <Text style={styles.loginButtonText}>Enter {authPersona?.name || "persona"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      <View style={styles.shell}>
        <View style={[styles.header, activeTab === "chat" ? styles.headerCompact : null]}>
          <View style={styles.headerText}>
            <Text style={styles.eyebrow}>Nellie Mobile</Text>
            <Text style={styles.headerTitle}>{activePersona?.name || "Nellie"}</Text>
            {activeTab === "chat" ? null : <Text style={styles.headerCopy}>A more personal, voice-first layer for the relationship.</Text>}
            <ProfileBadge profile={activeProfile} />
          </View>
          <MoodAvatar mood={currentMood} label={currentMood} activityState={presenceState} personaId={activePersonaId} />
        </View>

        <View style={[styles.hero, activeTab === "chat" ? styles.heroCompact : null]}>
          <View style={styles.heroTopline}>
            <Text style={styles.heroEyebrow}>Current bond state</Text>
            <Text style={styles.heroMood}>Mood: {currentMood}</Text>
          </View>
          <Text style={styles.stage}>{summary?.progress.stage || "Connection forming"}</Text>
          <Text style={styles.copy}>
            {activeTab === "chat" ? `Talk to ${activePersona?.name || "Nellie"} directly. Everything else should stay out of the way.` : `This is where the bond with ${activePersona?.name || "Nellie"} starts to take shape.`}
          </Text>
          {activeTab === "chat" ? null : <Text style={styles.journeyCopy}>{journeyCopy}</Text>}
          <View style={styles.heroStats}>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatLabel}>Level</Text>
              <Text style={styles.heroStatValue}>{level}</Text>
            </View>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatLabel}>XP</Text>
              <Text style={styles.heroStatValue}>{xp}</Text>
            </View>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatLabel}>Gallery</Text>
              <Text style={styles.heroStatValue}>{summary?.gallery_unlock_count ?? 0}</Text>
            </View>
          </View>
          <View style={styles.heroProgressBlock}>
            <View style={styles.heroProgressHeader}>
              <Text style={styles.heroProgressLabel}>Bond progress</Text>
              <Text style={styles.heroProgressMeta}>{xpToNextLevel} XP to next level</Text>
            </View>
            <View style={styles.heroProgressTrack}>
              <View style={[styles.heroProgressFill, { width: `${heroProgress * 100}%` }]} />
            </View>
          </View>
          <View style={styles.heroNextRow}>
            <Text style={styles.heroNextText}>
              {nextGallery
                ? `Next gallery: Lv ${nextGallery.level} • ${nextGallery.title}`
                : galleryAvailable
                  ? "Gallery tier fully unlocked for now"
                  : "No gallery is attached to this persona yet"}
            </Text>
            <Text style={styles.heroNextText}>
              {nextTool ? `Next tool: Lv ${nextTool.level} • ${nextTool.label}` : "Core toolset unlocked"}
            </Text>
            <Text style={styles.heroNextText}>
              {nextFeatureUnlock ? `Next phone feature: Lv ${nextFeatureUnlock.level} • ${nextFeatureUnlock.label}` : "Current phone feature band unlocked"}
            </Text>
          </View>
        </View>

        <View style={styles.tabs}>
          <TabButton label="Chat" active={activeTab === "chat"} onPress={() => setActiveTab("chat")} />
          <TabButton label="Gallery" active={activeTab === "gallery"} onPress={() => setActiveTab("gallery")} />
          <TabButton label="Bond" active={activeTab === "bond"} onPress={() => setActiveTab("bond")} />
          <TabButton label="Settings" active={activeTab === "settings"} onPress={() => setActiveTab("settings")} />
        </View>

        {activeTab === "chat" ? (
          <View style={styles.chatArea}>
            <View style={styles.presenceCard}>
              <Text style={styles.sectionEyebrow}>Presence</Text>
              <Text style={styles.presenceTitle}>{activePersona?.name || "Nellie"} is listening for tone, not just words.</Text>
              <Text style={styles.presenceCopy}>{voicePhaseLabel.detail}</Text>
            </View>
            <View style={styles.voiceRow}>
              <TouchableOpacity style={styles.voiceButton} onPress={handlePlayLastReply} disabled={isPlayingVoice}>
                <Text style={styles.voiceButtonText}>{isPlayingVoice ? "Playing..." : "Play last reply"}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.voiceButton, isRecording ? styles.voiceButtonActive : null]} onPress={handleVoiceShell} disabled={isVoiceBusy || isPlayingVoice}>
                <Text style={styles.voiceButtonText}>{isRecording ? "Stop recording" : isVoiceBusy ? "Working..." : isPlayingVoice ? "Voice playing..." : "Voice shell"}</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.voicePhase}>
              {voicePhaseLabel.label}
            </Text>
            <Text style={styles.voiceHint}>{voiceHint}</Text>
            <View style={styles.panel}>
              <MessageList messages={messages} />
            </View>
            <Composer onSend={handleComposerSend} disabled={isSending} />
          </View>
        ) : null}

        {activeTab === "gallery" ? (
          <ScrollView contentContainerStyle={styles.scrollContent}>
            <View style={styles.galleryIntro}>
              <Text style={styles.sectionEyebrow}>Private archive</Text>
              <Text style={styles.galleryIntroTitle}>Unlocked gallery</Text>
              <Text style={styles.galleryIntroCopy}>
                {unlockedItems.length
                  ? `You have unlocked ${unlockedItems.length} image${unlockedItems.length === 1 ? "" : "s"} so far.`
                  : galleryAvailable
                    ? "No gallery images unlocked yet."
                    : `${activePersona?.name || "This persona"} has no gallery attached yet.`}
              </Text>
              <Text style={styles.galleryIntroMeta}>
                {nextGallery
                  ? `${lockedCount} locked reward${lockedCount === 1 ? "" : "s"} remain. Next at level ${nextGallery.level}: ${nextGallery.title}.`
                  : galleryAvailable
                    ? "No further gallery tier is queued right now."
                    : "No images will be sent from this persona until a dedicated gallery is added."}
              </Text>
            </View>
            <GalleryGrid
              items={unlockedItems}
              unlockedPaths={new Set(unlockedItems.map((item) => item.image_path || item.path || item.filename))}
              onSelect={setSelectedGalleryItem}
            />
          </ScrollView>
        ) : null}

        {activeTab === "bond" ? (
          <ScrollView contentContainerStyle={styles.scrollContent}>
            <BondCard summary={summary} />
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Meaning</Text>
              <Text style={styles.settingsNoteTitle}>Why this matters now</Text>
              <Text style={styles.settingsNoteCopy}>{practicalFocus}</Text>
            </View>
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Practical access</Text>
              <Text style={styles.settingsNoteTitle}>What {activePersona?.name || "your companion"} can do now</Text>
              <Text style={styles.settingsNoteCopy}>
                {enabledFeatureLabels.length
                  ? enabledFeatureLabels.join(", ")
                  : availableFeatureLabels.length
                    ? "You have unlocked feature bands, but none are enabled on this phone yet."
                    : "Right now the progression is still about trust, memory, and early gallery beats."}
              </Text>
            </View>
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Suggested next move</Text>
              <Text style={styles.settingsNoteTitle}>What to try next</Text>
              {suggestedPrompts.length ? (
                suggestedPrompts.map((prompt) => (
                  <Text key={prompt} style={styles.promptLine}>
                    • {prompt}
                  </Text>
                ))
              ) : (
                <Text style={styles.settingsNoteCopy}>Keep talking with {activePersona?.name || "this persona"} and the next practical band will open soon.</Text>
              )}
            </View>
          </ScrollView>
        ) : null}

        {activeTab === "settings" ? (
          <ScrollView contentContainerStyle={styles.scrollContent}>
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Identity</Text>
              <Text style={styles.settingsNoteTitle}>Profiles</Text>
              <View style={styles.profileRow}>
                {profiles.map((profile) => (
                  <TouchableOpacity
                    key={profile.userId}
                    style={[styles.profileChip, profile.userId === activeUserId ? styles.profileChipActive : null]}
                    onPress={() => handleProfileSwitch(profile.userId)}
                  >
                    <View style={[styles.profileChipDot, { backgroundColor: profile.badgeColor }]} />
                    <Text style={styles.profileChipText}>{profile.displayName}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Persona</Text>
              <Text style={styles.settingsNoteTitle}>Active companion</Text>
              <Text style={styles.settingsNoteCopy}>
                Each persona keeps separate memory, progression, and voice settings for this user profile.
              </Text>
              <View style={styles.profileRow}>
                {personaProfiles.map((persona) => (
                  <TouchableOpacity
                    key={persona.id}
                    style={[styles.profileChip, persona.id === activePersonaId ? styles.profileChipActive : null]}
                    onPress={() => handlePersonaSwitch(persona.id)}
                  >
                    <View style={[styles.profileChipDot, { backgroundColor: persona.id === "rolf" ? "#5db7de" : "#ff7b54" }]} />
                    <Text style={styles.profileChipText}>{persona.name || persona.label || persona.id}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {activePersona?.description ? <Text style={styles.settingsNoteCopy}>{activePersona.description}</Text> : null}
            </View>
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Voice</Text>
              <Text style={styles.settingsNoteTitle}>{activePersona?.name || "Persona"} voice</Text>
              <Text style={styles.settingsNoteCopy}>
                Pick which saved voice this persona should use when text is spoken aloud.
              </Text>
              <View style={styles.profileRow}>
                {voiceProfiles.map((profile) => (
                  <TouchableOpacity
                    key={profile.id}
                    style={[styles.profileChip, selectedVoiceProfile?.id === profile.id ? styles.profileChipActive : null]}
                    onPress={() => handleVoiceProfileSelect(profile)}
                  >
                    <View style={[styles.profileChipDot, selectedVoiceProfile?.id === profile.id ? { backgroundColor: "#ff7b54" } : { backgroundColor: "#9ea7b3" }]} />
                    <Text style={styles.profileChipText}>{profile.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {selectedVoiceProfile?.description ? <Text style={styles.settingsNoteCopy}>{selectedVoiceProfile.description}</Text> : null}
            </View>
            <FeatureAccessPanel
              featureAccess={featureAccess}
              currentLevel={level}
              pendingFeatureId={pendingFeatureId}
              unsupportedFeatureIds={unsupportedFeatureIds}
              nextFeatureUnlock={nextFeatureUnlock}
              practicalFocus={practicalFocus}
              onToggle={handleFeatureToggle}
            />
            {isAdminProfile ? (
              <View style={styles.settingsNote}>
                <Text style={styles.sectionEyebrow}>Testing</Text>
                <Text style={styles.settingsNoteTitle}>Admin controls</Text>
                <Text style={styles.settingsNoteCopy}>
                  Admin can test personas, voice profiles, mood portraits, levels, progression reset, and feature bands for the active user/persona pair.
                </Text>
                <View style={styles.adminRow}>
                  {[0, 1, 8, 16, 32, 64, 255].map((target) => (
                    <TouchableOpacity
                      key={target}
                      style={[styles.adminButton, adminBusy ? styles.adminButtonDisabled : null]}
                      disabled={adminBusy}
                      onPress={() => handleAdminSetLevel(target)}
                    >
                      <Text style={styles.adminButtonText}>Lv {target}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.settingsNoteTitle}>Mood preview</Text>
                <View style={styles.adminRow}>
                  {MOOD_OPTIONS.map((mood) => (
                    <TouchableOpacity
                      key={mood}
                      style={[styles.adminButton, adminMoodPreview === mood ? styles.profileChipActive : null]}
                      onPress={() => handleAdminMoodPreview(mood)}
                    >
                      <Text style={styles.adminButtonText}>{mood}</Text>
                    </TouchableOpacity>
                  ))}
                  <TouchableOpacity style={styles.adminButton} onPress={() => handleAdminMoodPreview(null)}>
                    <Text style={styles.adminButtonText}>Live mood</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.adminRow}>
                  <TouchableOpacity style={[styles.adminButton, adminBusy ? styles.adminButtonDisabled : null]} disabled={adminBusy} onPress={() => handleAdminSetAllFeatures(true)}>
                    <Text style={styles.adminButtonText}>Enable features</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.adminButton, adminBusy ? styles.adminButtonDisabled : null]} disabled={adminBusy} onPress={() => handleAdminSetAllFeatures(false)}>
                    <Text style={styles.adminButtonText}>Disable features</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.adminButton, adminBusy ? styles.adminButtonDisabled : null]} disabled={adminBusy} onPress={handleAdminReset}>
                    <Text style={styles.adminButtonText}>Reset run</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}
            {isAdminProfile ? (
              <View style={styles.settingsNote}>
                <Text style={styles.sectionEyebrow}>Emergent memory</Text>
                <Text style={styles.settingsNoteTitle}>{activePersona?.name || "Persona"} preferences</Text>
                <Text style={styles.settingsNoteCopy}>
                  These are soft preferences that formed from repeated dialogue and saved memory, not fixed persona facts.
                </Text>
                {nelliePreferences.length ? (
                  nelliePreferences.map((item: NelliePreference) => (
                    <Text key={item.id} style={styles.promptLine}>
                      • {item.label}: {item.value} ({Math.round(item.confidence * 100)}% confidence, seen {item.count}x)
                    </Text>
                  ))
                ) : (
                  <Text style={styles.settingsNoteCopy}>No stable persona-side preferences have formed yet.</Text>
                )}
              </View>
            ) : null}
            <View style={styles.settingsNote}>
              <Text style={styles.sectionEyebrow}>Diagnostics</Text>
              <View style={styles.diagnosticsRow}>
                <View style={styles.diagnosticsTextWrap}>
                  <Text style={styles.settingsNoteTitle}>Debug diagnostics</Text>
                  <Text style={styles.settingsNoteCopy}>
                    If enabled, this phone sends lightweight client logs and timing events so backend, voice, and dialogue issues are easier to trace.
                  </Text>
                </View>
                <Switch
                  value={diagnosticsEnabled}
                  onValueChange={handleDiagnosticsToggle}
                  trackColor={{ false: "rgba(255,255,255,0.12)", true: "rgba(255,123,84,0.48)" }}
                  thumbColor={diagnosticsEnabled ? "#ff7b54" : "#d0d7e3"}
                />
              </View>
              <Text style={styles.settingsNoteTitle}>Phone permissions only</Text>
              <Text style={styles.settingsNoteCopy}>
                This mobile settings view controls what {activePersona?.name || "your companion"} is allowed to use on your phone. Admin tools and rollout controls still belong in the browser on your computer.
              </Text>
              <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
                <Text style={styles.logoutButtonText}>Sign out</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        ) : null}
      </View>
      <Modal visible={Boolean(selectedGalleryItem)} animationType="fade" transparent onRequestClose={() => setSelectedGalleryItem(null)}>
        <View style={styles.modalBackdrop}>
          <Pressable style={styles.modalBackdropTap} onPress={() => setSelectedGalleryItem(null)} />
          <View style={styles.modalCard}>
            {selectedGalleryImageUrl ? <Image source={{ uri: selectedGalleryImageUrl }} style={styles.modalImage} resizeMode="contain" /> : null}
            <Text style={styles.modalTitle}>{selectedGalleryItem?.title || "Unlocked image"}</Text>
            {selectedGalleryItem?.caption ? <Text style={styles.modalCaption}>{selectedGalleryItem.caption}</Text> : null}
            <TouchableOpacity style={styles.modalButton} onPress={() => setSelectedGalleryItem(null)}>
              <Text style={styles.modalButtonText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
      <Modal visible={voiceDraftVisible} animationType="slide" transparent onRequestClose={() => setVoiceDraftVisible(false)}>
        <View style={styles.modalBackdrop}>
          <Pressable
            style={styles.modalBackdropTap}
            onPress={() => {
              setVoiceDraftVisible(false);
              setVoiceDraft("");
              setVoicePhase("idle");
            }}
          />
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Did {activePersona?.name || "your companion"} hear that right?</Text>
            <Text style={styles.modalCaption}>
              You can correct the transcript before it gets sent, or record it again if it came through wrong.
            </Text>
            <TextInput
              value={voiceDraft}
              onChangeText={setVoiceDraft}
              multiline
              autoFocus
              placeholder="Edit what you meant to say..."
              placeholderTextColor="#7d8794"
              style={styles.voiceDraftInput}
            />
            <View style={styles.voiceDraftActions}>
              <TouchableOpacity style={styles.voiceDraftButtonMuted} onPress={handleVoiceDraftRetry}>
                <Text style={styles.voiceDraftButtonMutedText}>Record again</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.voiceDraftButton} onPress={handleVoiceDraftSend} disabled={isVoiceBusy}>
                <Text style={styles.voiceDraftButtonText}>{isVoiceBusy ? "Sending..." : `Send to ${activePersona?.name || "companion"}`}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function journeyDescription(stage: string, personaName: string): string {
  const mapping: Record<string, string> = {
    Anonymous: `You are at the beginning. ${personaName} is still careful, a little hidden, and learning who you are.`,
    Curious: "They are starting to notice your habits and interests. The bond is beginning to take shape.",
    Warm: `${personaName} is more open now. They remember more, react more personally, and feel more present.`,
    Flirted: "The tone shifts here. They get more suggestive, more aware of chemistry, and less distant.",
    Close: "This is where they start feeling actively invested in you, not just responsive.",
    Magnetic: `Late-stage ${personaName}. Confident, intimate, and very aware of the connection between you.`,
  };
  return mapping[stage] || mapping.Anonymous;
}

function TabButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity style={[styles.tabButton, active ? styles.tabButtonActive : null]} onPress={onPress}>
      <Text style={[styles.tabButtonText, active ? styles.tabButtonTextActive : null]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, paddingHorizontal: 18, paddingTop: 14, paddingBottom: 10, gap: 8 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  headerCompact: { marginBottom: -2 },
  headerText: { flexShrink: 1, paddingRight: 12 },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12, marginBottom: 8 },
  headerTitle: { color: "#f7f2eb", fontSize: 28, fontWeight: "800", marginBottom: 4 },
  headerCopy: { color: "#b8c0ca", lineHeight: 17, marginBottom: 8, maxWidth: 260, fontSize: 12 },
  hero: {
    borderRadius: 28,
    padding: 14,
    gap: 8,
    backgroundColor: "rgba(255,248,239,0.05)",
    borderWidth: 1,
    borderColor: "rgba(255,218,184,0.10)",
  },
  heroCompact: {
    padding: 10,
    gap: 5,
  },
  heroTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 },
  heroEyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 1.4, fontSize: 11 },
  heroMood: { color: "#c9d1db", fontSize: 12 },
  stage: { color: "#f2efe9", fontSize: 20, fontWeight: "700" },
  copy: { color: "#d5d0c8", lineHeight: 18, fontSize: 13 },
  journeyCopy: {
    color: "#f0e1d0",
    lineHeight: 17,
    fontSize: 12,
  },
  heroStats: {
    flexDirection: "row",
    gap: 10,
  },
  heroStat: {
    flex: 1,
    borderRadius: 16,
    padding: 10,
    backgroundColor: "rgba(255,255,255,0.03)",
  },
  heroStatLabel: {
    color: "#9ea7b3",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  heroStatValue: {
    color: "#f2efe9",
    fontSize: 16,
    fontWeight: "700",
    marginTop: 2,
  },
  heroProgressBlock: {
    gap: 8,
  },
  heroProgressHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 10,
  },
  heroProgressLabel: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  heroProgressMeta: {
    color: "#9ea7b3",
    fontSize: 12,
  },
  heroProgressTrack: {
    height: 10,
    borderRadius: 999,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  heroProgressFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: "#ff7b54",
  },
  heroNextRow: {
    gap: 4,
  },
  heroNextText: {
    color: "#ffd2a6",
    fontSize: 11,
    lineHeight: 15,
  },
  tabs: {
    flexDirection: "row",
    gap: 8,
  },
  tabButton: {
    flex: 1,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.03)",
    alignItems: "center",
  },
  tabButtonActive: {
    borderColor: "rgba(255,123,84,0.34)",
    backgroundColor: "rgba(255,123,84,0.18)",
  },
  tabButtonText: {
    color: "#cbd2dc",
    fontWeight: "700",
  },
  tabButtonTextActive: {
    color: "#fff2e6",
  },
  chatArea: {
    flex: 1,
    minHeight: 0,
    gap: 10,
  },
  presenceCard: {
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 3,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  presenceTitle: {
    color: "#f5efe7",
    fontSize: 14,
    fontWeight: "700",
  },
  presenceCopy: {
    color: "#c8d0da",
    fontSize: 12,
    lineHeight: 17,
  },
  panel: {
    flex: 1,
    minHeight: 0,
    borderRadius: 24,
    padding: 12,
    backgroundColor: "rgba(21,26,35,0.92)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  voiceRow: {
    flexDirection: "row",
    gap: 8,
  },
  voiceButton: {
    flex: 1,
    backgroundColor: "rgba(255,123,84,0.14)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "rgba(255,123,84,0.28)",
    alignItems: "center",
  },
  voiceButtonActive: {
    backgroundColor: "rgba(93,211,158,0.18)",
    borderColor: "rgba(93,211,158,0.34)",
  },
  voiceButtonText: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  voiceHint: {
    color: "#9ea7b3",
    lineHeight: 17,
    fontSize: 12,
  },
  voicePhase: {
    color: "#ffd2a6",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  scrollContent: {
    gap: 14,
    paddingBottom: 20,
  },
  galleryIntro: {
    borderRadius: 24,
    padding: 16,
    gap: 6,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  sectionEyebrow: {
    color: "#ffd2a6",
    textTransform: "uppercase",
    letterSpacing: 1.4,
    fontSize: 11,
  },
  galleryIntroTitle: {
    color: "#f2efe9",
    fontSize: 18,
    fontWeight: "700",
  },
  galleryIntroCopy: {
    color: "#d5d0c8",
    lineHeight: 20,
  },
  galleryIntroMeta: {
    color: "#ffd2a6",
    fontSize: 12,
    lineHeight: 18,
  },
  settingsNote: {
    borderRadius: 22,
    padding: 16,
    gap: 7,
    backgroundColor: "rgba(255,255,255,0.03)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  settingsNoteTitle: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  settingsNoteCopy: {
    color: "#c8d0da",
    lineHeight: 19,
    fontSize: 13,
  },
  promptLine: {
    color: "#f0e1d0",
    lineHeight: 20,
    fontSize: 13,
  },
  profileRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 8,
  },
  profileChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  profileChipActive: {
    backgroundColor: "rgba(255,123,84,0.18)",
    borderColor: "rgba(255,123,84,0.34)",
  },
  profileChipDot: {
    width: 10,
    height: 10,
    borderRadius: 999,
  },
  profileChipText: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  personaCardRow: {
    gap: 10,
  },
  personaCard: {
    borderRadius: 20,
    padding: 14,
    gap: 7,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  personaCardActive: {
    backgroundColor: "rgba(255,123,84,0.14)",
    borderColor: "rgba(255,123,84,0.34)",
  },
  personaCardTitle: {
    color: "#f2efe9",
    fontWeight: "800",
    fontSize: 16,
  },
  personaCardCopy: {
    color: "#c8d0da",
    lineHeight: 18,
    fontSize: 12,
  },
  loginShell: {
    flex: 1,
    paddingHorizontal: 22,
    paddingVertical: 28,
    justifyContent: "center",
    gap: 14,
    position: "relative",
  },
  loginAmbient: {
    position: "absolute",
    top: 120,
    right: -40,
    width: 220,
    height: 220,
    borderRadius: 999,
    backgroundColor: "rgba(255,123,84,0.10)",
  },
  loginPanel: {
    gap: 14,
    borderRadius: 28,
    padding: 22,
    backgroundColor: "rgba(16,20,28,0.92)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  loginTitle: {
    color: "#f2efe9",
    fontSize: 30,
    fontWeight: "800",
  },
  loginCopy: {
    color: "#d5d0c8",
    lineHeight: 21,
  },
  loginPresenceCard: {
    borderRadius: 20,
    padding: 14,
    gap: 6,
    backgroundColor: "rgba(255,123,84,0.08)",
    borderWidth: 1,
    borderColor: "rgba(255,123,84,0.18)",
  },
  loginPresenceEyebrow: {
    color: "#ffd2a6",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1.4,
  },
  loginPresenceTitle: {
    color: "#fff1e2",
    fontSize: 17,
    fontWeight: "700",
    lineHeight: 22,
  },
  loginPresenceCopy: {
    color: "#ecd8c5",
    lineHeight: 19,
    fontSize: 13,
  },
  loginInput: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 14,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    color: "#f2efe9",
  },
  loginHint: {
    color: "#b8a997",
    fontSize: 12,
  },
  loginError: {
    color: "#ff9f85",
    fontWeight: "600",
  },
  loginButton: {
    alignSelf: "flex-start",
    backgroundColor: "#ff7b54",
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 999,
    marginTop: 4,
  },
  loginButtonText: {
    color: "#111111",
    fontWeight: "700",
  },
  secondaryButton: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
  },
  secondaryButtonText: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  diagnosticsRow: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  diagnosticsTextWrap: {
    flex: 1,
    gap: 4,
  },
  adminRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  adminButton: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: "rgba(255,123,84,0.16)",
    borderWidth: 1,
    borderColor: "rgba(255,123,84,0.3)",
  },
  adminButtonDisabled: {
    opacity: 0.55,
  },
  adminButtonText: {
    color: "#fff2e6",
    fontWeight: "700",
    fontSize: 13,
  },
  logoutButton: {
    alignSelf: "flex-start",
    marginTop: 12,
    backgroundColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  logoutButtonText: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "center",
    padding: 18,
  },
  modalBackdropTap: {
    ...StyleSheet.absoluteFillObject,
  },
  modalCard: {
    borderRadius: 24,
    padding: 16,
    gap: 12,
    backgroundColor: "#121720",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  modalImage: {
    width: "100%",
    height: 360,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  modalTitle: {
    color: "#f2efe9",
    fontSize: 20,
    fontWeight: "700",
  },
  modalCaption: {
    color: "#d5d0c8",
    lineHeight: 21,
  },
  modalButton: {
    alignSelf: "flex-end",
    backgroundColor: "#ff7b54",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
  },
  modalButtonText: {
    color: "#111111",
    fontWeight: "700",
  },
  voiceDraftInput: {
    minHeight: 120,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    color: "#f2efe9",
    textAlignVertical: "top",
    lineHeight: 21,
  },
  voiceDraftActions: {
    flexDirection: "row",
    gap: 10,
    justifyContent: "flex-end",
  },
  voiceDraftButton: {
    backgroundColor: "#ff7b54",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
  },
  voiceDraftButtonText: {
    color: "#111111",
    fontWeight: "700",
  },
  voiceDraftButtonMuted: {
    backgroundColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  voiceDraftButtonMutedText: {
    color: "#f2efe9",
    fontWeight: "700",
  },
});
