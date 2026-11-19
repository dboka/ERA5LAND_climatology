import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChevronDown, CircleHelp, CloudRain, Download, Info, Layers3, Search, Thermometer, X } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ClimateMap from './ClimateMap';
import { getAnomalies, getMeta, getSeries, isStaticData } from './dataClient';
import { countryDisplayName, countryFlagUrl, countryOptions } from './countryCatalog';
import PeriodPicker from './PeriodPicker';
import { anomalyColor, periodDates, periodLabel, type Anomalies, type CountryRecord, type Metadata, type Metric, type PeriodKind, type Season, type Series } from './types';

const fmt = (v:number, metric:Metric, digits=1) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)} ${metric==='precipitation'?'%':'°C'}`;
const amount = (v:number, metric:Metric) => `${v.toFixed(metric==='precipitation' && v<1 ? 2 : 1)} ${metric==='precipitation'?'mm':'°C'}`;
const displayDate = (value:string) => `${value.slice(8,10)}.${value.slice(5,7)}.${value.slice(0,4)}`;

function csvDownload(rows:CountryRecord[], start:string,end:string, mode:string, metric:Metric) {
  const unit=metric==='precipitation'?'mm':'c';
  const header=`iso3,country,un_status,start,end,actual_${unit},normal_${unit},anomaly_${metric==='precipitation'?'percent':'c'},quality,provisional,data_mode`;
  const lines=rows.map(r=>[r.iso3,`"${r.name.replaceAll('"','""')}"`,r.status,start,end,r.actual,r.normal,r.anomaly,r.quality,r.provisional,mode].join(','));
  const url=URL.createObjectURL(new Blob([[header,...lines].join('\n')],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`climate-${metric}-${start}-${end}.csv`;a.click();URL.revokeObjectURL(url);
}

export default function App() {
  const [metric,setMetric]=useState<Metric>('temperature');
  const [metaByMetric,setMetaByMetric]=useState<Partial<Record<Metric,Metadata>>>({});
  const meta=metaByMetric[metric]||null;
  const [kind,setKind]=useState<PeriodKind>('month');
  const [anchor,setAnchor]=useState('2026-09-01');
  const [endInput,setEndInput]=useState('2026-09-14');
  const [season,setSeason]=useState<Season>('SON');
  const [data,setData]=useState<Anomalies|null>(null);
  const [series,setSeries]=useState<Series|null>(null);
  const [selected,setSelected]=useState<string|null>('LVA');
  const [query,setQuery]=useState('');
  const [searchOpen,setSearchOpen]=useState(false);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [about,setAbout]=useState(false);
  const [panelOpen,setPanelOpen]=useState(()=>window.innerWidth>960);
  const initializedMeta=useRef(false);
  const latestMetaDate=useRef<Partial<Record<Metric,string|null>>>({});
  const [rangeStart,rangeEnd]=periodDates(kind,anchor,endInput,season);
  const valid=Boolean(meta?.first_date && meta?.latest_date && rangeStart>=meta.first_date && rangeStart<=rangeEnd && rangeStart<=meta.latest_date);
  const effectiveEnd=meta?.latest_date && rangeEnd>meta.latest_date ? meta.latest_date : rangeEnd;
  const partial=valid && effectiveEnd<rangeEnd;

  useEffect(()=>{
    let active=true;
    const refresh=()=>getMeta(metric).then((m:Metadata)=>{
      if(!active)return;
      if(isStaticData && latestMetaDate.current[metric] && m.latest_date!==latestMetaDate.current[metric]){window.location.reload();return;}
      latestMetaDate.current[metric]=m.latest_date;
      setMetaByMetric(previous=>({...previous,[metric]:m}));
      if(!initializedMeta.current && m.latest_date){
        initializedMeta.current=true;
        const d=new Date(`${m.latest_date}T12:00:00Z`);d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-1);
        setAnchor(d.toISOString().slice(0,10));setEndInput(m.latest_date);
      }
      const latest=m.latest_date;
      if(latest){setAnchor(previous=>previous>latest?latest:previous);setEndInput(previous=>previous>latest?latest:previous);}
    }).catch(()=>{if(active && !initializedMeta.current)setError('API nav sasniedzams. Palaidiet FastAPI serveri.');});
    void refresh();
    const timer=window.setInterval(()=>{void refresh();},5*60*1000);
    const visible=()=>{if(document.visibilityState==='visible')void refresh();};
    const focused=()=>{void refresh();};
    document.addEventListener('visibilitychange',visible);
    window.addEventListener('focus',focused);
    return ()=>{active=false;window.clearInterval(timer);document.removeEventListener('visibilitychange',visible);window.removeEventListener('focus',focused);};
  },[metric]);

  useEffect(()=>{
    if(!meta?.latest_date || !valid){setData(null);setSeries(null);setLoading(false);return;}
    const controller=new AbortController();let active=true;setLoading(true);setError('');setData(null);
    getAnomalies(metric,rangeStart,effectiveEnd,controller.signal)
      .then((d:Anomalies)=>{if(active)setData(d);}).catch(e=>{if(active&&e.name!=='AbortError')setError(e.message);})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;controller.abort();};
  },[metric,rangeStart,effectiveEnd,meta?.latest_date,valid]);

  useEffect(()=>{if(!selected||!valid){setSeries(null);return;}const c=new AbortController();let active=true;setSeries(null);
    getSeries(metric,selected,rangeStart,effectiveEnd,c.signal).then(value=>{if(active)setSeries(value);}).catch(()=>{});
    return ()=>{active=false;c.abort();};
  },[metric,selected,rangeStart,effectiveEnd,valid]);

  const rows=data?.countries||[];
  const current=rows.find(r=>r.iso3===selected);
  const currentFlag=selected?countryFlagUrl(selected):null;
  const missingCountry=selected && data && !current ? countryDisplayName(selected,selected) : null;
  const matching=useMemo(()=>countryOptions.filter(c=>`${c.name} ${c.iso3}`.toLowerCase().includes(query.toLowerCase())).slice(0,8),[query]);
  const mean=rows.length?rows.reduce((sum,r)=>sum+r.anomaly,0)/rows.length:0;
  const sorted=metric==='precipitation'?rows.map(row=>row.anomaly).sort((a,b)=>a-b):[];
  const summary=metric==='precipitation'&&sorted.length
    ? (sorted[Math.floor((sorted.length-1)/2)]+sorted[Math.floor(sorted.length/2)])/2 : mean;
  const title=periodLabel(kind,rangeStart,effectiveEnd,season);
  const dataMethod=metric==='precipitation'
    ? 'Copernicus ERA5-Land 24 UTC stundu nokrišņu summu pārvērš milimetros un aprēķina platības svērtu valsts vidējo. Izvēlētā perioda kopējo daudzumu salīdzina ar 1991–2020 attiecīgo kalendāra dienu normu. Ja norma ir ļoti maza, procentuālā novirze var būt liela.'
    : meta?.mode==='demo'
    ? 'Šajā priekšskatījumā izmantoti ilustratīvi dati. Reālajā versijā Copernicus ERA5-Land diennakts temperatūru apkopo katrai valstij un salīdzina ar 1991–2020 klimatisko normu.'
    : 'Copernicus ERA5-Land diennakts temperatūru aprēķina kā platības svērtu valsts sauszemes vidējo un salīdzina ar attiecīgo kalendāra dienu 1991–2020 normu.';
  const qualityNote=meta?.mode==='demo'?'':current?.quality==='proxy'?' Šīs valsts vērtība ir reģionāla aproksimācija, nevis precīzs valsts vidējais.':current?.quality==='limited'?' Mazā režģa pārklājuma dēļ vērtība ir aptuvena.':'';
  const select=(iso:string)=>{setSelected(iso);setPanelOpen(true);setSearchOpen(false);setQuery('');};
  const changeMetric=(next:Metric)=>{setMetric(next);setData(null);setSeries(null);setError('');};

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><img className="brand-logo" src={`${import.meta.env.BASE_URL}lvgmc-logo-dark.svg`} alt="LVĢMC logotips"/></div>
      <div className="metric-switch" role="group" aria-label="Klimata rādītājs">
        <button type="button" className={metric==='temperature'?'active':''} aria-pressed={metric==='temperature'} onClick={()=>changeMetric('temperature')}><Thermometer size={16}/> Temperatūra</button>
        <button type="button" className={metric==='precipitation'?'active':''} aria-pressed={metric==='precipitation'} disabled={metaByMetric.temperature?.mode==='demo'} onClick={()=>changeMetric('precipitation')}><CloudRain size={16}/> Nokrišņi</button>
      </div>
      <div className="topbar-actions"><button className="icon-text" onClick={()=>setAbout(true)} aria-label="Par projektu"><CircleHelp size={17}/> Par projektu</button></div>
    </header>

    <main className={`workspace ${panelOpen?'':'panel-closed'}`}>
      <aside className="sidebar">
        <div className="sidebar-scroll">
          <h1>Pasaules<br/><em>klimats</em></h1>
          <p className="intro">{metric==='precipitation'?'Atklāj, kur izvēlētajā periodā nokrišņu bija vairāk vai mazāk nekā klimatiskajā normā.':'Atklāj, kur izvēlētajā periodā gaisa temperatūra atšķīrās no klimatiskās normas attiecīgajā valstī.'}</p>
          <div className="sidebar-divider"/>
          <PeriodPicker kind={kind} anchor={anchor} endInput={endInput} season={season} latestDate={meta?.latest_date}
            title={title} start={rangeStart} end={effectiveEnd} valid={valid} firstDate={meta?.first_date}
            onKind={setKind} onAnchor={setAnchor} onEnd={setEndInput} onSeason={setSeason}/>
          <div className="sidebar-divider"/>
          <div className="section-heading"><Search size={16}/><span>ATRAST VALSTI</span></div>
          <div className="search-wrap"><Search size={16}/><input placeholder="Meklēt pēc nosaukuma vai ISO..." value={query} onFocus={()=>setSearchOpen(true)} onChange={e=>{setQuery(e.target.value);setSearchOpen(true);}}/>{query&&<button aria-label="Notīrīt meklēšanu" onClick={()=>setQuery('')}><X size={15}/></button>}
            {searchOpen&&query&&<div className="search-results">{matching.length?matching.map(c=>{const r=rows.find(row=>row.iso3===c.iso3);return <button key={c.iso3} onClick={()=>select(c.iso3)}><span>{c.name}</span><strong style={{color:r?anomalyColor(r.anomaly,metric):'#9bb3bf'}}>{r?fmt(r.anomaly,metric):'Nav datu'}</strong></button>;}):<div>Valsts nav atrasta</div>}</div>}
          </div>
          <div className="sidebar-divider"/>
          <div className="section-heading"><Layers3 size={16}/><span>DATU PĀRSKATS</span></div>
          <div className="stat-card"><div><span className="stat-label">{metric==='precipitation'?'VALSTU MEDIĀNĀ NOVIRZE':'VALSTU VIDĒJĀ ANOMĀLIJA'}</span><strong className={metric==='precipitation'?(summary>=0?'wet':'dry'):(summary>=0?'warm':'cool')}>{rows.length?fmt(summary,metric):'—'}</strong></div><div className="stat-icon">{metric==='precipitation'?<CloudRain size={19}/>:<Thermometer size={19}/>}</div></div>
        </div>
      </aside>

      <section className="map-section">
        <div className="map-topline"><div><h2>{metric==='precipitation'?'Nokrišņu novirzes':'Temperatūras anomālijas'}</h2><p className="map-period">{title}{partial&&<span> · nepilns periods</span>}</p><p className="map-explainer">{metric==='precipitation'?'Kartē attēlota izvēlētā perioda nokrišņu summas procentuālā novirze no 1991–2020 normas.':'Kartē attēlotas gaisa temperatūras novirzes no 1991–2020 klimatiskās normas.'}{meta?.mode==='era5_land'&&meta.latest_date&&<> Dati pieejami līdz {displayDate(meta.latest_date)}.</>}</p></div><button className="export-button" disabled={!rows.length} onClick={()=>csvDownload(rows,rangeStart,effectiveEnd,meta?.mode||'unknown',metric)}><Download size={16}/> Lejupielādēt CSV</button></div>
        <div className="map-wrap"><ClimateMap records={rows} metric={metric} selected={selected} onSelect={select}/>
          {loading&&<div className="loading-pill">Atjauno karti…</div>}
          {error&&<div className="error-pill">{error}</div>}
          {meta?.mode==='demo'&&<div className="demo-banner"><Info size={14}/> ILUSTRATĪVI DATI — nav ERA5‑Land datu</div>}
          <div className="map-coordinate">90°N <span>·</span> 0° <span>·</span> 90°S</div>
          <div className="legend"><div className="legend-header"><strong>{metric==='precipitation'?'NOVIRZE NO NORMAS':'ANOMĀLIJA'}</strong><span>{metric==='precipitation'?'%':'°C'}</span></div><div className={`gradient ${metric==='precipitation'?'precipitation':''}`}/><div className="legend-ticks">{(metric==='precipitation'?['−100%','−50%','0%','+50%','≥+100%']:['−6°','−3°','0°','+3°','+6°']).map(tick=><span key={tick}>{tick}</span>)}</div><div className="legend-foot"><span>{metric==='precipitation'?'Mazāk nokrišņu':'Aukstāks par normu'}</span><span>{metric==='precipitation'?'Vairāk nokrišņu':'Siltāks par normu'}</span></div><div className="legend-note"><span className="no-data-swatch"/> Nav datu <span className="proxy-swatch"/> Aproksimācija *</div><div className="territory-note"><span className="territory-swatch"/> Pārējās teritorijas · bez valsts datiem</div></div>
        </div>
      </section>

      <aside className={`detail-panel ${panelOpen?'open':''}`}>
        <div className="detail-header"><span>VALSTS PROFILS</span><button onClick={()=>setPanelOpen(false)} aria-label="Aizvērt paneli"><X size={18}/></button></div>
        {current?<div className="detail-content">
          <div className="country-heading">{currentFlag&&<img className="country-flag" src={currentFlag} alt={`${current.name} karogs`}/>}<h2>{current.name}</h2></div><div className="country-period"><CalendarDays size={14}/> {title}</div><div className={`quality-line ${current.quality}`}>{current.quality==='grid'?'Režģa vidējais':current.quality==='limited'?'Ierobežots režģa pārklājums':'Reģionāla aproksimācija'}</div>
          <div className={`anomaly-hero ${metric==='precipitation'?'precipitation':''} ${current.anomaly>=0?'positive':'negative'}`}><div className="anomaly-caption">{metric==='precipitation'?'NOKRIŠŅU NOVIRZE':'TEMPERATŪRAS ANOMĀLIJA'}</div><div className="anomaly-value">{fmt(current.anomaly,metric,2)}</div><div className="anomaly-descriptor">{current.anomaly>=0?<ArrowUpRight size={17}/>:<ArrowDownRight size={17}/>} {metric==='precipitation'?(current.anomaly>=0?'Vairāk':'Mazāk'):(current.anomaly>=0?'Siltāks':'Aukstāks')} {metric==='precipitation'?'nokrišņu nekā parasti':'par klimatisko normu šajā valstī'}</div></div>
          <div className="metric-grid"><div><span>{metric==='precipitation'?'FAKTISKĀ SUMMA':'FAKTISKĀ VIDĒJĀ'}</span><strong>{amount(current.actual,metric)}</strong></div><div><span>1991–2020 NORMA</span><strong>{amount(current.normal,metric)}</strong></div></div>
          <div className="detail-section-title"><Activity size={16}/> ANOMĀLIJAS DINAMIKA</div>
          <div className="chart-wrap">{series?.points.length?<ResponsiveContainer width="100%" height={164}><AreaChart data={series.points} margin={{top:12,right:4,left:-28,bottom:0}}><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={metric==='precipitation'?'#5eb4ce':'#eb907e'} stopOpacity={.45}/><stop offset="100%" stopColor={metric==='precipitation'?'#5eb4ce':'#eb907e'} stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#25435a" strokeDasharray="3 4" vertical={false}/><XAxis dataKey="date" tick={{fill:'#8ca5b5',fontSize:10}} tickLine={false} axisLine={false} minTickGap={25}/><YAxis tick={{fill:'#8ca5b5',fontSize:10}} tickLine={false} axisLine={false} tickFormatter={v=>`${v}${metric==='precipitation'?'%':'°'}`}/><Tooltip contentStyle={{background:'#123149',border:'1px solid #345367',borderRadius:8,color:'#fff'}} formatter={(v)=>[fmt(Number(v),metric,2),'Anomālija']} labelFormatter={value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)?displayDate(value):value}/><Area type="monotone" dataKey="anomaly" name="Anomālija" stroke={metric==='precipitation'?'#65bad3':'#ed9a88'} strokeWidth={2.2} fill="url(#chartFill)"/></AreaChart></ResponsiveContainer>:<div className="chart-empty">Dati nav pieejami</div>}</div>
          <div className="chart-foot"><span>{series?.grouping==='day'?'DIENAS VĒRTĪBAS':metric==='precipitation'?'MĒNEŠU NOVIRZES':'MĒNEŠU VIDĒJĀS'}</span><span>Anomālija {metric==='precipitation'?'%':'°C'}</span></div>
          <div className="detail-section-title"><Info size={16}/> DATU IEGŪŠANA</div>
          <p className="data-method">{dataMethod}{qualityNote}{meta?.mode!=='demo'&&current.provisional?' Jaunākās vērtības var būt provizoriskas.':''}</p>
        </div>:missingCountry?<div className="detail-content"><div className="country-heading">{currentFlag&&<img className="country-flag" src={currentFlag} alt={`${missingCountry} karogs`}/>}<h2>{missingCountry}</h2></div><div className="country-period"><CalendarDays size={14}/> {title}</div><div className="no-data-panel"><strong>Nav uzticamu valsts datu</strong><p>ERA5-Land sauszemes režģis šo valsti nepārklāj pietiekami, lai aprēķinātu valsts vidējo {metric==='precipitation'?'nokrišņu daudzumu':'temperatūru'} un anomāliju. Kartē tā attēlota neitrālā krāsā.</p></div></div>:<div className="empty-detail">Izvēlies valsti kartē, lai skatītu detalizētu informāciju.</div>}
      </aside>
      {!panelOpen&&<button className="reopen-panel" onClick={()=>setPanelOpen(true)}>Valsts profils <ChevronDown size={15}/></button>}
    </main>

    {about&&<div className="modal-backdrop" onClick={()=>setAbout(false)}><div className="modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setAbout(false)}><X size={20}/></button><span className="section-kicker">PAR PROJEKTU</span><h2>Kā lasīt karti?</h2><p>Salīdzinājumā ietilpst 193 ANO dalībvalstis un 2 novērotājvalstis — Svētais Krēsls un Palestīna. Grenlande un pārējās ārpus šī saraksta esošās teritorijas ir redzamas neitrālā krāsā, bet nav klikšķināmas un netiek iekļautas valstu statistikā. Valsts poligonā ietilpstošās salas tiek iekļautas tās vidējā; Spānijai tās ir arī Kanāriju un Baleāru salas.</p>{metric==='precipitation'?<p>Izvēlētā perioda nokrišņu summa milimetros salīdzināta ar attiecīgo 1991–2020 kalendāra dienu normu. Kartē rādīta procentuālā novirze: brūnā krāsa nozīmē sausāku, zilā — mitrāku periodu. Pie ļoti mazas normas procentuālā novirze var būt liela.</p>:<p>Katrai valstij rādīta izvēlētā perioda vidējās 2 m gaisa temperatūras novirze no attiecīgo kalendāra dienu 1991–2020 normas. Zilā krāsa apzīmē aukstāku, sarkanā — siltāku periodu.</p>}{meta?.mode==='demo'?<p>Šajā priekšskatījumā izmantoti ilustratīvi ģenerēti dati. Tie nav izmantojami klimata secinājumiem.</p>:<><p>Dati iegūti no Copernicus ERA5-Land {metric==='precipitation'?'kopējiem nokrišņiem, summējot 24 UTC stundas katrai dienai':'2 m temperatūras, apkopojot 24 UTC stundu vērtības katrai dienai'} un pēc tam aprēķinot valstu platības svērtās vērtības. Klimatiskā norma aprēķināta no 1991–2020 valstu dienu vēstures.</p><p>ERA5-Land sauszemes režģis nedod pietiekamu pārklājumu septiņām salu valstīm: Kiribati, Maldīvijai, Māršala Salām, Nauru, Seišelām, Tongai un Tuvalu. Tās redzamas kartē bez anomālijas krāsas. Jaunākā saglabātā diena: {meta?.latest_date&&displayDate(meta.latest_date)}.</p></>}<button className="modal-action" onClick={()=>setAbout(false)}>Saprotu</button></div></div>}
  </div>;
}
