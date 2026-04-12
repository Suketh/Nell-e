import { FormEvent, useState } from "react";

type ComposerProps = {
  disabled?: boolean;
  onSend: (text: string) => Promise<void>;
  voiceStatus?: string;
  voiceEnabled?: boolean;
  voiceState?: "idle" | "arming" | "listening";
  onVoiceTap?: () => Promise<void> | void;
};

function voiceButtonLabel(state?: "idle" | "arming" | "listening", enabled?: boolean): string {
  if (state === "listening") return "Release mic";
  if (state === "arming") return "Processing";
  if (enabled) return "Open mic";
  return "Arm mic";
}

export function Composer({ disabled, onSend, voiceStatus, voiceEnabled, voiceState, onVoiceTap }: ComposerProps) {
  const [value, setValue] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    setValue("");
    await onSend(trimmed);
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-topline">
        <span>{voiceStatus || "Text channel is open."}</span>
        <button
          type="button"
          className={`voice-shell-btn ${voiceEnabled ? "active" : ""} ${voiceState || "idle"}`}
          onClick={onVoiceTap}
          disabled={disabled || voiceState === "arming"}
        >
          {voiceButtonLabel(voiceState, voiceEnabled)}
        </button>
      </div>
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Write something with a little signal..."
        rows={3}
        disabled={disabled}
      />
      <div className="composer-actions">
        <div className="composer-hint">
          Short, intentional prompts land best here. Voice input can shape the rhythm, text can shape the detail.
        </div>
        <button type="submit" className="send-btn" disabled={disabled || !value.trim()}>
          Send
        </button>
      </div>
    </form>
  );
}
