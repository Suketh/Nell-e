import { Image, StyleSheet, Text, View } from "react-native";
import { buildMoodPortraitUrl } from "@/src/api/client";

const moodPalette = {
  angry: { glow: "#ff6b6b", fill: "#5a1d23" },
  annoyed: { glow: "#ff9b6a", fill: "#5b2b1a" },
  happy: { glow: "#ffd56a", fill: "#5a4712" },
  neutral: { glow: "#d9d4cb", fill: "#3a3a40" },
  sad: { glow: "#79a8ff", fill: "#1f3156" },
  thoughtful: { glow: "#c8a7ff", fill: "#392252" },
  tired: { glow: "#9c90dd", fill: "#2d2548" },
} as const;

function normalizeMood(mood?: string): keyof typeof moodPalette {
  const value = (mood || "thoughtful").toLowerCase();
  return (value in moodPalette ? value : "thoughtful") as keyof typeof moodPalette;
}

export function MoodAvatar({ mood, label }: { mood?: string; label?: string }) {
  const normalized = normalizeMood(mood);
  const palette = moodPalette[normalized];
  return (
    <View style={styles.wrap}>
      <View style={[styles.image, { backgroundColor: palette.fill, borderColor: palette.glow, shadowColor: palette.glow }]}>
        <Image source={{ uri: buildMoodPortraitUrl(normalized) }} style={styles.portrait} resizeMode="cover" />
      </View>
      {label ? <Text style={styles.label}>{label}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: "center",
    gap: 8,
  },
  image: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 2,
    overflow: "hidden",
    shadowOpacity: 0.35,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
  portrait: {
    width: "100%",
    height: "100%",
  },
  label: {
    color: "#f2efe9",
    fontSize: 14,
    textTransform: "capitalize",
  },
});
