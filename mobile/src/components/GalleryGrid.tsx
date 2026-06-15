import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { buildGalleryAssetUrl } from "@/src/api/client";
import type { GalleryItem } from "@/src/types/api";

export function GalleryGrid({
  items,
  unlockedPaths,
  onSelect,
}: {
  items: GalleryItem[];
  unlockedPaths: Set<string | undefined>;
  onSelect?: (item: GalleryItem) => void;
}) {
  const rows: GalleryItem[][] = [];
  for (let index = 0; index < items.length; index += 2) {
    rows.push(items.slice(index, index + 2));
  }

  return (
    <View style={styles.list}>
      {rows.map((row, rowIndex) => (
        <View key={`row-${rowIndex}`} style={styles.row}>
          {row.map((item, itemIndex) => {
            const unlocked = Boolean(item.unlocked) || unlockedPaths.has(item.image_path) || unlockedPaths.has(item.path) || unlockedPaths.has(item.filename);
            const imageUrl = buildGalleryAssetUrl(item);
            return (
              <Pressable
                key={`${item.path || item.title || "asset"}-${rowIndex}-${itemIndex}`}
                style={[styles.card, unlocked ? styles.unlocked : styles.locked]}
                onPress={() => {
                  if (unlocked && onSelect) {
                    onSelect(item);
                  }
                }}
                disabled={!unlocked}
              >
                {unlocked && imageUrl ? (
                  <Image source={{ uri: imageUrl }} style={styles.preview} resizeMode="cover" />
                ) : (
                  <View style={styles.previewFallback}>
                    <Text style={styles.lockedBadge}>{unlocked ? "No preview" : "Locked"}</Text>
                  </View>
                )}
                <Text style={styles.title}>{item.title || "Gallery item"}</Text>
                <Text style={styles.meta}>{unlocked ? "Unlocked" : `Level ${item.level_min ?? "?"}`}</Text>
                <Text style={styles.meta}>
                  {item.tone || "soft"} / {item.visibility || "private"}
                </Text>
                {unlocked && item.caption ? <Text style={styles.caption}>{item.caption}</Text> : null}
              </Pressable>
            );
          })}
          {row.length === 1 ? <View style={styles.cardSpacer} /> : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: 12,
  },
  row: {
    gap: 12,
    flexDirection: "row",
  },
  card: {
    flex: 1,
    minHeight: 208,
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    gap: 8,
  },
  unlocked: {
    backgroundColor: "rgba(255,123,84,0.12)",
    borderColor: "rgba(255,123,84,0.28)",
  },
  locked: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderColor: "rgba(255,255,255,0.08)",
  },
  preview: {
    width: "100%",
    height: 108,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  previewFallback: {
    width: "100%",
    height: 108,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.05)",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
  },
  lockedBadge: {
    color: "#c7b7aa",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 1.2,
    fontWeight: "700",
  },
  title: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  meta: {
    color: "#9ea7b3",
    fontSize: 13,
  },
  caption: {
    color: "#d8d2ca",
    fontSize: 12,
    lineHeight: 18,
  },
  cardSpacer: {
    flex: 1,
  },
});
