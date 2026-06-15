import { StyleSheet, Text, View } from "react-native";
import type { MobileProfile } from "@/src/types/api";

export function ProfileBadge({ profile }: { profile: MobileProfile }) {
  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: profile.badgeColor }]} />
      <Text style={styles.text}>{profile.displayName}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 999,
  },
  text: {
    color: "#f2efe9",
    fontSize: 15,
    fontWeight: "600",
  },
});
