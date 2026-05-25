import enUS from "./messages/en-US.json";

export type LocaleId = "en-US";

export const DEFAULT_LOCALE: LocaleId = "en-US";

const MESSAGES: Record<LocaleId, Record<string, string>> = {
  "en-US": enUS,
};

const reportedMissing = new Set<string>();

export function t(key: string, locale: LocaleId = DEFAULT_LOCALE): string {
  const value = MESSAGES[locale][key];
  if (typeof value === "string") {
    return value;
  }
  if (process.env.NODE_ENV !== "production" && !reportedMissing.has(key)) {
    reportedMissing.add(key);
    console.warn(`[i18n] missing key for locale ${locale}: ${key}`);
  }
  return key;
}
