type RecordingSession = {
  stop: () => Promise<Int16Array>;
};

type AudioContextLike = typeof AudioContext;

const WORKLET_PROCESSOR_NAME = "nellie-recorder-processor";
const WORKLET_SOURCE = `
class NellieRecorderProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (channel && channel.length) {
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}
registerProcessor("${WORKLET_PROCESSOR_NAME}", NellieRecorderProcessor);
`;

function getAudioContextCtor(): AudioContextLike | undefined {
  return window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

function downsampleBuffer(buffer: Float32Array, inputSampleRate: number, outputSampleRate: number): Float32Array {
  if (outputSampleRate >= inputSampleRate) {
    return buffer;
  }
  const ratio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i += 1) {
      accum += buffer[i];
      count += 1;
    }
    result[offsetResult] = count ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function toInt16Pcm(buffer: Float32Array): Int16Array {
  const result = new Int16Array(buffer.length);
  for (let i = 0; i < buffer.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, buffer[i]));
    result[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return result;
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

async function beginWorkletRecording(
  audioContext: AudioContext,
  stream: MediaStream,
  targetSampleRate: number,
): Promise<RecordingSession> {
  const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
  const workletUrl = URL.createObjectURL(blob);
  await audioContext.audioWorklet.addModule(workletUrl);
  URL.revokeObjectURL(workletUrl);

  const source = audioContext.createMediaStreamSource(stream);
  const recorderNode = new AudioWorkletNode(audioContext, WORKLET_PROCESSOR_NAME, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
  });
  const muteGain = audioContext.createGain();
  muteGain.gain.value = 0;
  const chunks: Float32Array[] = [];

  recorderNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
    if (event.data?.length) {
      chunks.push(new Float32Array(event.data));
    }
  };

  source.connect(recorderNode);
  recorderNode.connect(muteGain);
  muteGain.connect(audioContext.destination);

  return {
    async stop() {
      recorderNode.port.onmessage = null;
      source.disconnect();
      recorderNode.disconnect();
      muteGain.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      await audioContext.close();
      return toInt16Pcm(downsampleBuffer(mergeChunks(chunks), audioContext.sampleRate, targetSampleRate));
    },
  };
}

function beginScriptProcessorRecording(
  audioContext: AudioContext,
  stream: MediaStream,
  targetSampleRate: number,
): RecordingSession {
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const muteGain = audioContext.createGain();
  muteGain.gain.value = 0;
  const chunks: Float32Array[] = [];

  processor.onaudioprocess = (event) => {
    const channel = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(channel));
  };

  source.connect(processor);
  processor.connect(muteGain);
  muteGain.connect(audioContext.destination);

  return {
    async stop() {
      processor.disconnect();
      source.disconnect();
      muteGain.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      await audioContext.close();
      return toInt16Pcm(downsampleBuffer(mergeChunks(chunks), audioContext.sampleRate, targetSampleRate));
    },
  };
}

export async function beginPcmRecording(targetSampleRate = 16000): Promise<RecordingSession> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      noiseSuppression: true,
      echoCancellation: true,
      autoGainControl: true,
    },
  });

  const AudioContextCtor = getAudioContextCtor();
  if (!AudioContextCtor) {
    stream.getTracks().forEach((track) => track.stop());
    throw new Error("AudioContext is not supported in this browser.");
  }

  const audioContext = new AudioContextCtor();

  try {
    if (audioContext.audioWorklet && typeof AudioWorkletNode !== "undefined") {
      return await beginWorkletRecording(audioContext, stream, targetSampleRate);
    }
  } catch {
    // Fall back quietly to ScriptProcessorNode if AudioWorklet setup fails.
  }

  return beginScriptProcessorRecording(audioContext, stream, targetSampleRate);
}
