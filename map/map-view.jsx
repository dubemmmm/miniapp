/* Main MapView — mounts Leaflet, places markers, tracks selected card position */

const MapView = () => {
  const containerRef = React.useRef(null);
  const mapRef = React.useRef(null);
  const [selPx, setSelPx] = React.useState({x: 700, y: 320});

  React.useEffect(() => {
    if (!containerRef.current || mapRef.current || !window.L) return;

    const map = L.map(containerRef.current, {
      center: [6.4480, 3.4600],
      zoom: 13,
      zoomControl: false,
      attributionControl: false,
      zoomSnap: 0.25,
    });
    mapRef.current = map;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 19,
    }).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 19, opacity: 0.8,
    }).addTo(map);

    buildMarkers().forEach(m => {
      let html;
      if (m.type === 'cluster') html = clusterHTML(m.count, m.tone);
      else if (m.type === 'thumb') html = thumbHTML(m.img, m.active);
      else if (m.type === 'price') html = priceHTML(m.text);
      const icon = L.divIcon({ html, className: 'cw-marker', iconSize: [0, 0], iconAnchor: [0, 0] });
      L.marker([m.lat, m.lng], { icon }).addTo(map);
    });

    const updateSelected = () => {
      const pt = map.latLngToContainerPoint([6.4570, 3.4380]);
      setSelPx({ x: pt.x, y: pt.y });
    };
    updateSelected();
    map.on('move zoom', updateSelected);

    return () => { map.off('move zoom', updateSelected); map.remove(); mapRef.current = null; };
  }, []);

  return (
    <div style={{
      width:'100%', height:'100%', overflow:'hidden',
      background:'var(--bg-gradient)', position:'relative',
      fontFamily:'var(--font-sans)', color:'var(--ink)'
    }}>
      <ChromeHeader active="Map view"/>

      <div className="cw-map" style={{position:'absolute', left:0, right:0, top:84, bottom:0, overflow:'hidden'}}>
        <div ref={containerRef} style={{position:'absolute', inset:0}}/>
        <SelectedCard offsetX={selPx.x} offsetY={selPx.y}/>
        <LeftRail/>
        <RightControls mapRef={mapRef}/>
        <Legend/>
      </div>
    </div>
  );
};

Object.assign(window, { MapView });
