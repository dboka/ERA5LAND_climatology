/** Freeze Latvian display names and local flag files for the approved 195 states. */
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import countries from 'i18n-iso-countries';

const require = createRequire(import.meta.url);
countries.registerLocale(require('i18n-iso-countries/langs/lv.json'));
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = JSON.parse(await readFile(join(root, 'backend', 'country_catalog.json'), 'utf8'));
const flagsSource = join(root, 'node_modules', 'flag-icons');
const flagsTarget = join(root, 'public', 'flags');
const displayNames = new Intl.DisplayNames('lv-LV', { type: 'region' });
const overrides = { PSE: 'Palestīna', VAT: 'Vatikāns' };
const catalog = {};

if (source.countries.length !== 195) throw new Error('Expected the approved 195-country roster');
await mkdir(flagsTarget, { recursive: true });
for (const country of source.countries) {
  const iso2 = countries.alpha3ToAlpha2(country.iso3);
  if (!iso2) throw new Error(`No ISO alpha-2 code for ${country.iso3}`);
  const name = overrides[country.iso3] || displayNames.of(iso2) || countries.getName(country.iso3, 'lv');
  if (!name || name === iso2) throw new Error(`No Latvian name for ${country.iso3}`);
  const flag = `${iso2.toLowerCase()}.svg`;
  await copyFile(join(flagsSource, 'flags', '4x3', flag), join(flagsTarget, flag));
  catalog[country.iso3] = { iso2, name, flag: `flags/${flag}` };
}
await copyFile(join(flagsSource, 'LICENSE'), join(flagsTarget, 'LICENSE'));
await writeFile(join(root, 'src', 'countryCatalog.json'), `${JSON.stringify(catalog, null, 2)}\n`, 'utf8');
console.log(`Prepared ${Object.keys(catalog).length} Latvian country names and flags`);
