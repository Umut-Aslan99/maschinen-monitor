const de1 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const de = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 });

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${de1.format(x)} %`);
export const num = (x: number | null | undefined, decimals?: number) =>
  x === null || x === undefined ? '–'
    : decimals === undefined ? de.format(x)
      : new Intl.NumberFormat('de-DE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(x);
export const int = (x: number) => new Intl.NumberFormat('de-DE').format(x);

/** 47 min · 1 h 05 min · 2 d 3 h */
export function duration(minutes: number): string {
  const m = Math.round(minutes);
  if (m < 60) return `${m} min`;
  if (m < 24 * 60) return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
  return `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`;
}

export const minutesSince = (iso: string | null, now = Date.now()) => (iso ? Math.max(0, (now - Date.parse(iso)) / 60000) : 0);

const timeFmt = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' });
const dayTimeFmt = new Intl.DateTimeFormat('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' });
const dayFmt = new Intl.DateTimeFormat('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'Europe/Berlin' });

export const time = (d: string | number | Date) => timeFmt.format(new Date(d));
export const dayTime = (d: string | number | Date) => dayTimeFmt.format(new Date(d));
export const day = (d: string | number | Date) => dayFmt.format(new Date(d));
/** Today's times without date, older ones with weekday and date. */
export const when = (d: string) => (new Date(d).toDateString() === new Date().toDateString() ? time(d) : dayTime(d));
