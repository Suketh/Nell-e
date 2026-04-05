import { useEffect, useMemo, useState } from "react";
import { SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Composer } from "@/src/components/Composer";
import { MessageList } from "@/src/components/MessageList";
import { MoodAvatar } from "@/src/components/MoodAvatar";
import { ProfileBadge } from "@/src/components/ProfileBadge";
import { fetchProfileSummary, fetchTtsAudioDataUri, sendReply } from "@/src/api/client";
import { playRemoteAudio, stopRemoteAudio } from "@/src/audio/player";
import { startNativeRecording, stopNativeRecording } from "@/src/audio/recorder";
import { loadActiveUserId, loadProfiles } from "@/src/store/profile";
import { randomSessionId } from "@/src/store/session";
import type { ChatMessage, MobileProfile, ProfileSummary } from "@/src/types/api";

export default function ChatScreen() {
  const [profiles, setProfiles] = useState<MobileProfile[]>([]);
  const [activeUserId, setActiveUserId] = useState("guest");
  const [summary, setSummary] = useState<ProfileSummary | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceHint, setVoiceHint] = useState("Native voice shell scaffold is ready.");
  const [sessionId] = useState(() => randomSessionId());

  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.userId === activeUserId) || { userId: "guest", displayName: "Guest", badgeColor: "#f2c14e" },
    [profiles, activeUserId],
  );

  useEffect(() => {
    async function boot() {
      const loadedProfiles = await loadProfiles();
      const storedUser = await loadActiveUserId();
      const nextUserId = storedUser || loadedProfiles[0]?.userId || "guest";
      setProfiles(loadedProfiles);
      setActiveUserId(nextUserId);
      try {
        setSummary(await fetchProfileSummary(nextUserId));
      } catch {
        // leave summary empty in scaffold mode
      }
    }
    void boot();
  }, []);

  async function handleSend(text: string) {
    setIsSending(true);
    setMessages((current) => [...current, { id: `${Date.now()}-user`, role: "user", text }]);
    try {
      const response = await sendReply({ userId: activeUserId, sessionId, text });
      setMessages((current) => [
        ...current,
        { id: `${Date.now()}-assistant`, role: "assistant", text: response.reply, mood: response.mood },
      ]);
      setSummary(await fetchProfileSummary(activeUserId));
    } finally {
      setIsSending(false);
    }
  }

  async function handlePlayLastReply() {
    const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
    if (!lastAssistant) {
      setVoiceHint("No Nellie reply to play yet.");
      return;
    }
    setIsPlayingVoice(true);
    setVoiceHint("Playing Nellie's voice...");
    try {
      const audio = await fetchTtsAudioDataUri(lastAssistant.text, activeUserId);
      await playRemoteAudio(audio.uri);
      setVoiceHint("Voice playback active.");
    } catch (err) {
      setVoiceHint(err instanceof Error ? err.message : "Voice playback failed.");
    } finally {
      setIsPlayingVoice(false);
    }
  }

  async function handleVoiceShell() {
    try {
      if (!isRecording) {
        await startNativeRecording();
        setIsRecording(true);
        setVoiceHint("Recording locally on the device. STT bridge is the next pass.");
        return;
      }
      const uri = await stopNativeRecording();
      setIsRecording(false);
      setVoiceHint(uri ? `Recorded locally: ${uri}` : "Recording stopped.");
    } catch (err) {
      setIsRecording(false);
      setVoiceHint(err instanceof Error ? err.message : "Native recording failed.");
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.shell}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>Nellie Mobile</Text>
            <ProfileBadge profile={activeProfile} />
          </View>
          <MoodAvatar mood={messages[messages.length - 1]?.mood || "thoughtful"} />
        </View>
        <View style={styles.hero}>
          <Text style={styles.stage}>{summary?.progress.stage || "Connection forming"}</Text>
          <Text style={styles.copy}>
            Mobile chat is the primary shell. Admin controls and rollout still belong in the desktop browser/web client.
          </Text>
        </View>
        <View style={styles.voiceRow}>
          <TouchableOpacity style={styles.voiceButton} onPress={handlePlayLastReply} disabled={isPlayingVoice}>
            <Text style={styles.voiceButtonText}>{isPlayingVoice ? "Playing..." : "Play last reply"}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.voiceButton, isRecording ? styles.voiceButtonActive : null]} onPress={handleVoiceShell}>
            <Text style={styles.voiceButtonText}>{isRecording ? "Stop recording" : "Voice shell"}</Text>
          </TouchableOpacity>
        </View>
        <Text style={styles.voiceHint}>{voiceHint}</Text>
        <View style={styles.panel}>
          <MessageList messages={messages} />
        </View>
        <Composer onSend={handleSend} disabled={isSending} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, padding: 18, gap: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12, marginBottom: 8 },
  hero: {
    borderRadius: 24,
    padding: 18,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  stage: { color: "#f2efe9", fontSize: 24, fontWeight: "700", marginBottom: 8 },
  copy: { color: "#d5d0c8", lineHeight: 22 },
  panel: {
    flex: 1,
    borderRadius: 24,
    padding: 14,
    backgroundColor: "rgba(21,26,35,0.92)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  voiceRow: {
    flexDirection: "row",
    gap: 12,
  },
  voiceButton: {
    flex: 1,
    backgroundColor: "rgba(255,123,84,0.14)",
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 12,
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
    lineHeight: 20,
  },
});
