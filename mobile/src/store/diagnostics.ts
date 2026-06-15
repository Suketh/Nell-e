import AsyncStorage from "@react-native-async-storage/async-storage";

const DIAGNOSTICS_KEY = "nellie.mobile.diagnosticsEnabled";

export async function loadDiagnosticsEnabled(): Promise<boolean> {
  const raw = await AsyncStorage.getItem(DIAGNOSTICS_KEY);
  return raw === "1";
}

export async function saveDiagnosticsEnabled(enabled: boolean) {
  await AsyncStorage.setItem(DIAGNOSTICS_KEY, enabled ? "1" : "0");
}
