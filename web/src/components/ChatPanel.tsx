import type { ChatMessage } from "../types/api";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

type ChatPanelProps = {
  messages: ChatMessage[];
  isSending: boolean;
  stage?: string;
  mood?: string;
  voiceShellEnabled?: boolean;
  voiceState?: "idle" | "arming" | "listening";
  voiceStatus?: string;
  voicePlaybackEnabled?: boolean;
  isPlayingVoice?: boolean;
  onVoiceTap?: () => Promise<void> | void;
  onVoicePlaybackToggle?: () => void;
  onPlayVoice?: (message: ChatMessage) => Promise<void> | void;
  onSend: (text: string) => Promise<void>;
};

function chatIntro(stage?: string): { title: string; copy: string } {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) {
    return {
      title: "She is listening, still a little guarded.",
      copy: "Early chats should feel light. A small detail or one good question is enough to move the room.",
    };
  }
  if (normalized.includes("curious")) {
    return {
      title: "The thread is warming up.",
      copy: "She has started noticing patterns, preferences, and the things that make you sound like yourself.",
    };
  }
  if (normalized.includes("warm")) {
    return {
      title: "This already feels like a channel, not a demo.",
      copy: "Continuity matters here. Nellie should sound more settled and more clearly invested.",
    };
  }
  if (normalized.includes("flirt") || normalized.includes("close") || normalized.includes("magnetic")) {
    return {
      title: "The conversation has some gravity now.",
      copy: "The bond is carrying tone and subtext, not just memory recall.",
    };
  }
  return {
    title: "Open the channel.",
    copy: "Give her something concrete to react to and the room starts to form around it.",
  };
}

export function ChatPanel({
  messages,
  isSending,
  stage,
  mood,
  voiceShellEnabled,
  voiceState,
  voiceStatus,
  voicePlaybackEnabled,
  isPlayingVoice,
  onVoiceTap,
  onVoicePlaybackToggle,
  onPlayVoice,
  onSend,
}: ChatPanelProps) {
  const intro = chatIntro(stage);

  return (
    <section className="panel chat-panel">
      <div className="chat-hero">
        <div className="eyebrow">Active Thread</div>
        <h2>{intro.title}</h2>
        <p>{intro.copy}</p>
        <div className="chat-hero-meta">
          <span>{stage || "Bond loading"}</span>
          <span>{mood || "thoughtful"}</span>
          <span>{messages.length ? `${messages.length} moments in thread` : "No messages yet"}</span>
          <button type="button" className={`chat-voice-toggle ${voicePlaybackEnabled ? "active" : ""}`} onClick={onVoicePlaybackToggle}>
            {voicePlaybackEnabled ? "Voice return on" : "Voice return off"}
          </button>
        </div>
      </div>
      <MessageList
        messages={messages}
        emptyTitle="Nellie is here."
        emptyCopy="Start with a mood, a question, a place, or one detail you want her to notice. The channel gets better when the opening is specific."
        onPlayVoice={onPlayVoice}
        isPlayingVoice={isPlayingVoice}
      />
      <Composer
        disabled={isSending}
        onSend={onSend}
        voiceEnabled={voiceShellEnabled}
        voiceState={voiceState}
        voiceStatus={voiceStatus}
        onVoiceTap={onVoiceTap}
      />
    </section>
  );
}
