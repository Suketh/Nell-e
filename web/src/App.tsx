import { useEffect, useRef, useState } from "react";
import { fetchTtsAudio, transcribePcmAudio, fetchGalleryCatalog, fetchProfileSummary, fetchUnlockedGallery, sendReply } from "./api/client";
import { beginPcmRecording } from "./audio/recorder";
import { ChatPanel } from "./components/ChatPanel";
import { HeaderBar } from "./components/HeaderBar";
import { MoodOrb } from "./components/MoodOrb";
import { PhonePreview } from "./components/PhonePreview";
import { ProfileSwitcher } from "./components/ProfileSwitcher";
import type { ChatMessage, GalleryItem, ProfileSummary, WebProfile } from "./types/api";

const PROFILE_KEY = "nellie.web.profiles";
const ACTIVE_PROFILE_KEY = "nellie.web.activeProfile";
const BADGE_COLORS = ["#f2c14e", "#d96c75", "#5db7de", "#5dd39e", "#9b5de5", "#ff7b54"];

type MainTab = "chat" | "gallery" | "bond";
type GalleryFilter = "all" | "unlocked" | "locked";
type VoiceShellState = "idle" | "arming" | "listening";

function slugify(input: string): string {
  return (
    input
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "guest"
  );
}

function randomSessionId(): string {
  const secureCrypto = globalThis.crypto;
  if (secureCrypto && typeof secureCrypto.randomUUID === "function") {
    return `web-${secureCrypto.randomUUID().slice(0, 8)}`;
  }
  const entropy = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `web-${entropy.slice(0, 12)}`;
}

function loadProfiles(): WebProfile[] {
  const raw = window.localStorage.getItem(PROFILE_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as WebProfile[];
      if (Array.isArray(parsed) && parsed.length) {
        return parsed;
      }
    } catch {
      // ignore local corruption and rebuild below
    }
  }
  return [{ userId: "guest", displayName: "Guest", badgeColor: BADGE_COLORS[0] }];
}

function saveProfiles(profiles: WebProfile[]) {
  window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profiles));
}

function titleFromItem(item: GalleryItem): string {
  return item.title || item.path?.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "Gallery item";
}

function stageCopy(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "She is still guarded, curious, and a little hard to read.";
  if (normalized.includes("curious")) return "The shell starts to feel personal. She notices more.";
  if (normalized.includes("warm")) return "Nellie settles in and sounds more like herself.";
  if (normalized.includes("flirt")) return "The chemistry is visible now. Replies land closer.";
  if (normalized.includes("close")) return "The app feels less like a tool and more like a late-night channel.";
  if (normalized.includes("magnetic")) return "This is where she stops holding the room at a distance.";
  return "A companion shell for chat, memory and progression.";
}

function stageMood(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "careful, distant, observant";
  if (normalized.includes("curious")) return "interested, warming, more attentive";
  if (normalized.includes("warm")) return "comfortable, softer, more open";
  if (normalized.includes("flirt")) return "playful, charged, more direct";
  if (normalized.includes("close")) return "private, invested, late-night";
  if (normalized.includes("magnetic")) return "confident, intimate, unmistakable";
  return "present, curious, responsive";
}

function stageMeaning(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "Early progression is about trust. Nellie is still deciding how much of herself to show.";
  if (normalized.includes("curious")) return "She starts storing more details and reacts more clearly to topics she likes.";
  if (normalized.includes("warm")) return "This is where continuity matters. The app should feel more lived-in between conversations.";
  if (normalized.includes("flirt")) return "Her timing changes here. The bond starts carrying subtext, not just memory.";
  if (normalized.includes("close")) return "Rewards and replies should feel more personal, less like system outputs.";
  if (normalized.includes("magnetic")) return "The experience should read as deliberate chemistry rather than generic assistant behavior.";
  return "The relationship layer is active, but still forming.";
}

function galleryAtmosphere(item: GalleryItem | null): string {
  if (!item) return "Curated rewards live here once the thread has earned them.";
  const tone = (item.tone || "soft").toLowerCase();
  const visibility = (item.visibility || "private").toLowerCase();
  if (visibility === "extreme") return "This sits at the far edge of the reward track and should feel intentionally withheld.";
  if (visibility === "intimate") return "This reads as a more private reward. The app should frame it like trust, not loot.";
  if (tone === "bold") return "This is where Nellie starts feeling more self-aware about being seen.";
  if (tone === "romantic") return "The reward tone here should feel softer, slower, and closer to chemistry than spectacle.";
  if (tone === "dramatic" || tone === "special") return "This belongs to the part of the gallery that feels less everyday and more eventful.";
  return "This part of the gallery should feel like a lived-in extension of the bond, not a sterile unlock list.";
}

function galleryCardMood(item: GalleryItem): string {
  const tone = (item.tone || "soft").toLowerCase();
  const visibility = (item.visibility || "private").toLowerCase();
  return `${tone}-${visibility}`;
}

function bondSignal(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "She keeps a little distance and gives away less of herself.";
  if (normalized.includes("curious")) return "She starts tugging on details and remembering what seems like you.";
  if (normalized.includes("warm")) return "This is where the room stops feeling generic and starts feeling inhabited.";
  if (normalized.includes("flirt")) return "There is a visible charge here. She is more aware of timing and chemistry.";
  if (normalized.includes("close")) return "The bond is personal now. Rewards and replies should carry more intention.";
  if (normalized.includes("magnetic")) return "At this stage she should feel deliberate, confident, and hard to ignore.";
  return "The connection is present, but still undefined.";
}

function nextToolLabel(progress: ProfileSummary["progress"] | null): string {
  const next = progress?.next_tool_unlock;
  if (!next) return "More agency ahead";
  if (typeof next === "string") return next;
  return next.label || `Level ${next.level}`;
}

export default function App() {
  const [profiles, setProfiles] = useState<WebProfile[]>(() => loadProfiles());
  const [activeUserId, setActiveUserId] = useState<string>(
    () => window.localStorage.getItem(ACTIVE_PROFILE_KEY) || loadProfiles()[0].userId,
  );
  const [summary, setSummary] = useState<ProfileSummary | null>(null);
  const [catalog, setCatalog] = useState<GalleryItem[]>([]);
  const [unlocked, setUnlocked] = useState<GalleryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [activeTab, setActiveTab] = useState<MainTab>("chat");
  const [galleryFilter, setGalleryFilter] = useState<GalleryFilter>("all");
  const [selectedGalleryPath, setSelectedGalleryPath] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [voiceShellEnabled, setVoiceShellEnabled] = useState(false);
  const [voiceShellState, setVoiceShellState] = useState<VoiceShellState>("idle");
  const [voicePlaybackEnabled, setVoicePlaybackEnabled] = useState(true);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const recorderRef = useRef<Awaited<ReturnType<typeof beginPcmRecording>> | null>(null);
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null);
  const sessionIdRef = useRef(randomSessionId());

  const activeProfile = profiles.find((profile) => profile.userId === activeUserId) || profiles[0];
  const progress = summary?.progress ?? null;
  const unlockedPaths = new Set(unlocked.map((item) => item.path));
  const latestUnlock = summary?.latest_unlock;
  const currentMood = [...messages].reverse().find((message) => message.role === "assistant" && message.mood)?.mood || "thoughtful";
  const selectedGalleryItem =
    catalog.find((item) => item.path === selectedGalleryPath) ||
    unlocked[unlocked.length - 1] ||
    catalog[0] ||
    null;
  const filteredGallery = catalog.filter((item) => {
    const isUnlocked = unlockedPaths.has(item.path);
    if (galleryFilter === "unlocked") return isUnlocked;
    if (galleryFilter === "locked") return !isUnlocked;
    return true;
  });

  useEffect(() => {
    saveProfiles(profiles);
  }, [profiles]);

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_PROFILE_KEY, activeUserId);
  }, [activeUserId]);

  useEffect(() => {
    let cancelled = false;

    async function loadRemoteState() {
      if (!activeProfile) return;
      try {
        setError("");
        const [nextSummary, nextCatalog, nextUnlocked] = await Promise.all([
          fetchProfileSummary(activeProfile.userId),
          fetchGalleryCatalog(activeProfile.userId),
          fetchUnlockedGallery(activeProfile.userId),
        ]);
        if (cancelled) return;
        setSummary(nextSummary);
        setCatalog(nextCatalog);
        setUnlocked(nextUnlocked);
        setSelectedGalleryPath((current) => {
          if (current && nextCatalog.some((item) => item.path === current)) {
            return current;
          }
          return nextUnlocked[nextUnlocked.length - 1]?.path || nextCatalog[0]?.path || "";
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to reach Nellie backend.");
        }
      }
    }

    setMessages([]);
    setActiveTab("chat");
    sessionIdRef.current = randomSessionId();
    void loadRemoteState();

    return () => {
      cancelled = true;
    };
  }, [activeProfile]);

  useEffect(() => {
    return () => {
      if (recorderRef.current) {
        void recorderRef.current.stop().catch(() => undefined);
        recorderRef.current = null;
      }
      if (playbackAudioRef.current) {
        playbackAudioRef.current.pause();
        playbackAudioRef.current = null;
      }
    };
  }, []);

  async function refreshRemoteState(userId: string) {
    const [nextSummary, nextCatalog, nextUnlocked] = await Promise.all([
      fetchProfileSummary(userId),
      fetchGalleryCatalog(userId),
      fetchUnlockedGallery(userId),
    ]);
    setSummary(nextSummary);
    setCatalog(nextCatalog);
    setUnlocked(nextUnlocked);
  }

  async function refreshProgressState(userId: string, refreshUnlocked = false) {
    const requests: [Promise<ProfileSummary>, Promise<GalleryItem[]> | null] = [
      fetchProfileSummary(userId),
      refreshUnlocked ? fetchUnlockedGallery(userId) : null,
    ];
    const [nextSummary, nextUnlocked] = await Promise.all([
      requests[0],
      requests[1] ?? Promise.resolve(null),
    ]);
    setSummary(nextSummary);
    if (nextUnlocked) {
      setUnlocked(nextUnlocked);
    }
  }

  async function handleSend(text: string) {
    if (!activeProfile) return;
    let releasedSending = false;
    setError("");
    setIsSending(true);
    setMessages((current) => [
      ...current,
      {
        id: `${Date.now()}-user`,
        role: "user",
        text,
      },
    ]);
    try {
      const response = await sendReply({
        userId: activeProfile.userId,
        sessionId: sessionIdRef.current,
        text,
      });
      const assistantMessage: ChatMessage = {
        id: `${Date.now()}-assistant`,
        role: "assistant",
        text: response.reply,
        mood: response.mood,
      };
      const hasNewUnlock = Boolean(
        response.new_unlock &&
        typeof response.new_unlock === "object" &&
        Object.keys(response.new_unlock).length,
      );
      setMessages((current) => [
        ...current,
        assistantMessage,
      ]);
      setIsSending(false);
      releasedSending = true;
      void refreshProgressState(activeProfile.userId, hasNewUnlock).catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to refresh Nellie state.");
      });
      if (voicePlaybackEnabled) {
        void playAssistantVoice(assistantMessage).catch((err) => {
          setError(err instanceof Error ? err.message : "Voice playback failed.");
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reply failed.");
      setIsSending(false);
      releasedSending = true;
    } finally {
      if (!releasedSending) {
        setIsSending(false);
      }
    }
  }

  function handleCreateProfile() {
    const name = window.prompt("New profile name");
    if (!name) return;
    const userId = slugify(name);
    if (profiles.some((profile) => profile.userId === userId)) {
      setError("That profile already exists.");
      return;
    }
    const nextProfile: WebProfile = {
      userId,
      displayName: name.trim(),
      badgeColor: BADGE_COLORS[profiles.length % BADGE_COLORS.length],
    };
    setProfiles((current) => [...current, nextProfile]);
    setActiveUserId(nextProfile.userId);
  }

  async function handleVoiceShellTap() {
    if (!activeProfile || isSending) {
      return;
    }

    if (voiceShellState === "idle") {
      try {
        setError("");
        setVoiceShellEnabled(true);
        setVoiceShellState("arming");
        recorderRef.current = await beginPcmRecording(16000);
        setVoiceShellState("listening");
      } catch (err) {
        setVoiceShellEnabled(false);
        setVoiceShellState("idle");
        setError(err instanceof Error ? err.message : "Microphone setup failed.");
      }
      return;
    }

    if (!recorderRef.current) {
      setVoiceShellState("idle");
      return;
    }

    try {
      setVoiceShellState("arming");
      const pcm16 = await recorderRef.current.stop();
      recorderRef.current = null;
      const transcript = await transcribePcmAudio({ pcm16 });
      setVoiceShellState("idle");
      await handleSend(transcript);
    } catch (err) {
      recorderRef.current = null;
      setVoiceShellState("idle");
      setError(err instanceof Error ? err.message : "Voice transcription failed.");
    }
  }

  async function playAssistantVoice(message: ChatMessage) {
    if (message.role !== "assistant") {
      return;
    }
    setIsPlayingVoice(true);
    const blob = await fetchTtsAudio({ text: message.text });
    const objectUrl = URL.createObjectURL(blob);

    if (playbackAudioRef.current) {
      playbackAudioRef.current.pause();
      playbackAudioRef.current = null;
    }

    const audio = new Audio(objectUrl);
    playbackAudioRef.current = audio;
    audio.onended = () => {
      URL.revokeObjectURL(objectUrl);
      if (playbackAudioRef.current === audio) {
        playbackAudioRef.current = null;
      }
      setIsPlayingVoice(false);
    };
    audio.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      if (playbackAudioRef.current === audio) {
        playbackAudioRef.current = null;
      }
      setIsPlayingVoice(false);
    };

    try {
      await audio.play();
    } catch (err) {
      URL.revokeObjectURL(objectUrl);
      if (playbackAudioRef.current === audio) {
        playbackAudioRef.current = null;
      }
      setIsPlayingVoice(false);
      throw err;
    }
  }

  const voiceStatus =
    voiceShellState === "listening"
      ? "Listening now. Tap again to stop and send to STT."
      : voiceShellState === "arming"
        ? "Voice shell is arming or processing the current take."
        : voiceShellEnabled
          ? "Voice shell is ready. Tap to record a short message."
          : "Voice shell is off for now. Text remains the active path.";
  const presenceStateLabel =
    voiceShellState === "listening"
      ? "Nellie is listening"
      : isSending
        ? "Nellie is composing"
        : isPlayingVoice
          ? "Nellie is speaking"
          : "Channel is open";
  const presencePulseLabel =
    voiceShellState === "listening"
      ? "Live mic"
      : isSending
        ? "Thinking"
        : isPlayingVoice
          ? "Voice active"
          : "Standby";

  return (
    <div className="app-shell mobile-app-shell">
      <HeaderBar profile={activeProfile} progress={progress} mood={currentMood} onOpenGallery={() => setActiveTab("gallery")} />
      <section className="presence-hero-grid">
        <section className="panel presence-focus-card">
          <div className="presence-focus-copy">
            <div className="eyebrow">Living Presence</div>
            <h2 className="presence-title">Nellie should feel present before she says a word.</h2>
            <p className="presence-copy">
              This shell centers mood, bond state, and live voice behavior so the UI reads more like an inhabited channel than a generic assistant panel.
            </p>
          </div>
          <div className="presence-center">
            <div className={`presence-pulse ${voiceShellState} ${isSending ? "busy" : ""} ${isPlayingVoice ? "speaking" : ""}`}>
              <MoodOrb mood={currentMood} label={currentMood} size="hero" />
            </div>
            <div className="presence-status-stack">
              <div className="presence-state-line">
                <span className="presence-state-dot" />
                <strong>{presenceStateLabel}</strong>
                <small>{presencePulseLabel}</small>
              </div>
              <p>{bondSignal(progress?.stage)}</p>
            </div>
          </div>
          <div className="presence-signal-grid">
            <article className="presence-signal-card">
              <span>Bond stage</span>
              <strong>{progress?.stage || "Loading connection"}</strong>
              <p>{stageMood(progress?.stage)}</p>
            </article>
            <article className="presence-signal-card">
              <span>Voice channel</span>
              <strong>{voiceShellEnabled ? "Armed" : "Text-first"}</strong>
              <p>{voiceStatus}</p>
            </article>
            <article className="presence-signal-card">
              <span>Current thread</span>
              <strong>{messages.length ? `${messages.length} messages` : "Fresh room"}</strong>
              <p>{latestUnlock ? latestUnlock.title || "New unlock available" : "No recent unlock event"}</p>
            </article>
          </div>
        </section>

        <aside className="presence-side-stack">
          <ProfileSwitcher
            profiles={profiles}
            activeUserId={activeUserId}
            onSelect={setActiveUserId}
            onCreate={handleCreateProfile}
          />
          <section className="panel presence-stage-card">
            <div className="eyebrow">Connection Arc</div>
            <h2>{progress?.stage || "Loading connection"}</h2>
            <p className="mobile-stage-copy">{stageCopy(progress?.stage)}</p>
            <div className="presence-stage-meta">
              <span>Level {progress?.level ?? 0}</span>
              <span>{summary?.gallery_unlock_count ?? 0} unlocks</span>
              <span>{nextToolLabel(progress)}</span>
            </div>
          </section>
        </aside>
      </section>
      <main className="mobile-layout">
        <aside className="mobile-sidebar narrative-sidebar">
          <section className="panel narrative-card">
            <div className="eyebrow">Channel Notes</div>
            <h2>What the room is doing</h2>
            <p>{stageMeaning(progress?.stage)}</p>
            <div className="narrative-stat-list">
              <div className="narrative-stat">
                <span>Current mood</span>
                <strong>{currentMood}</strong>
              </div>
              <div className="narrative-stat">
                <span>Latest signal</span>
                <strong>{presencePulseLabel}</strong>
              </div>
              <div className="narrative-stat">
                <span>Next reward</span>
                <strong>{progress?.next_gallery_unlock || "More soon"}</strong>
              </div>
            </div>
          </section>
          <PhonePreview
            profile={activeProfile}
            summary={summary}
            catalog={catalog}
            unlocked={unlocked}
            messages={messages}
            isSending={isSending}
          />
        </aside>

        <section className="mobile-main panel">
          {error ? <div className="error-banner">{error}</div> : null}

          <div className="mobile-tabs">
            <button className={`mobile-tab ${activeTab === "chat" ? "active" : ""}`} onClick={() => setActiveTab("chat")}>
              Chat
            </button>
            <button className={`mobile-tab ${activeTab === "gallery" ? "active" : ""}`} onClick={() => setActiveTab("gallery")}>
              Gallery
            </button>
            <button className={`mobile-tab ${activeTab === "bond" ? "active" : ""}`} onClick={() => setActiveTab("bond")}>
              Bond
            </button>
          </div>

          {activeTab === "chat" ? (
            <div className="mobile-screen">
              <section className="chat-stage-shell">
                <div className="chat-stage-copy">
                  <div className="eyebrow">Channel State</div>
                  <strong>{stageMood(progress?.stage)}</strong>
                  <span>{stageCopy(progress?.stage)}</span>
                </div>
                <div className={`voice-stage-chip ${voiceShellState}`}>
                  <span className="voice-stage-dot" />
                  {voiceShellState === "listening" ? "Listening shell" : voiceShellEnabled ? "Voice shell ready" : "Text channel"}
                </div>
              </section>
              {latestUnlock ? (
                <section className="mobile-highlight">
                  <div className="muted">Latest unlock</div>
                  <strong>{latestUnlock.title || "Recent reward"}</strong>
                  <span>{latestUnlock.reason_text || "Unlocked through progression."}</span>
                </section>
              ) : null}
              <ChatPanel
                messages={messages}
                isSending={isSending}
                onSend={handleSend}
                stage={progress?.stage}
                mood={currentMood}
                voiceShellEnabled={voiceShellEnabled}
                voiceState={voiceShellState}
                voiceStatus={voiceStatus}
                voicePlaybackEnabled={voicePlaybackEnabled}
                isPlayingVoice={isPlayingVoice}
                onVoiceTap={handleVoiceShellTap}
                onVoicePlaybackToggle={() => setVoicePlaybackEnabled((current) => !current)}
                onPlayVoice={playAssistantVoice}
              />
            </div>
          ) : null}

          {activeTab === "gallery" ? (
            <div className="mobile-screen">
              <section className="gallery-hero-card">
                <div className="eyebrow">Gallery Room</div>
                <h2>{selectedGalleryItem ? titleFromItem(selectedGalleryItem) : "Nellie's gallery"}</h2>
                <p className="gallery-hero-copy">
                  {selectedGalleryItem?.reason_text ||
                    selectedGalleryItem?.caption ||
                    "This is where Nellie's unlocked images and future rewards start to feel curated instead of purely mechanical."}
                </p>
                <div className={`gallery-hero-visual ${selectedGalleryItem ? galleryCardMood(selectedGalleryItem) : "soft-private"}`}>
                  <div className="gallery-hero-overlay">
                    <span>{selectedGalleryItem?.tone || "soft"}</span>
                    <strong>{selectedGalleryItem ? titleFromItem(selectedGalleryItem) : "Gallery reward"}</strong>
                    <small>{galleryAtmosphere(selectedGalleryItem)}</small>
                  </div>
                </div>
                <div className="gallery-hero-meta">
                  <span>{selectedGalleryItem?.tone || "soft"}</span>
                  <span>{selectedGalleryItem?.visibility || "private"}</span>
                  <span>{selectedGalleryItem?.level_min ? `Level ${selectedGalleryItem.level_min}+` : "Reward track"}</span>
                </div>
              </section>

              <section className="gallery-filter-row">
                <button className={`mobile-tab ${galleryFilter === "all" ? "active" : ""}`} onClick={() => setGalleryFilter("all")}>
                  All
                </button>
                <button className={`mobile-tab ${galleryFilter === "unlocked" ? "active" : ""}`} onClick={() => setGalleryFilter("unlocked")}>
                  Unlocked
                </button>
                <button className={`mobile-tab ${galleryFilter === "locked" ? "active" : ""}`} onClick={() => setGalleryFilter("locked")}>
                  Locked
                </button>
              </section>

              <section className="mobile-gallery-grid">
                {filteredGallery.map((item, index) => {
                  const isUnlocked = unlockedPaths.has(item.path);
                  return (
                    <article
                      key={`${item.path ?? "asset"}-${index}`}
                      className={`mobile-gallery-card ${galleryCardMood(item)} ${isUnlocked ? "unlocked" : "locked"} ${selectedGalleryItem?.path === item.path ? "selected" : ""}`}
                      onClick={() => setSelectedGalleryPath(item.path || "")}
                    >
                      <div className="mobile-gallery-thumb">
                        <span>{item.content_type || "image"}</span>
                        <strong>{item.level_min ? `Lv ${item.level_min}` : "Reward"}</strong>
                      </div>
                      <strong>{titleFromItem(item)}</strong>
                      <span>{isUnlocked ? "Unlocked" : `Level ${item.level_min ?? "?"}`}</span>
                      <span>{item.tone || "neutral"} / {item.visibility || "private"}</span>
                      {item.tags?.length ? <div className="gallery-tag-row">{item.tags.slice(0, 3).map((tag) => <span key={tag} className="gallery-tag">{tag}</span>)}</div> : null}
                    </article>
                  );
                })}
              </section>
            </div>
          ) : null}

          {activeTab === "bond" ? (
            <div className="mobile-screen mobile-bond-screen">
              <section className="bond-debug-card">
                <div className="eyebrow">Bond</div>
                <h2>{progress?.stage || "Connection forming"}</h2>
                <p className="bond-hero-copy">
                  {progress
                    ? stageCopy(progress.stage)
                    : "Nellie is still loading her current bond state, but this page is now forced to render a visible fallback block."}
                </p>
                <div className="bond-mood-line">
                  <MoodOrb mood={currentMood} label={currentMood} size="hero" />
                  <span>Current tone: {stageMood(progress?.stage)}</span>
                </div>
                <div className="bond-debug-grid">
                  <article className="bond-debug-item">
                    <span>Level</span>
                    <strong>{progress?.level ?? 0}</strong>
                  </article>
                  <article className="bond-debug-item">
                    <span>XP</span>
                    <strong>{progress?.xp ?? 0}</strong>
                  </article>
                  <article className="bond-debug-item">
                    <span>Unlocks</span>
                    <strong>{summary?.gallery_unlock_count ?? 0}</strong>
                  </article>
                  <article className="bond-debug-item">
                    <span>Next</span>
                    <strong>{progress?.next_gallery_unlock || "More soon"}</strong>
                  </article>
                </div>
                <section className="bond-narrative-grid">
                  <article className="bond-note-card">
                    <span>How She Feels</span>
                    <strong>{stageMood(progress?.stage)}</strong>
                    <p>{bondSignal(progress?.stage)}</p>
                  </article>
                  <article className="bond-note-card">
                    <span>What Changes Now</span>
                    <strong>{nextToolLabel(progress)}</strong>
                    <p>{stageMeaning(progress?.stage)}</p>
                  </article>
                  <article className="bond-note-card">
                    <span>Gallery Tone</span>
                    <strong>{latestUnlock?.title || "Next reward track"}</strong>
                    <p>{galleryAtmosphere(latestUnlock || selectedGalleryItem)}</p>
                  </article>
                </section>
                <p className="bond-detail-copy">
                  {progress
                    ? stageMeaning(progress.stage)
                    : "If you can see this card, the bond tab itself is rendering correctly and the earlier problem was layout-related."}
                </p>
                <section className="bond-quick-nav">
                  <button className="ghost-btn" onClick={() => setActiveTab("chat")}>
                    Back To Chat
                  </button>
                  <button className="ghost-btn" onClick={() => setActiveTab("gallery")}>
                    Open Gallery
                  </button>
                </section>
              </section>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
