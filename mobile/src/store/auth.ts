import AsyncStorage from "@react-native-async-storage/async-storage";

export type MobileAuthSession = {
  userId: string;
  token: string;
};

const AUTH_SESSION_KEY = "nellie.mobile.auth.session";
const CUSTOM_PASSWORDS_KEY = "nellie.mobile.auth.passwords";
const DEFAULT_PASSWORDS: Record<string, string> = {
  guest: "guest",
  "admin-mobile": "nellie",
};

function buildToken(userId: string) {
  return `local-${userId}-${Date.now()}`;
}

export async function loadAuthSession(): Promise<MobileAuthSession | null> {
  const raw = await AsyncStorage.getItem(AUTH_SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as MobileAuthSession;
    if (parsed?.userId && parsed?.token) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return null;
}

export async function saveAuthSession(session: MobileAuthSession) {
  await AsyncStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export async function clearAuthSession() {
  await AsyncStorage.removeItem(AUTH_SESSION_KEY);
}

async function loadCustomPasswords(): Promise<Record<string, string>> {
  const raw = await AsyncStorage.getItem(CUSTOM_PASSWORDS_KEY);
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw) as Record<string, string>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function saveCustomPasswords(passwords: Record<string, string>) {
  await AsyncStorage.setItem(CUSTOM_PASSWORDS_KEY, JSON.stringify(passwords));
}

export async function loginLocally(userId: string, password: string): Promise<MobileAuthSession> {
  const expected = DEFAULT_PASSWORDS[userId];
  const normalizedPassword = String(password || "");
  if (expected && String(password || "") !== expected) {
    throw new Error("Wrong password.");
  }
  if (!expected) {
    if (!normalizedPassword.trim()) {
      throw new Error("Choose a local password for this profile.");
    }
    const customPasswords = await loadCustomPasswords();
    const storedPassword = customPasswords[userId];
    if (storedPassword && normalizedPassword !== storedPassword) {
      throw new Error("Wrong password.");
    }
    if (!storedPassword) {
      customPasswords[userId] = normalizedPassword;
      await saveCustomPasswords(customPasswords);
    }
  }
  const session = { userId, token: buildToken(userId) };
  await saveAuthSession(session);
  return session;
}
