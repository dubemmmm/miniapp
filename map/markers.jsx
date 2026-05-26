/* Map markers — HTML strings consumed by L.divIcon, plus dataset */

const clusterHTML = (count, tone="ink") => {
  const size = 36 + Math.min(count, 30) * 0.9;
  const bg = tone === "coral" ? "#FF4D5D" : "#0B1024";
  return `
    <div style="
      width:${size}px; height:${size}px; border-radius:50%;
      background:${bg}; color:white;
      display:flex; align-items:center; justify-content:center;
      font-family: 'Instrument Serif', 'Cormorant Garamond', serif;
      font-size:${size > 56 ? 22 : 18}px; font-weight:400;
      border:2px solid white;
      box-shadow:0 8px 18px -4px rgba(11,16,36,0.35), 0 0 0 6px rgba(255,255,255,0.45);
      transform: translate(-50%, -50%);
    ">${count}</div>`;
};

const thumbHTML = (img, active=false) => `
  <div style="transform: translate(-50%, -100%); pointer-events:auto;">
    <div style="
      width:${active ? 64 : 52}px; height:${active ? 64 : 52}px; border-radius:50%;
      border:${active ? '3px solid #FF4D5D' : '3px solid white'};
      box-shadow:0 10px 22px -6px rgba(11,16,36,0.45);
      background:url(${img}) center/cover, #E2E5EE;
    "></div>
    <div style="
      width:0; height:0; margin:0 auto; margin-top:-2px;
      border-left:7px solid transparent; border-right:7px solid transparent;
      border-top:${active ? '9px solid #FF4D5D' : '9px solid white'};
      filter: drop-shadow(0 4px 4px rgba(11,16,36,0.25));
    "></div>
  </div>`;

const priceHTML = (price) => `
  <div style="
    transform: translate(-50%, -100%);
    background:white; color:#0B1024;
    padding:6px 10px; border-radius:999px;
    font-family: 'Geist Mono', ui-monospace, monospace; font-size:11px; font-weight:600;
    border:1px solid #E2E5EE;
    box-shadow:0 6px 14px -4px rgba(11,16,36,0.25);
    white-space:nowrap;
  ">${price}</div>`;

/* Marker dataset — anchored to real Lagos lat/lng */
const buildMarkers = () => {
  const FEATURED = PROPERTIES.find(p => p.id === "marina-crown");
  return [
    {type:'cluster', count:5,  tone:'ink',   lat:6.4527, lng:3.4080},
    {type:'cluster', count:12, tone:'ink',   lat:6.4580, lng:3.4180},
    {type:'cluster', count:18, tone:'coral', lat:6.4500, lng:3.4434},
    {type:'cluster', count:9,  tone:'coral', lat:6.4281, lng:3.4219},
    {type:'cluster', count:6,  tone:'ink',   lat:6.4474, lng:3.4731},
    {type:'cluster', count:3,  tone:'ink',   lat:6.4474, lng:3.5400},
    {type:'cluster', count:2,  tone:'ink',   lat:6.4474, lng:3.5900},
    {type:'thumb',   active:true, img: FEATURED.img, lat:6.4570, lng:3.4380},
    {type:'thumb',   img: PROPERTIES.find(p=>p.id==="oak-place").img, lat:6.4470, lng:3.4350},
    {type:'thumb',   img: PROPERTIES.find(p=>p.id==="verde").img,     lat:6.4450, lng:3.4900},
    {type:'price',   text:'₦780M',  lat:6.4474, lng:3.5500},
    {type:'price',   text:'₦1.35B', lat:6.4520, lng:3.4250},
  ];
};

Object.assign(window, { clusterHTML, thumbHTML, priceHTML, buildMarkers });
