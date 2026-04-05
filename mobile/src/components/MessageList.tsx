import { FlatList, StyleSheet, Text, View } from "react-native";
import type { ChatMessage } from "@/src/types/api";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <FlatList
      data={messages}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.list}
      renderItem={({ item }) => (
        <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.assistantBubble]}>
          <Text style={styles.role}>{item.role === "user" ? "You" : "Nellie"}</Text>
          <Text style={styles.text}>{item.text}</Text>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  list: {
    gap: 12,
    paddingBottom: 16,
  },
  bubble: {
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
  },
  userBubble: {
    backgroundColor: "rgba(255,123,84,0.16)",
    borderColor: "rgba(255,123,84,0.32)",
  },
  assistantBubble: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderColor: "rgba(255,255,255,0.08)",
  },
  role: {
    color: "#9ea7b3",
    fontSize: 12,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  text: {
    color: "#f2efe9",
    fontSize: 15,
    lineHeight: 22,
  },
});
