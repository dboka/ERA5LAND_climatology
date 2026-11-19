import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { periodDates, type PeriodKind, type Season } from './types';

const MODES: { id: PeriodKind; label: string }[] = [
  { id: 'day', label: 'Diena' },
  { id: 'week', label: 'Nedēļa' },
  { id: 'range', label: 'Intervāls' },
  { id: 'month', label: 'Mēnesis' },
  { id: 'season', label: 'Sezona' },
  { id: 'year', label: 'Gads' },
];
const MONTHS = Array.from({ length: 12 }, (_, month) =>
  new Intl.DateTimeFormat('lv-LV', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2020, month, 1))));
const SEASONS: { id: Season; label: string; months: string }[] = [
  { id: 'DJF', label: 'Ziema', months: 'dec.–feb.' },
  { id: 'MAM', label: 'Pavasaris', months: 'mar.–mai.' },
  { id: 'JJA', label: 'Vasara', months: 'jūn.–aug.' },
  { id: 'SON', label: 'Rudens', months: 'sep.–nov.' },
];
const WEEKDAYS = ['Pr', 'Ot', 'Tr', 'Ce', 'Pk', 'Se', 'Sv'];
const pad = (value: number) => String(value).padStart(2, '0');
const shortDate = (date: string) => `${date.slice(8, 10)}.${date.slice(5, 7)}.${date.slice(0, 4)}`;
const longDate = (date: string) => new Intl.DateTimeFormat('lv-LV', {
  day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
}).format(new Date(`${date}T12:00:00Z`));

function CalendarDateField({ label, value, min, max, onChange }: {
  label: string; value: string; min: string; max?: string; onChange: (date: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(value.slice(0, 7));
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape); };
  }, [open]);

  const [year, monthNumber] = viewMonth.split('-').map(Number);
  const monthIndex = monthNumber - 1;
  const firstWeekday = (new Date(Date.UTC(year, monthIndex, 1)).getUTCDay() + 6) % 7;
  const daysInMonth = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  const cells = Math.ceil((firstWeekday + daysInMonth) / 7) * 7;
  const moveMonth = (direction: number) => new Date(Date.UTC(year, monthIndex + direction, 1)).toISOString().slice(0, 7);
  const previous = moveMonth(-1);
  const next = moveMonth(1);
  const previousMonthEnd = new Date(Date.UTC(year, monthIndex, 0)).toISOString().slice(0, 10);

  return <div className="calendar-field" ref={root}>
    <span className="period-field-label">{label}</span>
    <button ref={trigger} type="button" className={`calendar-trigger ${open ? 'open' : ''}`}
      aria-label={`${label}: ${longDate(value)}`} aria-expanded={open} aria-haspopup="dialog"
      onClick={() => { setViewMonth(value.slice(0, 7)); setOpen(!open); }}>
      <span>{shortDate(value)}</span><CalendarDays size={17}/>
    </button>
    {open && <div className="calendar-popover" role="dialog" aria-label={`${label} izvēle`}>
      <div className="calendar-month-bar">
        <button type="button" aria-label="Iepriekšējais mēnesis" disabled={previousMonthEnd < min} onClick={() => setViewMonth(previous)}><ChevronLeft size={17}/></button>
        <strong>{year}. gada {MONTHS[monthIndex]}</strong>
        <button type="button" aria-label="Nākamais mēnesis" disabled={Boolean(max && `${next}-01` > max)} onClick={() => setViewMonth(next)}><ChevronRight size={17}/></button>
      </div>
      <div className="calendar-grid">
        {WEEKDAYS.map(day => <span className="calendar-weekday" key={day}>{day}</span>)}
        {Array.from({ length: cells }, (_, index) => {
          const day = index - firstWeekday + 1;
          if (day < 1 || day > daysInMonth) return <span aria-hidden="true" key={index}/>;
          const date = `${viewMonth}-${pad(day)}`;
          return <button type="button" key={date} className={date === value ? 'selected' : ''}
            aria-label={longDate(date)} aria-pressed={date === value}
            disabled={date < min || Boolean(max && date > max)}
            onClick={() => { onChange(date); setOpen(false); trigger.current?.focus(); }}>{day}</button>;
        })}
      </div>
    </div>}
  </div>;
}

export default function PeriodPicker({ kind, anchor, endInput, season, firstDate, latestDate, title, start, end, valid,
  onKind, onAnchor, onEnd, onSeason }: {
  kind: PeriodKind; anchor: string; endInput: string; season: Season; firstDate?: string | null; latestDate?: string | null;
  title: string; start: string; end: string; valid: boolean;
  onKind: (kind: PeriodKind) => void; onAnchor: (date: string) => void;
  onEnd: (date: string) => void; onSeason: (season: Season) => void;
}) {
  const earliest = firstDate || '2020-01-01';
  const firstWeek = new Date(`${earliest}T12:00:00Z`);
  firstWeek.setUTCDate(firstWeek.getUTCDate() + (8 - firstWeek.getUTCDay()) % 7);
  const firstWeekDate = firstWeek.toISOString().slice(0, 10);
  const selectedYear = Number(anchor.slice(0, 4));
  const selectedMonth = anchor.slice(5, 7);
  const latestYear = Number(latestDate?.slice(0, 4) || anchor.slice(0, 4));
  const years = Array.from({ length: Math.max(0, latestYear - Number(earliest.slice(0, 4)) + 1) }, (_, index) => latestYear - index);
  const setMonthYear = (year: number, month: string) => {
    const requested = `${year}-${month}`;
    const selected = latestDate && requested > latestDate.slice(0, 7) ? latestDate.slice(0, 7) : requested;
    onAnchor(`${selected}-01`);
  };
  const changeStart = (date: string) => { onAnchor(date); if (kind === 'range' && endInput < date) onEnd(date); };
  const seasonUnavailable = (code: Season, year: number) => {
    const [first] = periodDates('season', `${year}-01-01`, '', code);
    return first < earliest || Boolean(latestDate && first > latestDate);
  };

  return <section className="period-picker" aria-label="Laika perioda izvēle">
    <div className="period-picker-heading"><CalendarDays size={18}/><span>Laika periods</span></div>
    <div className="period-modes" role="group" aria-label="Perioda veids">
      {MODES.map(mode => <button type="button" key={mode.id} className={kind === mode.id ? 'active' : ''}
        aria-pressed={kind === mode.id} onClick={() => {
          if (mode.id === 'week' && anchor < firstWeekDate) onAnchor(firstWeekDate);
          onKind(mode.id);
        }}>{mode.label}</button>)}
    </div>
    <div className="period-controls">
      {kind === 'day' && <CalendarDateField label="Izvēlies dienu" value={anchor} min={earliest} max={latestDate || undefined} onChange={onAnchor}/>}
      {kind === 'week' && <><CalendarDateField label="Izvēlies nedēļas dienu" value={anchor} min={firstWeekDate} max={latestDate || undefined} onChange={onAnchor}/><p className="period-helper">Nedēļa ilgst no pirmdienas līdz svētdienai.</p></>}
      {kind === 'range' && <div className="period-range-fields">
        <CalendarDateField label="No" value={anchor} min={earliest} max={latestDate || undefined} onChange={changeStart}/>
        <CalendarDateField label="Līdz" value={endInput} min={anchor} max={latestDate || undefined} onChange={onEnd}/>
      </div>}
      {kind === 'month' && <div className="period-select-row">
        <label className="period-select-field period-month-field"><span className="period-field-label">Mēnesis</span><select value={selectedMonth} onChange={event => setMonthYear(selectedYear, event.target.value)}>
          {MONTHS.map((name, index) => { const month = pad(index + 1); return <option key={month} value={month} disabled={`${selectedYear}-${month}` < earliest.slice(0, 7) || Boolean(latestDate && `${selectedYear}-${month}` > latestDate.slice(0, 7))}>{name.charAt(0).toUpperCase() + name.slice(1)}</option>; })}
        </select><ChevronDown size={16}/></label>
        <label className="period-select-field period-year-field"><span className="period-field-label">Gads</span><select value={selectedYear} onChange={event => setMonthYear(Number(event.target.value), selectedMonth)}>
          {years.map(year => <option key={year} value={year}>{year}</option>)}
        </select><ChevronDown size={16}/></label>
      </div>}
      {(kind === 'season' || kind === 'year') && <label className="period-select-field period-full-field"><span className="period-field-label">Gads</span><select value={selectedYear} onChange={event => onAnchor(`${event.target.value}-01-01`)}>
        {years.map(year => <option key={year} value={year} disabled={kind === 'season' && seasonUnavailable(season, year)}>{year}</option>)}
      </select><ChevronDown size={16}/></label>}
      {kind === 'season' && <div className="season-options" role="group" aria-label="Meteoroloģiskā sezona">
        {SEASONS.map(item => <button type="button" key={item.id} className={season === item.id ? 'active' : ''}
          aria-pressed={season === item.id} disabled={seasonUnavailable(item.id, selectedYear)} onClick={() => onSeason(item.id)}>
          <strong>{item.label}</strong><span>{item.months}</span>
        </button>)}
      </div>}
      {!valid && latestDate && <p className="period-error" role="alert">Šis periods nav pieejams. Izvēlies datumu no {shortDate(earliest)} līdz {shortDate(latestDate)}.</p>}
      <div className="period-selection" aria-live="polite">
        <span className="period-selection-label">Kartē redzams</span>
        <strong>{valid ? title : 'Nav pieejamu datu'}</strong>
        {valid && <small>{shortDate(start)} — {shortDate(end)}</small>}
      </div>
    </div>
  </section>;
}
