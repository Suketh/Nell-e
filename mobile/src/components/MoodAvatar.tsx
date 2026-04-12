import { useEffect, useRef } from "react";
import { Animated, Easing, Image, StyleSheet, Text, View } from "react-native";
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

type MoodAvatarActivity = "idle" | "listening" | "thinking" | "speaking";

function normalizeMood(mood?: string): keyof typeof moodPalette {
  const value = (mood || "thoughtful").toLowerCase();
  return (value in moodPalette ? value : "thoughtful") as keyof typeof moodPalette;
}

function normalizeActivity(activityState?: string): MoodAvatarActivity {
  const value = (activityState || "idle").toLowerCase();
  if (value === "listening" || value === "thinking" || value === "speaking") {
    return value;
  }
  return "idle";
}

function animationProfile(activity: MoodAvatarActivity): { duration: number; minScale: number; maxScale: number; minOpacity: number; maxOpacity: number } {
  if (activity === "listening") {
    return { duration: 760, minScale: 0.98, maxScale: 1.1, minOpacity: 0.34, maxOpacity: 0.82 };
  }
  if (activity === "thinking") {
    return { duration: 1400, minScale: 0.99, maxScale: 1.05, minOpacity: 0.24, maxOpacity: 0.56 };
  }
  if (activity === "speaking") {
    return { duration: 520, minScale: 0.99, maxScale: 1.14, minOpacity: 0.42, maxOpacity: 0.94 };
  }
  return { duration: 900, minScale: 1, maxScale: 1.02, minOpacity: 0.18, maxOpacity: 0.26 };
}

export function MoodAvatar({ mood, label, activityState, personaId = "nellie" }: { mood?: string; label?: string; activityState?: MoodAvatarActivity | string; personaId?: string }) {
  const normalized = normalizeMood(mood);
  const activity = normalizeActivity(activityState);
  const palette = moodPalette[normalized];
  const pulse = useRef(new Animated.Value(0)).current;
  const loopRef = useRef<Animated.CompositeAnimation | null>(null);

  useEffect(() => {
    loopRef.current?.stop();
    if (activity === "idle") {
      pulse.stopAnimation();
      pulse.setValue(0);
      return;
    }
    const profile = animationProfile(activity);
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: profile.duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: profile.duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loopRef.current = loop;
    loop.start();
    return () => {
      loop.stop();
    };
  }, [activity, pulse]);

  const profile = animationProfile(activity);
  const pulseScale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [profile.minScale, profile.maxScale],
  });
  const pulseOpacity = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [profile.minOpacity, profile.maxOpacity],
  });

  return (
    <View style={styles.wrap}>
      <View style={styles.avatarStage}>
        <Animated.View
          pointerEvents="none"
          style={[
            styles.pulseRing,
            {
              borderColor: palette.glow,
              opacity: pulseOpacity,
              transform: [{ scale: pulseScale }],
            },
          ]}
        />
        <Animated.View
          pointerEvents="none"
          style={[
            styles.pulseAura,
            {
              backgroundColor: palette.glow,
              opacity: pulseOpacity.interpolate({
                inputRange: [0, 1],
                outputRange: [0.04, activity === "idle" ? 0.08 : 0.2],
              }),
              transform: [{ scale: pulseScale }],
            },
          ]}
        />
        <View style={[styles.image, { backgroundColor: palette.fill, borderColor: palette.glow, shadowColor: palette.glow }]}>
          <Image source={{ uri: buildMoodPortraitUrl(normalized, personaId) }} style={styles.portrait} resizeMode="cover" />
        </View>
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
  avatarStage: {
    width: 96,
    height: 96,
    alignItems: "center",
    justifyContent: "center",
  },
  pulseRing: {
    position: "absolute",
    width: 92,
    height: 92,
    borderRadius: 46,
    borderWidth: 2,
  },
  pulseAura: {
    position: "absolute",
    width: 92,
    height: 92,
    borderRadius: 46,
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
