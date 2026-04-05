import type { ProfileSummary } from "../types/api";

type ProgressCardProps = {
  summary: ProfileSummary | null;
};

export function ProgressCard({ summary }: ProgressCardProps) {
  const progress = summary?.progress;

  return (
    <section className="panel">
      <h2>Connection</h2>
      {progress ? (
        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-label">Level</span>
            <strong>{progress.level}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">XP</span>
            <strong>{progress.xp}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">Stage</span>
            <strong>{progress.stage}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">Unlocks</span>
            <strong>{summary?.gallery_unlock_count ?? 0}</strong>
          </div>
        </div>
      ) : (
        <div className="muted">Loading progression...</div>
      )}
    </section>
  );
}
