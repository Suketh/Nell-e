import { ActivityIndicator, StyleSheet, Switch, Text, View } from "react-native";

import type { FeatureAccessItem, FeatureAccessState, NextFeatureUnlock } from "@/src/types/api";

type Props = {
  featureAccess?: FeatureAccessState | null;
  currentLevel: number;
  pendingFeatureId?: string | null;
  unsupportedFeatureIds?: Set<string>;
  nextFeatureUnlock?: NextFeatureUnlock | null;
  practicalFocus?: string;
  onToggle: (item: FeatureAccessItem, enabled: boolean) => void;
};

const CATEGORY_LABELS: Record<string, string> = {
  utility: "Utility",
  knowledge: "Knowledge",
  services: "Services",
  device: "Phone widgets",
};

export function FeatureAccessPanel({
  featureAccess,
  currentLevel,
  pendingFeatureId,
  unsupportedFeatureIds,
  nextFeatureUnlock,
  practicalFocus,
  onToggle,
}: Props) {
  const items = featureAccess?.items ?? [];
  const grouped = items.reduce<Record<string, FeatureAccessItem[]>>((acc, item) => {
    const key = String(item.category || "other");
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
  const enabledItems = items.filter((item) => Boolean(item.enabled));
  const unlockedPendingItems = items.filter((item) => Boolean(item.unlocked) && !item.enabled);
  const lockedItems = items.filter((item) => !item.unlocked);

  return (
    <View style={styles.wrap}>
      <View style={styles.hero}>
        <Text style={styles.heroEyebrow}>Phone permissions</Text>
        <Text style={styles.heroTitle}>Feature access</Text>
        <Text style={styles.heroCopy}>
          When Nellie reaches the right level, you decide which phone-side abilities she is actually allowed to use.
        </Text>
        <Text style={styles.heroMeta}>
          Level {currentLevel} • {featureAccess?.enabled_count ?? 0} enabled • {featureAccess?.available_count ?? 0} available
        </Text>
        {practicalFocus ? <Text style={styles.heroPractical}>{practicalFocus}</Text> : null}
      </View>
      <View style={styles.summaryRow}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Active now</Text>
          <Text style={styles.summaryValue}>{enabledItems.length}</Text>
          <Text style={styles.summaryCopy}>Features Nellie can actively use on this phone.</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Waiting for you</Text>
          <Text style={styles.summaryValue}>{unlockedPendingItems.length}</Text>
          <Text style={styles.summaryCopy}>Unlocked, but not yet approved by you.</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Still ahead</Text>
          <Text style={styles.summaryValue}>{lockedItems.length}</Text>
          <Text style={styles.summaryCopy}>Features that arrive later in the journey.</Text>
        </View>
      </View>
      {nextFeatureUnlock ? (
        <View style={styles.nextFeatureCard}>
          <Text style={styles.nextFeatureLabel}>Next feature band</Text>
          <Text style={styles.nextFeatureValue}>
            Level {nextFeatureUnlock.level} • {nextFeatureUnlock.label}
          </Text>
          <Text style={styles.nextFeatureCopy}>{nextFeatureUnlock.description}</Text>
        </View>
      ) : null}
      {Object.entries(grouped).map(([category, categoryItems]) => (
        <View key={category} style={styles.section}>
          <Text style={styles.sectionTitle}>{CATEGORY_LABELS[category] || category}</Text>
          {categoryItems.map((item) => {
            const locked = !item.unlocked;
            const pending = pendingFeatureId === item.id;
            const unsupported = Boolean(unsupportedFeatureIds?.has(item.id));
            const disabled = locked || pending || !item.implemented || unsupported;
            const status = locked
              ? `Unlocks at level ${item.min_level}`
              : unsupported
                ? "Unavailable in Expo Go. Use a development build for this phone bridge."
              : item.implemented
                ? item.enabled
                  ? "Enabled on this phone"
                  : "Available, but waiting for your approval"
                : "Planned for a later phone bridge";
            return (
              <View key={item.id} style={styles.card}>
                <View style={styles.cardText}>
                  <Text style={styles.cardTitle}>{item.label}</Text>
                  <Text style={styles.cardCopy}>{item.description}</Text>
                  <Text style={[styles.cardStatus, locked ? styles.locked : item.implemented ? styles.live : styles.planned]}>
                    {status}
                  </Text>
                </View>
                <View style={styles.toggleWrap}>
                  {pending ? <ActivityIndicator color="#ffd2a6" /> : null}
                  <Switch
                    value={Boolean(item.enabled)}
                    onValueChange={(value) => onToggle(item, value)}
                    disabled={disabled}
                    trackColor={{ false: "rgba(255,255,255,0.12)", true: "rgba(255,123,84,0.48)" }}
                    thumbColor={item.enabled ? "#ff7b54" : "#d0d7e3"}
                  />
                </View>
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 14,
    paddingBottom: 22,
  },
  hero: {
    borderRadius: 24,
    padding: 16,
    gap: 8,
    backgroundColor: "rgba(255,248,239,0.05)",
    borderWidth: 1,
    borderColor: "rgba(255,218,184,0.10)",
  },
  heroEyebrow: {
    color: "#ffd2a6",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1.4,
  },
  heroTitle: {
    color: "#f2efe9",
    fontSize: 18,
    fontWeight: "700",
  },
  heroCopy: {
    color: "#d5d0c8",
    lineHeight: 20,
  },
  heroMeta: {
    color: "#ffd2a6",
    fontSize: 12,
  },
  heroPractical: {
    color: "#f0e1d0",
    lineHeight: 19,
    fontSize: 13,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 10,
  },
  summaryCard: {
    flex: 1,
    borderRadius: 18,
    padding: 12,
    gap: 6,
    backgroundColor: "rgba(255,255,255,0.03)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  summaryLabel: {
    color: "#9ea7b3",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  summaryValue: {
    color: "#f2efe9",
    fontSize: 22,
    fontWeight: "700",
  },
  summaryCopy: {
    color: "#d5d0c8",
    fontSize: 12,
    lineHeight: 17,
  },
  nextFeatureCard: {
    borderRadius: 20,
    padding: 16,
    gap: 6,
    backgroundColor: "rgba(255,123,84,0.10)",
    borderWidth: 1,
    borderColor: "rgba(255,123,84,0.24)",
  },
  nextFeatureLabel: {
    color: "#ffd2a6",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  nextFeatureValue: {
    color: "#fff2e6",
    fontSize: 17,
    fontWeight: "700",
  },
  nextFeatureCopy: {
    color: "#f0e1d0",
    lineHeight: 18,
    fontSize: 13,
  },
  section: {
    gap: 8,
  },
  sectionTitle: {
    color: "#f2efe9",
    fontSize: 15,
    fontWeight: "700",
    paddingHorizontal: 2,
  },
  card: {
    borderRadius: 18,
    padding: 14,
    gap: 12,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  cardText: {
    flex: 1,
    gap: 6,
  },
  cardTitle: {
    color: "#f2efe9",
    fontSize: 16,
    fontWeight: "700",
  },
  cardCopy: {
    color: "#d5d0c8",
    lineHeight: 19,
    fontSize: 13,
  },
  cardStatus: {
    fontSize: 12,
    lineHeight: 16,
  },
  locked: {
    color: "#9ea7b3",
  },
  live: {
    color: "#ffd2a6",
  },
  planned: {
    color: "#8ec7ff",
  },
  toggleWrap: {
    width: 56,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
});
