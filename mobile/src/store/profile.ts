import AsyncStorage from "@react-native-async-storage/async-storage";
import type { MobileProfile } from "@/src/types/api";

const PROFILE_KEY = "nellie.mobile.profiles";
const ACTIVE_PROFILE_KEY = "nellie.mobile.activeProfile";
const ACTIVE_PERSONA_KEY = "nellie.mobile.activePersona";
const BADGE_COLORS = ["#f2c14e", "#d96c75", "#5db7de", "#5dd39e", "#9b5de5", "#ff7b54"];

const DEFAULT_PROFILES: MobileProfile[] = [
  { userId: "guest", displayName: "Guest", badgeColor: BADGE_COLORS[0] },
  { userId: "admin-mobile", displayName: "Admin", badgeColor: BADGE_COLORS[5], isAdmin: true },
];

function normalizeProfiles(profiles: MobileProfile[] | null | undefined): MobileProfile[] {
  const items = Array.isArray(profiles) ? profiles.filter(Boolean) : [];
  const byId = new Map<string, MobileProfile>();
  for (const profile of DEFAULT_PROFILES) {
    byId.set(profile.userId, profile);
  }
  for (const profile of items) {
    if (!profile?.userId) {
      continue;
    }
    byId.set(profile.userId, {
      ...byId.get(profile.userId),
      ...profile,
      isAdmin: profile.userId === "admin-mobile" ? true : Boolean(profile.isAdmin),
    });
  }
  return [...byId.values()];
}

export async function loadProfiles(): Promise<MobileProfile[]> {
  const raw = await AsyncStorage.getItem(PROFILE_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as MobileProfile[];
      if (Array.isArray(parsed) && parsed.length) {
        return normalizeProfiles(parsed);
      }
    } catch {
      // ignore and rebuild
    }
  }
  return normalizeProfiles(DEFAULT_PROFILES);
}

export async function saveProfiles(profiles: MobileProfile[]) {
  await AsyncStorage.setItem(PROFILE_KEY, JSON.stringify(normalizeProfiles(profiles)));
}

export async function loadActiveUserId(): Promise<string | null> {
  return await AsyncStorage.getItem(ACTIVE_PROFILE_KEY);
}

export async function saveActiveUserId(userId: string) {
  await AsyncStorage.setItem(ACTIVE_PROFILE_KEY, userId);
}

export async function loadActivePersonaId(): Promise<string | null> {
  return await AsyncStorage.getItem(ACTIVE_PERSONA_KEY);
}

export async function saveActivePersonaId(personaId: string) {
  await AsyncStorage.setItem(ACTIVE_PERSONA_KEY, personaId);
}

export function createMobileProfile(displayName: string, existingProfiles: MobileProfile[]): MobileProfile {
  const name = String(displayName || "").trim() || "Traveler";
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "traveler";
  const existingIds = new Set(existingProfiles.map((profile) => profile.userId));
  let userId = slug;
  let suffix = 2;
  while (existingIds.has(userId)) {
    userId = `${slug}-${suffix}`;
    suffix += 1;
  }
  return {
    userId,
    displayName: name,
    badgeColor: BADGE_COLORS[existingProfiles.length % BADGE_COLORS.length],
  };
}
