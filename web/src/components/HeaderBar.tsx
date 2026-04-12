import type { ProgressState, WebProfile } from "../types/api";
import { MoodOrb } from "./MoodOrb";

type HeaderBarProps = {
  profile: WebProfile;
  progress: ProgressState | null;
  mood?: string;
  onOpenGallery: () => void;
};

export function HeaderBar({ profile, progress, mood, onOpenGallery }: HeaderBarProps) {
  return (
    <header className="header-bar">
      <div className="header-copy">
        <div className="eyebrow">Nell-e</div>
        <h1 className="header-title">Private presence channel</h1>
        <div className="hero-copy">A local-first companion shell shaped around mood, memory, and voice presence instead of a plain chat window.</div>
        <div className="subhead">
          <span className="profile-dot" style={{ backgroundColor: profile.badgeColor }} />
          {profile.displayName}
          <span className="subhead-separator">•</span>
          <span>{progress ? `${progress.stage}` : "Loading bond"}</span>
        </div>
      </div>
      <div className="header-actions">
        <MoodOrb mood={mood} label={mood || "thoughtful"} />
        <div className="progress-pill">
          {progress ? `Lv ${progress.level} / ${progress.stage}` : "Loading profile..."}
        </div>
        <button className="ghost-btn" onClick={onOpenGallery}>
          Gallery
        </button>
      </div>
    </header>
  );
}
