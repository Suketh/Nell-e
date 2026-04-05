import type { ChatMessage } from "../types/api";

type MessageListProps = {
  messages: ChatMessage[];
  emptyTitle?: string;
  emptyCopy?: string;
  onPlayVoice?: (message: ChatMessage) => Promise<void> | void;
  isPlayingVoice?: boolean;
};

export function MessageList({
  messages,
  emptyTitle = "No messages yet",
  emptyCopy = "Start the thread when you're ready.",
  onPlayVoice,
  isPlayingVoice,
}: MessageListProps) {
  if (!messages.length) {
    return (
      <div className="message-list empty">
        <article className="message-empty-state">
          <div className="message-role">Nellie</div>
          <strong>{emptyTitle}</strong>
          <p>{emptyCopy}</p>
        </article>
      </div>
    );
  }

  return (
    <div className="message-list">
      {messages.map((message) => (
        <article key={message.id} className={`message-bubble ${message.role}`}>
          <div className="message-role">{message.role === "assistant" ? "Nellie" : "You"}</div>
          <div>{message.text}</div>
          {message.role === "assistant" ? (
            <div className="message-actions">
              <button
                type="button"
                className="message-voice-btn"
                onClick={() => onPlayVoice?.(message)}
                disabled={!onPlayVoice || isPlayingVoice}
              >
                {isPlayingVoice ? "Playing..." : "Play voice"}
              </button>
            </div>
          ) : null}
          {message.mood ? <div className="message-mood">{message.mood}</div> : null}
        </article>
      ))}
    </div>
  );
}
