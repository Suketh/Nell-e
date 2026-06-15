import type { CSSProperties } from "react";

type MoodOrbProps = {
  mood?: string;
  label?: string;
  size?: "compact" | "hero";
};

const MOOD_STYLES: Record<string, { glow: string; ring: string }> = {
  happy: { glow: "rgba(255, 190, 92, 0.42)", ring: "rgba(255, 204, 118, 0.55)" },
  thoughtful: { glow: "rgba(212, 182, 255, 0.34)", ring: "rgba(212, 182, 255, 0.5)" },
  neutral: { glow: "rgba(245, 219, 181, 0.24)", ring: "rgba(214, 217, 223, 0.38)" },
  tired: { glow: "rgba(147, 137, 210, 0.28)", ring: "rgba(167, 154, 221, 0.42)" },
  sad: { glow: "rgba(100, 142, 204, 0.28)", ring: "rgba(124, 164, 216, 0.42)" },
  annoyed: { glow: "rgba(255, 137, 88, 0.32)", ring: "rgba(255, 154, 104, 0.46)" },
  angry: { glow: "rgba(255, 94, 94, 0.34)", ring: "rgba(255, 120, 120, 0.46)" },
};

const MOOD_ALIASES: Record<string, string> = {
  curious: "thoughtful",
  calm: "neutral",
  content: "happy",
  confused: "thoughtful",
  upset: "sad",
  frustrated: "annoyed",
  sleepy: "tired",
};

const moodPortraits = import.meta.glob("../../../assets/moods/**/*.png", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

function normalizeMood(mood?: string): string {
  const value = (mood || "thoughtful").trim().toLowerCase();
  const normalized = MOOD_ALIASES[value] || value;
  return MOOD_STYLES[normalized] ? normalized : "thoughtful";
}

function portraitUrlForMood(mood: string): string {
  const wantedSuffix = `/assets/moods/nellie/${mood}.png`;
  const fallbackSuffix = "/assets/moods/nellie/neutral.png";
  const wanted = Object.entries(moodPortraits).find(([key]) => key.replace(/\\/g, "/").endsWith(wantedSuffix))?.[1];
  const fallback = Object.entries(moodPortraits).find(([key]) => key.replace(/\\/g, "/").endsWith(fallbackSuffix))?.[1];
  return wanted || fallback || "";
}

export function MoodOrb({ mood, label, size = "compact" }: MoodOrbProps) {
  const normalized = normalizeMood(mood);
  const style = MOOD_STYLES[normalized];
  const portraitUrl = portraitUrlForMood(normalized);

  return (
    <div className={`mood-orb-wrap mood-orb-wrap-${size}`} aria-label={label || `Nellie mood ${normalized}`}>
      <div
        className={`mood-orb mood-${normalized} mood-orb-${size}`}
        style={
          {
            "--orb-glow": style.glow,
            "--orb-ring": style.ring,
          } as CSSProperties
        }
      >
        {portraitUrl ? <img className="mood-orb-image" src={portraitUrl} alt={label || `${normalized} Nellie`} /> : null}
      </div>
      {label ? <span className={`mood-orb-label mood-orb-label-${size}`}>{label}</span> : null}
    </div>
  );
}
