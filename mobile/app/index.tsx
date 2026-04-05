import { Link } from "expo-router";
import { SafeAreaView, StyleSheet, Text, View } from "react-native";

export default function IndexScreen() {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.shell}>
        <Text style={styles.eyebrow}>Nellie Mobile</Text>
        <Text style={styles.title}>App shell is alive</Text>
        <Text style={styles.copy}>
          If you can read this, Expo is rendering correctly. Use the link below to enter the first chat screen.
        </Text>
        <Link href="/chat" style={styles.link}>
          Open chat
        </Link>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0e1116" },
  shell: { flex: 1, padding: 24, justifyContent: "center", gap: 14 },
  eyebrow: { color: "#ffd2a6", textTransform: "uppercase", letterSpacing: 2, fontSize: 12 },
  title: { color: "#f2efe9", fontSize: 30, fontWeight: "700" },
  copy: { color: "#d5d0c8", lineHeight: 22 },
  link: {
    color: "#ff7b54",
    fontSize: 18,
    fontWeight: "700",
    marginTop: 6,
  },
});
