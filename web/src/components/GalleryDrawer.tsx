import type { GalleryItem } from "../types/api";

type GalleryDrawerProps = {
  open: boolean;
  catalog: GalleryItem[];
  unlocked: GalleryItem[];
  onClose: () => void;
};

export function GalleryDrawer({ open, catalog, unlocked, onClose }: GalleryDrawerProps) {
  if (!open) {
    return null;
  }

  const unlockedPaths = new Set(unlocked.map((item) => item.path));

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <div className="panel-title-row">
          <h2>Gallery room</h2>
          <button className="ghost-btn" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="gallery-grid">
          {catalog.map((item, index) => {
            const unlockedItem = unlockedPaths.has(item.path);
            return (
              <div key={`${item.path ?? "asset"}-${index}`} className={`gallery-card ${unlockedItem ? "unlocked" : "locked"}`}>
                <strong>{item.title || item.path?.split(/[\\/]/).pop() || "Asset"}</strong>
                <span>{unlockedItem ? "Unlocked" : `Level ${item.level_min ?? "?"}`}</span>
                <span>{item.tone || "neutral"} • {item.visibility || "private"}</span>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
