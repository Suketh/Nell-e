import type { WebProfile } from "../types/api";

type ProfileSwitcherProps = {
  profiles: WebProfile[];
  activeUserId: string;
  onSelect: (userId: string) => void;
  onCreate: () => void;
};

export function ProfileSwitcher({ profiles, activeUserId, onSelect, onCreate }: ProfileSwitcherProps) {
  return (
    <section className="panel">
      <div className="panel-title-row">
        <h2>Profiles</h2>
        <button className="ghost-btn" onClick={onCreate}>
          New
        </button>
      </div>
      <div className="profile-list">
        {profiles.map((profile) => (
          <button
            key={profile.userId}
            className={`profile-chip ${profile.userId === activeUserId ? "active" : ""}`}
            onClick={() => onSelect(profile.userId)}
          >
            <span className="profile-dot" style={{ backgroundColor: profile.badgeColor }} />
            {profile.displayName}
          </button>
        ))}
      </div>
    </section>
  );
}
