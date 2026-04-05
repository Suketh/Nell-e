import { useEffect, useState } from "react";
import { SafeAreaView, StyleSheet, Text, View } from "react-native";
import { fetchProfileSummary } from "@/src/api/client";
import { BondCard } from "@/src/components/BondCard";
import { loadActiveUserId } from "@/src/store/profile";
import type { ProfileSummary } from "@/src/types/api";

export default function BondScreen() {
  const [summary, setSummary] = useState<ProfileSummary | null>(null);

  useEffect(() => {
    async function boot() {
      const userId = (await loadActiveUserId()) || "guest";
      try {
        setSummary(await fetchProfileSummary(userId));
      } catch {
        // scaffold shell
      }
    }
    void boot();
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.shell}>
        <Text style={styles.eyebrow}>Bond</Text>
        <Text style={styles.title}>Relationship track</Text>
        <Text style={styles.copy}>This is the mobile-facing bond layer. Operational settings and admin controls stay in the browser on your computer.</Text>
        <BondCard summary={summary} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, padding: 18, gap: 14 },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12 },
  title: { color: "#f2efe9", fontSize: 28, fontWeight: "700" },
  copy: { color: "#d5d0c8", lineHeight: 22 },
});
