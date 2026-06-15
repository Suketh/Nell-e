import { Audio, InterruptionModeAndroid, InterruptionModeIOS } from "expo-av";

let activeSound: Audio.Sound | null = null;

export async function playRemoteAudio(uri: string): Promise<{ loadMs: number; playMs: number }> {
  const loadStartedAt = Date.now();
  await Audio.setAudioModeAsync({
    allowsRecordingIOS: false,
    playsInSilentModeIOS: true,
    staysActiveInBackground: false,
    interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
    shouldDuckAndroid: true,
    playThroughEarpieceAndroid: false,
  });

  if (activeSound) {
    try {
      await activeSound.stopAsync();
      await activeSound.unloadAsync();
    } catch {
      // ignore stale sound state
    }
    activeSound = null;
  }

  const { sound, status } = await Audio.Sound.createAsync(
    { uri },
    {
      shouldPlay: false,
      volume: 1.0,
      rate: 1.0,
      shouldCorrectPitch: true,
      progressUpdateIntervalMillis: 200,
    },
    undefined,
    false,
  );
  activeSound = sound;
  sound.setOnPlaybackStatusUpdate((status) => {
    if ("didJustFinish" in status && status.didJustFinish) {
      void stopRemoteAudio();
    }
  });
  if (!("isLoaded" in status) || !status.isLoaded) {
    throw new Error("Audio stream could not be loaded.");
  }
  const loadMs = Date.now() - loadStartedAt;
  const playStartedAt = Date.now();
  await sound.playAsync();
  return {
    loadMs,
    playMs: Date.now() - playStartedAt,
  };
}

export async function stopRemoteAudio() {
  if (!activeSound) {
    return;
  }
  try {
    await activeSound.stopAsync();
  } catch {
    // ignore
  }
  try {
    await activeSound.unloadAsync();
  } catch {
    // ignore
  }
  activeSound = null;
}
