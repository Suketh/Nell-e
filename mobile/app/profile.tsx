import { SafeAreaView, StyleSheet, Text, View } from "react-native";
import { ADMIN_WEB_URL } from "@/src/config/env";

export default function ProfileScreen() {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.shell}>
        <Text style={styles.eyebrow}>Profile & Admin</Text>
        <Text style={styles.title}>Desktop remains the control room</Text>
        <Text style={styles.copy}>
          The mobile app is meant to be the intimate client: chat, gallery, bond, and voice.
          Admin mode, rollout checks, and deeper configuration should still live in the browser on your computer.
        </Text>
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Admin web</Text>
          <Text style={styles.cardValue}>{ADMIN_WEB_URL}</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, padding: 18, gap: 16 },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12 },
  title: { color: "#f2efe9", fontSize: 28, fontWeight: "700" },
  copy: { color: "#d5d0c8", lineHeight: 22 },
  card: {
    borderRadius: 22,
    padding: 18,
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    gap: 8,
  },
  cardLabel: { color: "#9ea7b3", textTransform: "uppercase", letterSpacing: 1, fontSize: 12 },
  cardValue: { color: "#f2efe9", fontSize: 16, fontWeight: "600" },
});
