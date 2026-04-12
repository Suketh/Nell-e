import { useState } from "react";
import type { ChatMessage, GalleryItem, ProfileSummary, WebProfile } from "../types/api";

type PhonePreviewProps = {
  profile: WebProfile;
  summary: ProfileSummary | null;
  catalog: GalleryItem[];
  unlocked: GalleryItem[];
  messages: ChatMessage[];
  isSending: boolean;
};

type PhoneTab = "chat" | "gallery" | "bond";

function stageLabel(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "Early hours";
  if (normalized.includes("curious")) return "Getting warmer";
  if (normalized.includes("warm")) return "After dark";
  if (normalized.includes("flirt")) return "Close signal";
  if (normalized.includes("close")) return "Private current";
  if (normalized.includes("magnetic")) return "Midnight current";
  return "Quiet signal";
}

function stageCopy(stage?: string): string {
  const normalized = (stage || "").toLowerCase();
  if (normalized.includes("anonymous")) return "She is still guarded, curious, and a little hard to read.";
  if (normalized.includes("curious")) return "The shell starts to feel personal. She notices more.";
  if (normalized.includes("warm")) return "Nellie settles in and sounds more like herself.";
  if (normalized.includes("flirt")) return "The chemistry is visible now. Replies land closer.";
  if (normalized.includes("close")) return "The app feels less like a tool and more like a late-night channel.";
  if (normalized.includes("magnetic")) return "This is where she stops holding the room at a distance.";
  return "A compact view of Nellie on a phone-sized shell.";
}

function titleFromItem(item: GalleryItem): string {
  return item.title || item.path?.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "Gallery item";
}

function nextToolText(nextTool: ProfileSummary["progress"]["next_tool_unlock"]): string {
  if (!nextTool) return "A new tool unlock will appear as the bond deepens.";
  if (typeof nextTool === "string") return nextTool;
  return nextTool.label ? `Level ${nextTool.level} • ${nextTool.label}` : `Level ${nextTool.level}`;
}

export function PhonePreview({ profile, summary, catalog, unlocked, messages, isSending }: PhonePreviewProps) {
  const [tab, setTab] = useState<PhoneTab>("chat");
  const progress = summary?.progress ?? null;
  const previewMessages = messages.slice(-3);
  const latestUnlock = summary?.latest_unlock;
  const unlockedPaths = new Set(unlocked.map((item) => item.path));
  const previewGallery = catalog.slice(0, 4);

  return (
    <section className="panel preview-panel">
      <div className="panel-title-row">
        <h2>Mobile preview</h2>
        <span className="muted">Presence shell</span>
      </div>
      <div className="phone-shell">
        <div className="phone-notch" />
        <div className="phone-screen">
          <div className="phone-topbar">
            <span>9:41</span>
            <span>Nellie</span>
            <span>5G</span>
          </div>
          <div className="phone-hero">
            <div className="eyebrow phone-eyebrow">{stageLabel(progress?.stage)}</div>
            <div className="phone-title">Nellie</div>
            <div className="phone-subtitle">
              <span className="profile-dot" style={{ backgroundColor: profile.badgeColor }} />
              {profile.displayName}
            </div>
            <div className="phone-stage">
              {progress ? `Level ${progress.level} / ${progress.stage}` : "Loading connection..."}
            </div>
            <div className="phone-copy">{stageCopy(progress?.stage)}</div>
          </div>

          <div className="phone-stats">
            <div className="phone-stat">
              <span>XP</span>
              <strong>{progress?.xp ?? 0}</strong>
            </div>
            <div className="phone-stat">
              <span>Unlocks</span>
              <strong>{summary?.gallery_unlock_count ?? 0}</strong>
            </div>
          </div>

          <div className="phone-body">
            {tab === "chat" ? (
              <>
                {latestUnlock ? (
                  <div className="phone-unlock">
                    <div className="phone-unlock-label">Latest unlock</div>
                    <strong>{latestUnlock.title || "Recent reward"}</strong>
                    <span>{latestUnlock.reason_text || "Unlocked through progression."}</span>
                  </div>
                ) : null}
                <div className="phone-feed">
                  {previewMessages.length ? (
                    previewMessages.map((message) => (
                      <article key={message.id} className={`phone-bubble ${message.role}`}>
                        <div>{message.text}</div>
                      </article>
                    ))
                  ) : (
                    <article className="phone-bubble assistant">
                      <div>She is waiting for the first message.</div>
                    </article>
                  )}
                </div>
                <div className="phone-composer">
                  <span>{isSending ? "Nellie is replying..." : "Drop a signal..."}</span>
                  <button className="phone-send" type="button">
                    Send
                  </button>
                </div>
              </>
            ) : null}

            {tab === "gallery" ? (
              <div className="phone-gallery-grid">
                {previewGallery.map((item, index) => {
                  const isUnlocked = unlockedPaths.has(item.path);
                  return (
                    <article key={`${item.path ?? "gallery"}-${index}`} className={`phone-gallery-card ${isUnlocked ? "unlocked" : "locked"}`}>
                      <strong>{titleFromItem(item)}</strong>
                      <span>{isUnlocked ? "Unlocked" : `Level ${item.level_min ?? "?"}`}</span>
                      <span>{item.tone || "neutral"} / {item.visibility || "private"}</span>
                    </article>
                  );
                })}
              </div>
            ) : null}

            {tab === "bond" ? (
              <div className="phone-bond-stack">
                <article className="phone-bond-card">
                  <span>Relationship stage</span>
                  <strong>{progress?.stage || "Loading"}</strong>
                  <p>{stageCopy(progress?.stage)}</p>
                </article>
                <article className="phone-bond-card">
                  <span>Next reward</span>
                  <strong>{progress?.next_gallery_unlock || "More gallery soon"}</strong>
                  <p>{nextToolText(progress?.next_tool_unlock)}</p>
                </article>
              </div>
            ) : null}
          </div>

          <div className="phone-nav">
            <button className={`phone-nav-item ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")} type="button">Chat</button>
            <button className={`phone-nav-item ${tab === "gallery" ? "active" : ""}`} onClick={() => setTab("gallery")} type="button">Gallery</button>
            <button className={`phone-nav-item ${tab === "bond" ? "active" : ""}`} onClick={() => setTab("bond")} type="button">Bond</button>
          </div>
        </div>
      </div>
    </section>
  );
}
