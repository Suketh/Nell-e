import * as Notifications from "expo-notifications";

let notificationHandlerReady = false;

type PhoneActionResult = {
  spoken: string;
  hint: string;
};

type TimerIntent = {
  seconds: number;
  label: string;
};

type AlarmIntent = {
  hour: number;
  minute: number;
  label: string;
  when: Date;
};

async function ensureNotificationPermission(): Promise<void> {
  if (!notificationHandlerReady) {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    notificationHandlerReady = true;
  }
    const permissions = await Notifications.getPermissionsAsync();
  if (permissions.granted || permissions.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL) {
    return;
  }
  const requested = await Notifications.requestPermissionsAsync();
  if (!requested.granted && requested.ios?.status !== Notifications.IosAuthorizationStatus.PROVISIONAL) {
    throw new Error("Notification permission is required for phone timers and alarms.");
  }
}

function parseTimerIntent(text: string): TimerIntent | null {
  const compact = String(text || "").trim().toLowerCase();
  const patterns = [
    /\b(?:set|start|create|run|satt|sätt|starta)\s+(?:a|an|en)?\s*timer(?:\s+(?:for|on|at|på))?\s+(\d{1,3})\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|sekunder|minuter|timmar)\b/i,
    /\b(\d{1,3})\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|sekunder|minuter|timmar)\s+timer\b/i,
  ];
  for (const pattern of patterns) {
    const match = compact.match(pattern);
    if (!match) {
      continue;
    }
    const amount = Number.parseInt(match[1] || "", 10);
    if (!Number.isFinite(amount) || amount <= 0) {
      return null;
    }
    const unit = String(match[2] || "").toLowerCase();
    let multiplier = 60;
    let labelUnit = "minute";
    if (/(second|sec|sekund)/i.test(unit)) {
      multiplier = 1;
      labelUnit = "second";
    } else if (/(hour|hr|tim)/i.test(unit)) {
      multiplier = 3600;
      labelUnit = "hour";
    }
    const seconds = amount * multiplier;
    const plural = amount === 1 ? labelUnit : `${labelUnit}s`;
    return {
      seconds,
      label: `${amount} ${plural}`,
    };
  }
  return null;
}

function nextOccurrence(hour: number, minute: number): Date {
  const now = new Date();
  const target = new Date(now);
  target.setSeconds(0, 0);
  target.setHours(hour, minute, 0, 0);
  if (target.getTime() <= now.getTime()) {
    target.setDate(target.getDate() + 1);
  }
  return target;
}

function parseAlarmIntent(text: string): AlarmIntent | null {
  const compact = String(text || "").trim().toLowerCase();
  const patterns = [
    /\b(?:set|create|add|wake me|alarm me|satt|sätt|ställ)\s+(?:an?|ett)?\s*alarm(?:\s+(?:for|at|på))?\s*(?:kl\.?\s*)?(\d{1,2})[:.](\d{2})\b/i,
    /\balarm\b.*?(?:kl\.?\s*)?(\d{1,2})[:.](\d{2})\b/i,
  ];
  for (const pattern of patterns) {
    const match = compact.match(pattern);
    if (!match) {
      continue;
    }
    const hour = Number.parseInt(match[1] || "", 10);
    const minute = Number.parseInt(match[2] || "", 10);
    if (!Number.isFinite(hour) || !Number.isFinite(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return null;
    }
    const when = nextOccurrence(hour, minute);
    return {
      hour,
      minute,
      when,
      label: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
    };
  }
  return null;
}

async function scheduleTimer(intent: TimerIntent): Promise<PhoneActionResult> {
  await ensureNotificationPermission();
  await Notifications.scheduleNotificationAsync({
    content: {
      title: "Nellie timer",
      body: `Your ${intent.label} timer is done.`,
      sound: true,
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds: intent.seconds,
    },
  });
  return {
    spoken: `I set a ${intent.label} timer on your phone.`,
    hint: `Phone timer set for ${intent.label}.`,
  };
}

async function scheduleAlarm(intent: AlarmIntent): Promise<PhoneActionResult> {
  await ensureNotificationPermission();
  await Notifications.scheduleNotificationAsync({
    content: {
      title: "Nellie alarm",
      body: `Alarm for ${intent.label}.`,
      sound: true,
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DATE,
      date: intent.when,
    },
  });
  const dayLabel = intent.when.toDateString() === new Date().toDateString() ? "today" : "tomorrow";
  return {
    spoken: `I set an alarm for ${intent.label} on your phone.`,
    hint: `Phone alarm set for ${intent.label} ${dayLabel}.`,
  };
}

export async function maybeRunPhoneAction(
  text: string,
  enabledFeatureIds: Set<string>,
): Promise<PhoneActionResult | null> {
  const timerIntent = parseTimerIntent(text);
  if (timerIntent && enabledFeatureIds.has("device_timers")) {
    return scheduleTimer(timerIntent);
  }
  const alarmIntent = parseAlarmIntent(text);
  if (alarmIntent && enabledFeatureIds.has("device_alarms")) {
    return scheduleAlarm(alarmIntent);
  }
  return null;
}
