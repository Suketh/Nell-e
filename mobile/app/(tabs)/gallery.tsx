import { useEffect, useState } from "react";
import { SafeAreaView, StyleSheet, Text, View } from "react-native";
import { fetchGalleryCatalog, fetchUnlockedGallery } from "@/src/api/client";
import { GalleryGrid } from "@/src/components/GalleryGrid";
import { loadActiveUserId } from "@/src/store/profile";
import type { GalleryItem } from "@/src/types/api";

export default function GalleryScreen() {
  const [catalog, setCatalog] = useState<GalleryItem[]>([]);
  const [unlocked, setUnlocked] = useState<GalleryItem[]>([]);

  useEffect(() => {
    async function boot() {
      const userId = (await loadActiveUserId()) || "guest";
      try {
        const [nextCatalog, nextUnlocked] = await Promise.all([
          fetchGalleryCatalog(userId),
          fetchUnlockedGallery(userId),
        ]);
        setCatalog(nextCatalog);
        setUnlocked(nextUnlocked);
      } catch {
        // scaffold shell
      }
    }
    void boot();
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.shell}>
        <Text style={styles.eyebrow}>Gallery</Text>
        <Text style={styles.title}>Nellie's rewards</Text>
        <Text style={styles.copy}>Mobile gets the intimate gallery. Admin curation and rollout still live best in the desktop browser.</Text>
        <GalleryGrid items={catalog} unlockedPaths={new Set(unlocked.map((item) => item.path))} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, padding: 18, gap: 14 },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12 },
  title: { color: "#f2efe9", fontSize: 28, fontWeight: "700" },
  copy: { color: "#d5d0c8", lineHeight: 22, marginBottom: 8 },
});
