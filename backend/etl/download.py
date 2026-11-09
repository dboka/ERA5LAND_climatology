"""Download CDS ERA5-Land UTC daily means in monthly files, outside request handling.

Requires ~/.cdsapirc and acceptance of the dataset licence in the CDS portal.
"""
import argparse
import calendar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import cdsapi
import zipfile

DATASET = 'derived-era5-land-daily-statistics'


def months(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', type=date.fromisoformat, default=date(1991, 1, 1))
    parser.add_argument('--through-date', type=date.fromisoformat, default=datetime.now(timezone.utc).date() - timedelta(days=6))
    parser.add_argument('--output', type=Path, default=Path('data/raw'))
    parser.add_argument('--refresh-months', type=int, default=3, help='Re-download the latest N calendar months to pick up provisional revisions')
    parser.add_argument('--recent-only', action='store_true', help='Download only the recent refresh window for --update')
    args = parser.parse_args()
    if args.refresh_months < 1:
        parser.error('--refresh-months must be at least 1')
    if args.recent_only:
        month_index = args.through_date.year * 12 + args.through_date.month - args.refresh_months
        args.from_date = date(month_index // 12, month_index % 12 + 1, 1)
    args.output.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    for year, month in months(args.from_date, args.through_date):
        first_day = 1 if (year, month) != (args.from_date.year, args.from_date.month) else args.from_date.day
        last_day = calendar.monthrange(year, month)[1] if (year, month) != (args.through_date.year, args.through_date.month) else args.through_date.day
        stem = f'era5_land_t2m_daily_{year}-{month:02d}'
        existing = [args.output / f'{stem}.{ext}' for ext in ('zip','nc')]
        age_months = (args.through_date.year - year) * 12 + args.through_date.month - month
        if any(p.exists() and p.stat().st_size > 0 for p in existing) and age_months >= args.refresh_months:
            print(f'Skip {stem}')
            continue
        request = {
            'variable': ['2m_temperature'], 'year': str(year), 'month': [f'{month:02d}'],
            'day': [f'{day:02d}' for day in range(first_day, last_day + 1)],
            'daily_statistic': 'daily_mean', 'time_zone': 'utc+00:00',
            'frequency': '1_hourly',
        }
        print(f'Request {year}-{month:02d}: {len(request["day"])} days')
        temporary = args.output / f'{stem}.partial'
        client.retrieve(DATASET, request, str(temporary))
        target = args.output / f'{stem}.{ "zip" if zipfile.is_zipfile(temporary) else "nc" }'
        temporary.replace(target)
        for previous in existing:
            if previous != target and previous.exists():
                previous.unlink()
        print(f'Saved {target}')


if __name__ == '__main__':
    main()
