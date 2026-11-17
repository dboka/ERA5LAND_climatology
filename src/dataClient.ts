import type { Anomalies, CountryRecord, Metadata, Metric, Series } from './types';
import { countryDisplayName } from './countryCatalog';

const STATIC = import.meta.env.VITE_STATIC_DATA === '1';
export const isStaticData = STATIC;
const base = `${import.meta.env.BASE_URL}data/`;
type CountryInfo = Pick<CountryRecord,'iso3'|'name'|'status'|'quality'|'grid_cells'|'coverage'|'note'>;
type Month = Record<string, Record<string, [number, boolean]>>;
let countriesPromise: Promise<CountryInfo[]> | null = null;
const normalsCache = new Map<Metric, Promise<Record<string, Record<string, number>>>>();
const monthCache = new Map<string, Promise<Month>>();
const metricBase = (metric:Metric) => metric === 'precipitation' ? `${base}precipitation/` : base;
const anomaly = (actual:number, normal:number, metric:Metric) => metric === 'precipitation'
  ? (normal > 0 ? (actual / normal - 1) * 100 : 0) : actual - normal;

async function json<T>(url:string, signal?:AbortSignal, fresh=false):Promise<T>{
  const response=await fetch(url,{signal,cache:fresh?'no-store':'default'});
  if(!response.ok){let detail='Datu ielāde neizdevās';try{detail=(await response.json()).detail||detail;}catch{ /* static 404 */ }throw new Error(detail);}
  return response.json();
}
function monthKeys(start:string,end:string){const result:string[]=[];let year=Number(start.slice(0,4)),month=Number(start.slice(5,7));const y2=Number(end.slice(0,4)),m2=Number(end.slice(5,7));while(year<y2||(year===y2&&month<=m2)){result.push(`${year}-${String(month).padStart(2,'0')}`);month++;if(month===13){year++;month=1;}}return result;}
function getMonth(metric:Metric,key:string){const cacheKey=`${metric}:${key}`;if(!monthCache.has(cacheKey))monthCache.set(cacheKey,json<Month>(`${metricBase(metric)}${key}.json`));return monthCache.get(cacheKey)!;}
async function staticData(metric:Metric,start:string,end:string){
  countriesPromise ||= json<CountryInfo[]>(`${base}countries.json`);
  if(!normalsCache.has(metric))normalsCache.set(metric,json<Record<string,Record<string,number>>>(`${metricBase(metric)}normals.json`));
  const keys=monthKeys(start,end);
  const [countries,normals,...months]=await Promise.all([countriesPromise,normalsCache.get(metric)!,...keys.map(key=>getMonth(metric,key))]);
  return {countries,normals,months,keys};
}
export function getMeta(metric:Metric,signal?:AbortSignal){return json<Metadata>(STATIC?`${metricBase(metric)}meta.json`:`/api/meta?metric=${metric}`,signal,true);}
function withLatvianNames(data:Anomalies):Anomalies{
  return {...data,countries:data.countries.map(country=>({...country,name:countryDisplayName(country.iso3,country.name)}))};
}
export async function getAnomalies(metric:Metric,start:string,end:string,signal?:AbortSignal):Promise<Anomalies>{
  if(!STATIC)return withLatvianNames(await json<Anomalies>(`/api/anomalies?start=${start}&end=${end}&metric=${metric}`,signal));
  const {countries,normals,months,keys}=await staticData(metric,start,end);
  const rows:CountryRecord[]=[];
  countries.forEach(c=>{
    let actual=0,normal=0,days=0,provisional=false;
    months.forEach((month,i)=>Object.entries(month[c.iso3]||{}).forEach(([dd,value])=>{
      const day=`${keys[i]}-${dd}`;if(day<start||day>end)return;
      const norm=normals[c.iso3]?.[day.slice(5)];if(norm===undefined)return;
      actual+=value[0];normal+=norm;days++;provisional ||= value[1];
    }));
    if(days)rows.push({...c,actual:metric==='precipitation'?actual:actual/days,
      normal:metric==='precipitation'?normal:normal/days,anomaly:anomaly(actual,normal,metric),days,provisional});
  });
  return withLatvianNames({start,end,mode:'static',countries:rows});
}
export async function getSeries(metric:Metric,iso3:string,start:string,end:string,signal?:AbortSignal):Promise<Series>{
  if(!STATIC)return json<Series>(`/api/countries/${iso3}/series?start=${start}&end=${end}&metric=${metric}`,signal);
  const {normals,months,keys}=await staticData(metric,start,end);
  const grouping=(new Date(end).getTime()-new Date(start).getTime())/86400000<=45?'day':'month';
  const buckets=new Map<string,{actual:number;normal:number;days:number}>();
  months.forEach((month,i)=>Object.entries(month[iso3]||{}).forEach(([dd,value])=>{
    const day=`${keys[i]}-${dd}`;if(day<start||day>end)return;
    const normal=normals[iso3]?.[day.slice(5)];if(normal===undefined)return;
    const key=grouping==='day'?day:keys[i];const b=buckets.get(key)||{actual:0,normal:0,days:0};
    b.actual+=value[0];b.normal+=normal;b.days++;buckets.set(key,b);
  }));
  return {iso3,grouping,points:[...buckets.entries()].map(([date,b])=>({date,
    actual:metric==='precipitation'?b.actual:b.actual/b.days,
    normal:metric==='precipitation'?b.normal:b.normal/b.days,
    anomaly:anomaly(b.actual,b.normal,metric),days:b.days}))};
}
