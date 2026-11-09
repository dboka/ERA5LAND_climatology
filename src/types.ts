export type PeriodKind = 'day' | 'week' | 'range' | 'month' | 'season' | 'year';
export type Season = 'DJF' | 'MAM' | 'JJA' | 'SON';
export interface Metadata { first_date: string | null; latest_date: string | null; countries_with_data: number; mode: 'demo' | 'era5_land'; source: string; baseline: string }
export interface CountryRecord { iso3: string; name: string; status: 'member' | 'observer'; quality: 'grid' | 'limited' | 'proxy' | 'unavailable'; grid_cells: number; coverage: number; note: string; actual: number; normal: number; anomaly: number; days: number; provisional: boolean }
export interface Anomalies { start: string; end: string; mode: string; countries: CountryRecord[] }
export interface Series { iso3: string; grouping: 'day' | 'month'; points: { date: string; actual: number; normal: number; anomaly: number; days: number }[] }

export const isoDate = (d: Date) => d.toISOString().slice(0, 10);
export function periodDates(kind: PeriodKind, anchor: string, endInput: string, season: Season): [string, string] {
  const d = new Date(`${anchor}T12:00:00Z`);
  const year = d.getUTCFullYear(), month = d.getUTCMonth();
  if (kind === 'day') return [anchor, anchor];
  if (kind === 'week') {
    const monday = new Date(Date.UTC(year, month, d.getUTCDate() - (d.getUTCDay() + 6) % 7));
    return [isoDate(monday), isoDate(new Date(Date.UTC(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate() + 6)))];
  }
  if (kind === 'range') return [anchor, endInput];
  if (kind === 'month') return [isoDate(new Date(Date.UTC(year, month, 1))), isoDate(new Date(Date.UTC(year, month + 1, 0)))];
  if (kind === 'year') return [`${year}-01-01`, `${year}-12-31`];
  const months = { DJF: [year - 1, 11, year, 1], MAM: [year, 2, year, 4], JJA: [year, 5, year, 7], SON: [year, 8, year, 10] }[season];
  return [isoDate(new Date(Date.UTC(months[0], months[1], 1))), isoDate(new Date(Date.UTC(months[2], months[3] + 1, 0)))];
}
export function periodLabel(kind: PeriodKind, start: string, end: string, season: Season): string {
  const year = Number(start.slice(0, 4));
  const month = new Intl.DateTimeFormat('lv-LV', { month: 'long', timeZone: 'UTC' }).format(new Date(`${start}T12:00:00Z`));
  const day = new Intl.DateTimeFormat('lv-LV', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${start}T12:00:00Z`));
  const shortDate = (date: string) => `${date.slice(8, 10)}.${date.slice(5, 7)}.${date.slice(0, 4)}`;
  if (kind === 'day') return day;
  if (kind === 'week' || kind === 'range') return `Periods no ${shortDate(start)} līdz ${shortDate(end)}`;
  if (kind === 'month') return `${year}. gada ${month}`;
  if (kind === 'year') return `${year}. gads`;
  const seasonName: Record<Season, string> = { DJF: 'ziema', MAM: 'pavasaris', JJA: 'vasara', SON: 'rudens' };
  const seasonYear = Number(start.slice(0, 4)) + (season === 'DJF' ? 1 : 0);
  return season === 'DJF' ? `${seasonYear - 1}./${seasonYear}. gada ziema` : `${seasonYear}. gada ${seasonName[season]}`;
}
export function anomalyColor(value: number | null): string {
  if (value === null) return '#60798a';
  const stops: [number, string][] = [[-6,'#214f9b'],[-3,'#5d9bd3'],[-1,'#b9d9e6'],[0,'#f3f0e9'],[1,'#f1bcaa'],[3,'#d96d64'],[6,'#992d4f']];
  const clamped = Math.max(-6, Math.min(6, value));
  for (let i=1;i<stops.length;i++) if (clamped <= stops[i][0]) {
    const t=(clamped-stops[i-1][0])/(stops[i][0]-stops[i-1][0]);
    const a=stops[i-1][1].match(/\w\w/g)!.map(x=>parseInt(x,16));
    const b=stops[i][1].match(/\w\w/g)!.map(x=>parseInt(x,16));
    return '#'+a.map((v,j)=>Math.round(v+(b[j]-v)*t).toString(16).padStart(2,'0')).join('');
  }
  return stops.at(-1)![1];
}
