import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { Map, MapGeoJSONFeature } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Feature, LineString } from 'geojson';
import type { CountryRecord } from './types';
import { anomalyColor } from './types';
import { countryDisplayName } from './countryCatalog';

maplibregl.setWorkerUrl(workerUrl);

const MICRO = [
  { iso3:'MCO', coords:[7.42,43.74] }, { iso3:'VAT', coords:[12.45,41.90] },
  { iso3:'SMR', coords:[12.46,43.94] }, { iso3:'LIE', coords:[9.55,47.14] },
  { iso3:'MLT', coords:[14.38,35.94] }, { iso3:'SGP', coords:[103.82,1.35] },
  { iso3:'KIR', coords:[173.10,1.36] }, { iso3:'MDV', coords:[73.41,3.26] },
  { iso3:'MHL', coords:[171.65,7.01] }, { iso3:'NRU', coords:[166.93,-0.52] },
  { iso3:'SYC', coords:[55.49,-4.67] }, { iso3:'TON', coords:[-175.25,-21.17] },
  { iso3:'TUV', coords:[179.21,-8.50] }
] as const;
const NO_DATA = new Set(['KIR','MDV','MHL','NRU','SYC','TON','TUV']);

export default function ClimateMap({ records, selected, onSelect }: { records: CountryRecord[]; selected: string | null; onSelect: (iso: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const hovered = useRef<string | null>(null);
  const recordsRef = useRef(records);
  const selectRef = useRef(onSelect);
  recordsRef.current = records; selectRef.current = onSelect;

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({ container: container.current, style: {
      version: 8, sources: {}, layers: [{ id:'background', type:'background', paint:{'background-color':'#08283f'} }]
    }, center:[0,15], zoom:1, minZoom:-.5, maxZoom:7, attributionControl:false, renderWorldCopies:false });
    mapRef.current = map;
    map.on('error', e => console.error('MapLibre:', e.error));
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    map.addControl(new maplibregl.NavigationControl({ showCompass:false }), 'bottom-right');
    for (const [selector, label] of [
      ['.maplibregl-ctrl-zoom-in', 'Pietuvināt karti'],
      ['.maplibregl-ctrl-zoom-out', 'Attālināt karti'],
    ]) {
      const button = container.current.querySelector<HTMLButtonElement>(selector);
      button?.setAttribute('aria-label', label);
      button?.setAttribute('title', label);
    }
    map.on('load', () => {
      map.fitBounds([[-180,-65],[180,85]], {padding:20,duration:0});
      const lines: Feature<LineString>[] = [];
      for (let lat=-60;lat<=80;lat+=20) lines.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:Array.from({length:73},(_,i)=>[-180+i*5,lat])}});
      for (let lon=-180;lon<=180;lon+=30) lines.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:Array.from({length:35},(_,i)=>[lon,-85+i*5])}});
      map.addSource('graticule',{type:'geojson',data:{type:'FeatureCollection',features:lines}});
      map.addLayer({id:'graticule',type:'line',source:'graticule',paint:{'line-color':'#527087','line-opacity':.19,'line-width':1}});
      map.addSource('territories',{type:'geojson',data:`${import.meta.env.BASE_URL}territories.geojson`});
      map.addLayer({id:'territory-fill',type:'fill',source:'territories',paint:{'fill-color':'#334e60','fill-opacity':.88}});
      map.addLayer({id:'territory-outline',type:'line',source:'territories',paint:{'line-color':'#a6bdc7','line-opacity':.42,'line-width':['interpolate',['linear'],['zoom'],1,.45,5,1.1]}});
      map.addSource('countries',{type:'geojson',data:`${import.meta.env.BASE_URL}countries.geojson`,promoteId:'iso3'});
      map.addLayer({id:'country-fill',type:'fill',source:'countries',paint:{
        'fill-color':['coalesce',['feature-state','color'],'#425e70'],
        'fill-opacity':['case',['boolean',['feature-state','hover'],false],.98,.89]
      }});
      map.addLayer({id:'country-outline',type:'line',source:'countries',paint:{'line-color':'#d8e9ee','line-opacity':.45,'line-width':['interpolate',['linear'],['zoom'],1,.45,5,1.2]}});
      map.addLayer({id:'selected-outline',type:'line',source:'countries',paint:{'line-color':'#fff8dd','line-width':2.6,'line-opacity':.95},filter:['==',['get','iso3'],'']});
      map.addSource('micro',{type:'geojson',data:{type:'FeatureCollection',features:MICRO.map(m=>({type:'Feature' as const,properties:{iso3:m.iso3,noData:NO_DATA.has(m.iso3)},geometry:{type:'Point' as const,coordinates:[...m.coords]}}))}});
      map.addLayer({id:'micro-halo',type:'circle',source:'micro',paint:{'circle-radius':7,'circle-color':['case',['get','noData'],'#40596a','#092e46'],'circle-stroke-color':['case',['get','noData'],'#a8b8c1','#deeced'],'circle-stroke-width':1.5,'circle-opacity':.9}});
      map.addLayer({id:'micro-dot',type:'circle',source:'micro',paint:{'circle-radius':2.7,'circle-color':['case',['get','noData'],'#9cabb5','#f8e6ca']}});
      const update = () => recordsRef.current.forEach(r => map.setFeatureState({source:'countries',id:r.iso3},{color:anomalyColor(r.anomaly)}));
      map.on('sourcedata', e=>{ if(e.sourceId==='countries' && e.isSourceLoaded) update(); });
      update();
      const show = (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0] as MapGeoJSONFeature | undefined;
        if (!f) return;
        const iso = String(f.properties?.iso3 || f.id || '');
        if (hovered.current && hovered.current !== iso) map.setFeatureState({source:'countries',id:hovered.current},{hover:false});
        hovered.current=iso; map.setFeatureState({source:'countries',id:iso},{hover:true});
        const row=recordsRef.current.find(r=>r.iso3===iso);
        map.getCanvas().style.cursor='pointer';
        popupRef.current?.remove();
        const safeName=document.createElement('div'); safeName.className='map-tooltip';
        const title=document.createElement('strong');title.textContent=row?.name || countryDisplayName(iso, String(f.properties?.name || iso));
        const value=document.createElement('span');value.textContent=row ? `${row.anomaly>=0?'+':''}${row.anomaly.toFixed(2)} °C ${row.quality==='proxy'?' · aproksimācija':''}` : 'Nav datu';
        safeName.append(title,value);
        popupRef.current=new maplibregl.Popup({closeButton:false,offset:15,className:'climate-popup'}).setLngLat(e.lngLat).setDOMContent(safeName).addTo(map);
      };
      map.on('mousemove','country-fill',show);
      map.on('mousemove','micro-halo',show);
      const leave = () => {if(hovered.current) map.setFeatureState({source:'countries',id:hovered.current},{hover:false}); hovered.current=null;map.getCanvas().style.cursor='';popupRef.current?.remove();};
      map.on('mouseleave','country-fill',leave);
      map.on('mouseleave','micro-halo',leave);
      map.on('click','country-fill',e=>{const iso=e.features?.[0]?.properties?.iso3;if(iso)selectRef.current(String(iso));});
      map.on('click','micro-halo',e=>{const iso=e.features?.[0]?.properties?.iso3;if(iso)selectRef.current(String(iso));});
      map.on('mouseenter','micro-halo',()=>{map.getCanvas().style.cursor='pointer';});
      map.on('mouseleave','micro-halo',()=>{map.getCanvas().style.cursor='';});
    });
    return ()=>{observer.disconnect();popupRef.current?.remove();map.remove();mapRef.current=null;};
  },[]);

  useEffect(()=>{const map=mapRef.current;if(!map?.isStyleLoaded())return;records.forEach(r=>map.setFeatureState({source:'countries',id:r.iso3},{color:anomalyColor(r.anomaly)}));},[records]);
  useEffect(()=>{const map=mapRef.current;if(map?.getLayer('selected-outline'))map.setFilter('selected-outline',['==',['get','iso3'],selected||'']);},[selected]);
  return <div ref={container} className="map-canvas" aria-label="Interaktīva pasaules temperatūras anomāliju karte"/>;
}
