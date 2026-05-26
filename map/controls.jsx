/* Right-side controls + bottom legend + selected-property floating card */

const ctrlBtnStyle = {
  display:'inline-flex', alignItems:'center', gap:8, padding:'9px 12px',
  background:'transparent', border:'none', borderRadius:'var(--r-md)',
  fontFamily:'var(--font-sans)', fontSize:12.5, color:'var(--ink)', cursor:'pointer',
  width:'100%', textAlign:'left'
};
const zoomBtnStyle = {
  width:38, height:38, background:'transparent', border:'none', cursor:'pointer',
  fontSize:18, fontWeight:300, color:'var(--ink)', fontFamily:'var(--font-display)'
};

const RightControls = ({mapRef}) => (
  <div style={{position:'absolute', top:24, right:24, display:'flex', flexDirection:'column', gap:10, alignItems:'flex-end', zIndex:600}}>
    <div style={{
      display:'flex', background:'rgba(250,248,242,0.92)', backdropFilter:'blur(20px)',
      border:'1px solid rgba(11,16,36,0.06)', borderRadius:'var(--r-full)',
      padding:4, boxShadow:'var(--shadow-md)'
    }}>
      <button style={{
        display:'inline-flex', alignItems:'center', gap:6, padding:'8px 14px',
        background:'var(--ink)', color:'white', border:'none', borderRadius:'var(--r-full)',
        fontFamily:'var(--font-sans)', fontSize:12.5, fontWeight:500, cursor:'pointer'
      }}><Icon.Map size={13}/> Map</button>
      <button style={{
        display:'inline-flex', alignItems:'center', gap:6, padding:'8px 14px',
        background:'transparent', color:'var(--ink)', border:'none', borderRadius:'var(--r-full)',
        fontFamily:'var(--font-sans)', fontSize:12.5, fontWeight:500, cursor:'pointer'
      }}><Icon.Grid size={13}/> Grid</button>
    </div>

    <div style={{
      display:'flex', flexDirection:'column', gap:6,
      background:'rgba(250,248,242,0.92)', backdropFilter:'blur(20px)',
      border:'1px solid rgba(11,16,36,0.06)', borderRadius:'var(--r-lg)',
      padding:6, boxShadow:'var(--shadow-md)', minWidth:148
    }}>
      <button style={ctrlBtnStyle}><Icon.Filter size={14}/> Filters <span style={{marginLeft:'auto', fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--slate-500)'}}>3</span></button>
      <button style={ctrlBtnStyle}><Icon.Sparkle size={12}/> Currency <span style={{marginLeft:'auto', fontFamily:'var(--font-mono)', fontSize:10.5, color:'var(--coral)', fontWeight:600}}>NGN</span></button>
      <div style={{height:1, background:'rgba(11,16,36,0.06)', margin:'2px 4px'}}/>
      <button style={ctrlBtnStyle} onClick={() => mapRef.current?.setView([6.4480, 3.4600], 13)}>Reset view</button>
    </div>

    <div style={{
      display:'flex', flexDirection:'column',
      background:'rgba(250,248,242,0.92)', backdropFilter:'blur(20px)',
      border:'1px solid rgba(11,16,36,0.06)', borderRadius:'var(--r-md)',
      boxShadow:'var(--shadow-md)', overflow:'hidden'
    }}>
      <button style={{...zoomBtnStyle, borderBottom:'1px solid rgba(11,16,36,0.06)'}} onClick={() => mapRef.current?.zoomIn()}>+</button>
      <button style={zoomBtnStyle} onClick={() => mapRef.current?.zoomOut()}>−</button>
    </div>
  </div>
);

const Legend = () => (
  <div style={{
    position:'absolute', left:388, bottom:24, zIndex:600,
    background:'rgba(250,248,242,0.92)', backdropFilter:'blur(20px)',
    border:'1px solid rgba(11,16,36,0.06)', borderRadius:'var(--r-md)',
    padding:'10px 14px', display:'flex', gap:18, alignItems:'center',
    boxShadow:'var(--shadow-md)'
  }}>
    <div style={{display:'flex', alignItems:'center', gap:8}}>
      <div style={{width:14, height:14, borderRadius:'50%', background:'var(--ink)', border:'2px solid white', boxShadow:'0 2px 4px rgba(11,16,36,0.25)'}}/>
      <span style={{fontSize:11.5, color:'var(--slate-600)'}}>Cluster</span>
    </div>
    <div style={{display:'flex', alignItems:'center', gap:8}}>
      <div style={{width:14, height:14, borderRadius:'50%', background:'var(--coral)', border:'2px solid white', boxShadow:'0 2px 4px rgba(11,16,36,0.25)'}}/>
      <span style={{fontSize:11.5, color:'var(--slate-600)'}}>Featured</span>
    </div>
    <div style={{width:1, height:18, background:'rgba(11,16,36,0.1)'}}/>
    <span className="eyebrow" style={{fontSize:9.5}}>© CartoDB · OSM</span>
  </div>
);

const SelectedCard = ({offsetX=0, offsetY=0}) => {
  const p = PROPERTIES.find(x => x.id === "marina-crown");
  return (
    <div style={{
      position:'absolute', left:offsetX, top:offsetY, width:260,
      transform:'translate(20px, -200px)',
      background:'white', borderRadius:'var(--r-lg)',
      boxShadow:'var(--shadow-lg)', overflow:'hidden',
      border:'1px solid rgba(11,16,36,0.06)', zIndex:550, pointerEvents:'auto'
    }}>
      <div style={{height:140, background:`url(${p.img}) center/cover, var(--slate-200)`, position:'relative'}}>
        <div style={{position:'absolute', top:10, left:10}}>
          <span className="status new"><span className="dot"/>{p.badge}</span>
        </div>
        <button style={{
          position:'absolute', top:10, right:10, width:30, height:30, borderRadius:'50%',
          border:'none', background:'rgba(255,255,255,0.95)', cursor:'pointer',
          display:'flex', alignItems:'center', justifyContent:'center'
        }}><Icon.Heart size={14}/></button>
      </div>
      <div style={{padding:'12px 14px 14px'}}>
        <div className="eyebrow" style={{fontSize:10, marginBottom:2}}>{p.location}</div>
        <div className="serif-display" style={{fontSize:22, marginBottom:6}}>
          {p.name.split(' ')[0]} <span className="italic-accent">{p.name.split(' ').slice(1).join(' ')}</span>
        </div>
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:8}}>
          <div style={{fontSize:14, fontWeight:600, fontVariantNumeric:'tabular-nums'}}>{p.price}</div>
          <div style={{fontSize:11.5, color:'var(--slate-500)'}}>{p.beds} bd · {p.baths} ba</div>
        </div>
        <button className="btn" style={{background:'var(--ink)', color:'white', width:'100%', justifyContent:'center', padding:'9px', fontSize:13}}>
          View property <Icon.ArrowRight size={13}/>
        </button>
      </div>
    </div>
  );
};

Object.assign(window, { RightControls, Legend, SelectedCard });
