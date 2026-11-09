import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChevronDown, CircleHelp, Download, Info, Layers3, Search, Thermometer, X } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ClimateMap from './ClimateMap';
import { getAnomalies, getMeta, getSeries, isStaticData } from './dataClient';
import { countryDisplayName, countryFlagUrl, countryOptions } from './countryCatalog';
import PeriodPicker from './PeriodPicker';
import { anomalyColor, periodDates, periodLabel, type Anomalies, type CountryRecord, type Metadata, type PeriodKind, type Season, type Series } from './types';

const fmt = (v:number, digits=1) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)} °C`;
const temp = (v:number) => `${v.toFixed(1)} °C`;
const displayDate = (value:string) => `${value.slice(8,10)}.${value.slice(5,7)}.${value.slice(0,4)}`;

function csvDownload(rows:CountryRecord[], start:string,end:string, mode:string) {
  const header='iso3,country,un_status,start,end,actual_c,normal_c,anomaly_c,quality,provisional,data_mode';
  const lines=rows.map(r=>[r.iso3,`"${r.name.replaceAll('"','""')}"`,r.status,start,end,r.actual,r.normal,r.anomaly,r.quality,r.provisional,mode].join(','));
  const url=URL.createObjectURL(new Blob([[header,...lines].join('\n')],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`climate-anomalies-${start}-${end}.csv`;a.click();URL.revokeObjectURL(url);
}

export default function App() {
  const [meta,setMeta]=useState<Metadata|null>(null);
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
  const latestMetaDate=useRef<string|null>(null);
  const [rangeStart,rangeEnd]=periodDates(kind,anchor,endInput,season);
  const valid=Boolean(meta?.latest_date && rangeStart>= '2020-01-01' && rangeStart<=rangeEnd && rangeStart<=meta.latest_date);
  const effectiveEnd=meta?.latest_date && rangeEnd>meta.latest_date ? meta.latest_date : rangeEnd;
  const partial=valid && effectiveEnd<rangeEnd;

  useEffect(()=>{
    let active=true;
    const refresh=()=>getMeta().then((m:Metadata)=>{
      if(!active)return;
      if(isStaticData && latestMetaDate.current && m.latest_date!==latestMetaDate.current){window.location.reload();return;}
      latestMetaDate.current=m.latest_date;
      setMeta(m);
      if(!initializedMeta.current && m.latest_date){
        initializedMeta.current=true;
        const d=new Date(`${m.latest_date}T12:00:00Z`);d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-1);
        setAnchor(d.toISOString().slice(0,10));setEndInput(m.latest_date);
      }
    }).catch(()=>{if(active && !initializedMeta.current)setError('API nav sasniedzams. Palaidiet FastAPI serveri.');});
    void refresh();
    const timer=window.setInterval(()=>{void refresh();},5*60*1000);
    const visible=()=>{if(document.visibilityState==='visible')void refresh();};
    const focused=()=>{void refresh();};
    document.addEventListener('visibilitychange',visible);
    window.addEventListener('focus',focused);
    return ()=>{active=false;window.clearInterval(timer);document.removeEventListener('visibilitychange',visible);window.removeEventListener('focus',focused);};
  },[]);

  useEffect(()=>{
    if(!meta?.latest_date || !valid){setData(null);setSeries(null);return;}
    const controller=new AbortController();setLoading(true);setError('');setData(null);
    getAnomalies(rangeStart,effectiveEnd,controller.signal)
      .then((d:Anomalies)=>setData(d)).catch(e=>{if(e.name!=='AbortError')setError(e.message);})
      .finally(()=>setLoading(false));
    return ()=>controller.abort();
  },[rangeStart,effectiveEnd,meta?.latest_date,valid]);

  useEffect(()=>{if(!selected||!valid){setSeries(null);return;}const c=new AbortController();setSeries(null);
    getSeries(selected,rangeStart,effectiveEnd,c.signal).then(setSeries).catch(()=>{});
    return ()=>c.abort();
  },[selected,rangeStart,effectiveEnd,valid]);

  const rows=data?.countries||[];
  const current=rows.find(r=>r.iso3===selected);
  const currentFlag=selected?countryFlagUrl(selected):null;
  const missingCountry=selected && data && !current ? countryDisplayName(selected,selected) : null;
  const matching=useMemo(()=>countryOptions.filter(c=>`${c.name} ${c.iso3}`.toLowerCase().includes(query.toLowerCase())).slice(0,8),[query]);
  const mean=rows.length?rows.reduce((sum,r)=>sum+r.anomaly,0)/rows.length:0;
  const title=periodLabel(kind,rangeStart,effectiveEnd,season);
  const dataMethod=meta?.mode==='demo'
    ? 'Šajā priekšskatījumā izmantoti ilustratīvi dati. Reālajā versijā Copernicus ERA5-Land diennakts temperatūru apkopo katrai valstij un salīdzina ar 1991–2020 klimatisko normu.'
    : 'Copernicus ERA5-Land diennakts temperatūru aprēķina kā platības svērtu valsts sauszemes vidējo un salīdzina ar attiecīgo kalendāra dienu 1991–2020 normu.';
  const qualityNote=meta?.mode==='demo'?'':current?.quality==='proxy'?' Šīs valsts vērtība ir reģionāla aproksimācija, nevis precīzs valsts vidējais.':current?.quality==='limited'?' Mazā režģa pārklājuma dēļ vērtība ir aptuvena.':'';
  const select=(iso:string)=>{setSelected(iso);setPanelOpen(true);setSearchOpen(false);setQuery('');};

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><img className="brand-logo" src={`${import.meta.env.BASE_URL}lvgmc-logo-dark.svg`} alt="LVĢMC logotips"/></div>
      <div className="topbar-actions"><button className="icon-text" onClick={()=>setAbout(true)} aria-label="Par projektu"><CircleHelp size={17}/> Par projektu</button></div>
    </header>

    <main className={`workspace ${panelOpen?'':'panel-closed'}`}>
      <aside className="sidebar">
        <div className="sidebar-scroll">
          <h1>Pasaules<br/><em>klimats</em></h1>
          <p className="intro">Atklāj, kur izvēlētajā periodā gaisa temperatūra atšķīrās no klimatiskās normas attiecīgajā valstī.</p>
          <div className="sidebar-divider"/>
          <PeriodPicker kind={kind} anchor={anchor} endInput={endInput} season={season} latestDate={meta?.latest_date}
            title={title} start={rangeStart} end={effectiveEnd} valid={valid}
            onKind={setKind} onAnchor={setAnchor} onEnd={setEndInput} onSeason={setSeason}/>
          <div className="sidebar-divider"/>
          <div className="section-heading"><Search size={16}/><span>ATRAST VALSTI</span></div>
          <div className="search-wrap"><Search size={16}/><input placeholder="Meklēt pēc nosaukuma vai ISO..." value={query} onFocus={()=>setSearchOpen(true)} onChange={e=>{setQuery(e.target.value);setSearchOpen(true);}}/>{query&&<button aria-label="Notīrīt meklēšanu" onClick={()=>setQuery('')}><X size={15}/></button>}
            {searchOpen&&query&&<div className="search-results">{matching.length?matching.map(c=>{const r=rows.find(row=>row.iso3===c.iso3);return <button key={c.iso3} onClick={()=>select(c.iso3)}><span>{c.name}</span><strong style={{color:r?anomalyColor(r.anomaly):'#9bb3bf'}}>{r?fmt(r.anomaly):'Nav datu'}</strong></button>;}):<div>Valsts nav atrasta</div>}</div>}
          </div>
          <div className="sidebar-divider"/>
          <div className="section-heading"><Layers3 size={16}/><span>DATU PĀRSKATS</span></div>
          <div className="stat-card"><div><span className="stat-label">VALSTU VIDĒJĀ ANOMĀLIJA</span><strong className={mean>=0?'warm':'cool'}>{rows.length?fmt(mean):'—'}</strong></div><div className="stat-icon"><Thermometer size={19}/></div></div>
        </div>
      </aside>

      <section className="map-section">
        <div className="map-topline"><div><h2>Temperatūras anomālijas</h2><p className="map-period">{title}{partial&&<span> · nepilns periods</span>}</p><p className="map-explainer">Kartē attēlotas gaisa temperatūras novirzes no 1991–2020 klimatiskās normas.{meta?.mode==='era5_land'&&meta.latest_date&&<> Dati pieejami līdz {displayDate(meta.latest_date)}.</>}</p></div><button className="export-button" disabled={!rows.length} onClick={()=>csvDownload(rows,rangeStart,effectiveEnd,meta?.mode||'unknown')}><Download size={16}/> Lejupielādēt CSV</button></div>
        <div className="map-wrap"><ClimateMap records={rows} selected={selected} onSelect={select}/>
          {loading&&<div className="loading-pill">Atjauno karti…</div>}
          {error&&<div className="error-pill">{error}</div>}
          {meta?.mode==='demo'&&<div className="demo-banner"><Info size={14}/> ILUSTRATĪVI DATI — nav ERA5‑Land datu</div>}
          <div className="map-coordinate">90°N <span>·</span> 0° <span>·</span> 90°S</div>
          <div className="legend"><div className="legend-header"><strong>ANOMĀLIJA</strong><span>°C</span></div><div className="gradient"/><div className="legend-ticks"><span>−6°</span><span>−3°</span><span>0°</span><span>+3°</span><span>+6°</span></div><div className="legend-foot"><span>Aukstāks par normu</span><span>Siltāks par normu</span></div><div className="legend-note"><span className="no-data-swatch"/> Nav datu <span className="proxy-swatch"/> Aproksimācija *</div><div className="territory-note"><span className="territory-swatch"/> Pārējās teritorijas · bez valsts datiem</div></div>
        </div>
      </section>

      <aside className={`detail-panel ${panelOpen?'open':''}`}>
        <div className="detail-header"><span>VALSTS PROFILS</span><button onClick={()=>setPanelOpen(false)} aria-label="Aizvērt paneli"><X size={18}/></button></div>
        {current?<div className="detail-content">
          <div className="country-heading">{currentFlag&&<img className="country-flag" src={currentFlag} alt={`${current.name} karogs`}/>}<h2>{current.name}</h2></div><div className="country-period"><CalendarDays size={14}/> {title}</div><div className={`quality-line ${current.quality}`}>{current.quality==='grid'?'Režģa vidējais':current.quality==='limited'?'Ierobežots režģa pārklājums':'Reģionāla aproksimācija'}</div>
          <div className={`anomaly-hero ${current.anomaly>=0?'positive':'negative'}`}><div className="anomaly-caption">TEMPERATŪRAS ANOMĀLIJA</div><div className="anomaly-value">{fmt(current.anomaly,2)}</div><div className="anomaly-descriptor">{current.anomaly>=0?<ArrowUpRight size={17}/>:<ArrowDownRight size={17}/>} {current.anomaly>=0?'Siltāks':'Aukstāks'} par klimatisko normu šajā valstī</div></div>
          <div className="metric-grid"><div><span>FAKTISKĀ VIDĒJĀ</span><strong>{temp(current.actual)}</strong></div><div><span>1991–2020 NORMA</span><strong>{temp(current.normal)}</strong></div></div>
          <div className="detail-section-title"><Activity size={16}/> ANOMĀLIJAS DINAMIKA</div>
          <div className="chart-wrap">{series?.points.length?<ResponsiveContainer width="100%" height={164}><AreaChart data={series.points} margin={{top:12,right:4,left:-28,bottom:0}}><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#eb907e" stopOpacity={.45}/><stop offset="100%" stopColor="#eb907e" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#25435a" strokeDasharray="3 4" vertical={false}/><XAxis dataKey="date" tick={{fill:'#8ca5b5',fontSize:10}} tickLine={false} axisLine={false} minTickGap={25}/><YAxis tick={{fill:'#8ca5b5',fontSize:10}} tickLine={false} axisLine={false} tickFormatter={v=>`${v}°`}/><Tooltip contentStyle={{background:'#123149',border:'1px solid #345367',borderRadius:8,color:'#fff'}} formatter={(v)=>[`${Number(v).toFixed(2)} °C`,'Anomālija']} labelFormatter={value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)?displayDate(value):value}/><Area type="monotone" dataKey="anomaly" name="Anomālija" stroke="#ed9a88" strokeWidth={2.2} fill="url(#chartFill)"/></AreaChart></ResponsiveContainer>:<div className="chart-empty">Dati nav pieejami</div>}</div>
          <div className="chart-foot"><span>{series?.grouping==='day'?'DIENAS VĒRTĪBAS':'MĒNEŠU VIDĒJĀS'}</span><span>Anomālija °C</span></div>
          <div className="detail-section-title"><Info size={16}/> DATU IEGŪŠANA</div>
          <p className="data-method">{dataMethod}{qualityNote}{meta?.mode!=='demo'&&current.provisional?' Jaunākās vērtības var būt provizoriskas.':''}</p>
        </div>:missingCountry?<div className="detail-content"><div className="country-heading">{currentFlag&&<img className="country-flag" src={currentFlag} alt={`${missingCountry} karogs`}/>}<h2>{missingCountry}</h2></div><div className="country-period"><CalendarDays size={14}/> {title}</div><div className="no-data-panel"><strong>Nav uzticamu valsts datu</strong><p>ERA5-Land sauszemes režģis šo valsti nepārklāj pietiekami, lai aprēķinātu valsts vidējo temperatūru un anomāliju. Kartē tā attēlota neitrālā krāsā.</p></div></div>:<div className="empty-detail">Izvēlies valsti kartē, lai skatītu detalizētu informāciju.</div>}
      </aside>
      {!panelOpen&&<button className="reopen-panel" onClick={()=>setPanelOpen(true)}>Valsts profils <ChevronDown size={15}/></button>}
    </main>

    {about&&<div className="modal-backdrop" onClick={()=>setAbout(false)}><div className="modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setAbout(false)}><X size={20}/></button><span className="section-kicker">PAR PROJEKTU</span><h2>Kā lasīt karti?</h2><p>Temperatūras salīdzinājumā ietilpst 193 ANO dalībvalstis un 2 novērotājvalstis — Svētais Krēsls un Palestīna. Grenlande un pārējās ārpus šī saraksta esošās teritorijas ir redzamas neitrālā krāsā, bet nav klikšķināmas un netiek iekļautas valstu statistikā. Valsts poligonā ietilpstošās salas tiek iekļautas tās vidējā; Spānijai tās ir arī Kanāriju un Baleāru salas.</p><p>Katrai valstij rādīta izvēlētā perioda vidējās 2 m gaisa temperatūras novirze no attiecīgo kalendāra dienu 1991–2020 normas. Zilā krāsa apzīmē aukstāku, sarkanā — siltāku periodu.</p>{meta?.mode==='demo'?<p>Šajā priekšskatījumā izmantoti ilustratīvi ģenerēti dati. Tie nav izmantojami klimata secinājumiem.</p>:<><p>Dati iegūti no Copernicus ERA5-Land 2 m temperatūras, apkopojot 24 UTC stundu vērtības katrai dienai un pēc tam katrai valstij. Klimatiskā norma aprēķināta no 1991–2020 valstu dienu vēstures.</p><p>ERA5-Land sauszemes režģis nedod pietiekamu pārklājumu septiņām salu valstīm: Kiribati, Maldīvijai, Māršala Salām, Nauru, Seišelām, Tongai un Tuvalu. Tās redzamas kartē bez anomālijas krāsas. Jaunākā saglabātā diena: {meta?.latest_date&&displayDate(meta.latest_date)}.</p></>}<button className="modal-action" onClick={()=>setAbout(false)}>Saprotu</button></div></div>}
  </div>;
}
