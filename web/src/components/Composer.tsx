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
  if (state === "listening") return "Stop recording";
  if (state === "arming") return "Working...";
  if (enabled) return "Start recording";
  return "Enable mic";
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
        placeholder="Write to Nellie..."
        rows={3}
        disabled={disabled}
      />
      <div className="composer-actions">
        <div className="composer-hint">
          Short messages feel the most natural here. Web voice playback is not wired yet.
        </div>
        <button type="submit" className="send-btn" disabled={disabled || !value.trim()}>
          Send
        </button>
      </div>
    </form>
  );
}
