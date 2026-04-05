import AsyncStorage from "@react-native-async-storage/async-storage";

export type MobileAuthSession = {
  userId: string;
  token: string;
};

const AUTH_SESSION_KEY = "nellie.mobile.auth.session";
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

export async function loginLocally(userId: string, password: string): Promise<MobileAuthSession> {
  const expected = DEFAULT_PASSWORDS[userId];
  if (!expected) {
    throw new Error("Unknown profile.");
  }
  if (String(password || "") !== expected) {
    throw new Error("Wrong password.");
  }
  const session = { userId, token: buildToken(userId) };
  await saveAuthSession(session);
  return session;
}

