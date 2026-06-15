import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useState } from "react";

export function Composer({ onSend, disabled }: { onSend: (text: string) => Promise<void> | void; disabled?: boolean }) {
  const [text, setText] = useState("");

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed || disabled) {
      return;
    }
    setText("");
    await onSend(trimmed);
  }

  return (
    <View style={styles.wrap}>
      <TextInput
        style={styles.input}
        placeholder="Say something to Nellie..."
        placeholderTextColor="#7f8792"
        value={text}
        onChangeText={setText}
        multiline
      />
      <TouchableOpacity style={[styles.button, disabled ? styles.buttonDisabled : null]} onPress={submit} disabled={disabled}>
        <Text style={styles.buttonText}>{disabled ? "..." : "Send"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 8,
  },
  input: {
    minHeight: 58,
    maxHeight: 88,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    backgroundColor: "rgba(255,255,255,0.04)",
    color: "#f2efe9",
    paddingHorizontal: 14,
    paddingVertical: 10,
    textAlignVertical: "top",
  },
  button: {
    alignSelf: "flex-end",
    backgroundColor: "#ff7b54",
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 999,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: "#111111",
    fontWeight: "700",
  },
});
