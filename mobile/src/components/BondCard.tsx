import { StyleSheet, Text, View } from "react-native";
import type { ProfileSummary } from "@/src/types/api";

export function BondCard({ summary }: { summary: ProfileSummary | null }) {
  const progress = summary?.progress;
  const xpIntoLevel = Math.max(0, progress?.xp_into_level ?? 0);
  const xpForNextLevel = Math.max(0, progress?.xp_for_next_level ?? 0);
  const xpToNextLevel = Math.max(0, progress?.xp_to_next_level ?? 0);
  const progressRatio = xpForNextLevel > 0 ? Math.max(0, Math.min(1, xpIntoLevel / xpForNextLevel)) : 1;
  const nextGallery =
    progress && typeof progress.next_gallery_unlock === "object" ? progress.next_gallery_unlock : null;
  const nextTool =
    progress && typeof progress.next_tool_unlock === "object" ? progress.next_tool_unlock : null;
  const unlockedTools = Array.isArray(progress?.unlocked_tools) ? progress.unlocked_tools : [];
  const stageCopy = stageDescription(progress?.stage || "Anonymous");
  const nextFeature = summary?.next_feature_unlock ?? null;
  const enabledFeatures = summary?.enabled_feature_labels ?? [];

  return (
    <View style={styles.card}>
      <Text style={styles.eyebrow}>Bond</Text>
      <Text style={styles.stage}>{progress?.stage || "Loading connection"}</Text>
      <Text style={styles.copy}>{stageCopy}</Text>
      <View style={styles.grid}>
        <View style={styles.item}>
          <Text style={styles.itemLabel}>Level</Text>
          <Text style={styles.itemValue}>{progress?.level ?? 0}</Text>
        </View>
        <View style={styles.item}>
          <Text style={styles.itemLabel}>XP</Text>
          <Text style={styles.itemValue}>{progress?.xp ?? 0}</Text>
        </View>
        <View style={styles.item}>
          <Text style={styles.itemLabel}>Unlocks</Text>
          <Text style={styles.itemValue}>{summary?.gallery_unlock_count ?? 0}</Text>
        </View>
      </View>
      <View style={styles.progressBlock}>
        <View style={styles.progressHeader}>
          <Text style={styles.progressLabel}>Progress to next level</Text>
          <Text style={styles.progressMeta}>{xpToNextLevel} XP left</Text>
        </View>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progressRatio * 100}%` }]} />
        </View>
        <Text style={styles.progressSubtle}>
          {xpIntoLevel} / {xpForNextLevel || 0} XP in this level
        </Text>
      </View>
      <View style={styles.nextGrid}>
        <View style={styles.nextItem}>
          <Text style={styles.nextEyebrow}>Visual reward</Text>
          <Text style={styles.nextLabel}>Next gallery beat</Text>
          <Text style={styles.nextValue}>
            {nextGallery ? `Lv ${nextGallery.level} • ${nextGallery.title}` : "Current gallery tier unlocked"}
          </Text>
          {nextGallery ? (
            <Text style={styles.nextMeta}>
              {nextGallery.visibility || "private"} / {nextGallery.tone || "soft"}
            </Text>
          ) : null}
        </View>
        <View style={styles.nextItem}>
          <Text style={styles.nextEyebrow}>Capability</Text>
          <Text style={styles.nextLabel}>Next agent unlock</Text>
          <Text style={styles.nextValue}>
            {nextTool ? `Lv ${nextTool.level} • ${nextTool.label}` : "Core toolset unlocked"}
          </Text>
        </View>
        <View style={styles.nextItem}>
          <Text style={styles.nextEyebrow}>Phone bridge</Text>
          <Text style={styles.nextLabel}>Next phone feature</Text>
          <Text style={styles.nextValue}>
            {nextFeature ? `Lv ${nextFeature.level} • ${nextFeature.label}` : "Current phone feature band unlocked"}
          </Text>
          {nextFeature ? <Text style={styles.nextMeta}>{nextFeature.description}</Text> : null}
        </View>
      </View>
      <View style={styles.nextItem}>
        <Text style={styles.nextLabel}>Unlocked functions</Text>
        <Text style={styles.nextValue}>
          {unlockedTools.length ? unlockedTools.join(", ") : "No advanced functions unlocked yet"}
        </Text>
      </View>
      <View style={styles.nextItem}>
        <Text style={styles.nextLabel}>Enabled on this phone</Text>
        <Text style={styles.nextValue}>
          {enabledFeatures.length ? enabledFeatures.join(", ") : "No phone-side feature access is enabled yet"}
        </Text>
      </View>
      {progress?.last_reason ? <Text style={styles.lastReason}>Recent XP came from: {progress.last_reason}</Text> : null}
    </View>
  );
}

function stageDescription(stage: string): string {
  const mapping: Record<string, string> = {
    Anonymous: "Nellie is still guarded and mostly private. This is the quiet beginning.",
    Curious: "She is starting to notice patterns in you and warm to your presence.",
    Warm: "The dynamic is more personal now. She remembers more and lets more of herself show.",
    Flirted: "The chemistry is active. Nellie starts responding with more intention and subtext.",
    Close: "The bond is established. More private gallery beats and stronger initiative start to open up.",
    Magnetic: "This is late-stage Nellie: confident, attentive, and much less shy about the connection.",
  };
  return mapping[stage] || mapping.Anonymous;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "rgba(255,248,239,0.05)",
    borderColor: "rgba(255,218,184,0.10)",
    borderWidth: 1,
    borderRadius: 24,
    padding: 20,
    gap: 12,
  },
  eyebrow: {
    color: "#ffd2a6",
    textTransform: "uppercase",
    letterSpacing: 2,
    fontSize: 12,
  },
  stage: {
    color: "#f2efe9",
    fontSize: 24,
    fontWeight: "700",
  },
  copy: {
    color: "#d5d0c8",
    lineHeight: 21,
  },
  grid: {
    flexDirection: "row",
    gap: 12,
  },
  item: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.03)",
  },
  itemLabel: {
    color: "#9ea7b3",
    fontSize: 12,
  },
  itemValue: {
    color: "#f2efe9",
    fontSize: 20,
    fontWeight: "700",
    marginTop: 4,
  },
  progressBlock: {
    gap: 8,
    marginTop: 2,
  },
  progressHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12,
  },
  progressLabel: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  progressMeta: {
    color: "#9ea7b3",
    fontSize: 12,
  },
  progressTrack: {
    height: 10,
    borderRadius: 999,
    overflow: "hidden",
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  progressFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: "#ff7b54",
  },
  progressSubtle: {
    color: "#9ea7b3",
    fontSize: 12,
  },
  nextGrid: {
    gap: 10,
  },
  nextItem: {
    borderRadius: 18,
    padding: 14,
    backgroundColor: "rgba(255,255,255,0.03)",
  },
  nextEyebrow: {
    color: "#ffd2a6",
    fontSize: 11,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  nextLabel: {
    color: "#9ea7b3",
    fontSize: 12,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  nextValue: {
    color: "#f2efe9",
    fontWeight: "700",
  },
  nextMeta: {
    color: "#c7b7aa",
    fontSize: 12,
    marginTop: 6,
    textTransform: "capitalize",
  },
  lastReason: {
    color: "#ffd2a6",
    fontSize: 12,
    lineHeight: 18,
  },
});
