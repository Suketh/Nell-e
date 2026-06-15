import { Audio, InterruptionModeAndroid, InterruptionModeIOS } from "expo-av";

let activeRecording: Audio.Recording | null = null;

export async function requestRecordingPermission(): Promise<boolean> {
  const permission = await Audio.requestPermissionsAsync();
  return Boolean(permission.granted);
}

export async function startNativeRecording(): Promise<void> {
  const granted = await requestRecordingPermission();
  if (!granted) {
    throw new Error("Microphone permission was not granted.");
  }

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
    staysActiveInBackground: false,
    interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
    shouldDuckAndroid: true,
    playThroughEarpieceAndroid: false,
  });

  if (activeRecording) {
    await stopNativeRecording();
  }

  const recording = new Audio.Recording();
  await recording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
  await recording.startAsync();
  activeRecording = recording;
}

export async function stopNativeRecording(): Promise<string | null> {
  if (!activeRecording) {
    return null;
  }
  try {
    await activeRecording.stopAndUnloadAsync();
    return activeRecording.getURI();
  } finally {
    activeRecording = null;
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      staysActiveInBackground: false,
      interruptionModeIOS: InterruptionModeIOS.DoNotMix,
      interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    });
  }
}
