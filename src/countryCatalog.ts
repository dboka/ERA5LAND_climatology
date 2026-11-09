import catalogJson from './countryCatalog.json';

type CountryUi = { iso2: string; name: string; flag: string };
const catalog = catalogJson as Record<string, CountryUi>;

export const countryOptions = Object.entries(catalog).map(([iso3, country]) => ({ iso3, name: country.name }));

export function countryDisplayName(iso3: string, fallback: string): string {
  return catalog[iso3]?.name || fallback;
}

export function countryFlagUrl(iso3: string): string | null {
  const flag = catalog[iso3]?.flag;
  return flag ? `${import.meta.env.BASE_URL}${flag}` : null;
}
