/* Floating left rail — search, district chips, scrollable property list */

const LeftRail = () => {
  const districts = [
    {name:"Ikoyi", count:78, active:true},
    {name:"Lekki", count:62},
    {name:"Victoria Island", count:24},
    {name:"Banana Island", count:9},
    {name:"Ajah", count:5},
  ];
  const list = PROPERTIES.filter(p => p.area === "Ikoyi").slice(0, 4);

  return (
    <div style={{
      position:'absolute', top:24, left:24, bottom:24, width:340,
      background:'rgba(250,248,242,0.92)', backdropFilter:'blur(20px)',
      border:'1px solid rgba(11,16,36,0.06)', borderRadius:'var(--r-xl)',
      boxShadow:'var(--shadow-lg)',
      display:'flex', flexDirection:'column', overflow:'hidden', zIndex:600
    }}>
      {/* Search */}
      <div style={{padding:'18px 20px 12px'}}>
        <div className="eyebrow coral" style={{marginBottom:10}}>● Map view · Lagos</div>
        <div style={{
          display:'flex', alignItems:'center', gap:10,
          background:'white', border:'1px solid var(--slate-200)',
          borderRadius:'var(--r-full)', padding:'10px 16px'
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--slate-500)" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
          </svg>
          <input placeholder="Search address, district, name…"
                 style={{border:'none', outline:'none', flex:1, fontSize:13.5, background:'transparent', color:'var(--ink)', fontFamily:'var(--font-sans)'}}/>
          <span className="kbd">⌘K</span>
        </div>
      </div>

      {/* District filters */}
      <div style={{padding:'4px 20px 16px', borderBottom:'1px solid rgba(11,16,36,0.06)'}}>
        <div className="eyebrow" style={{fontSize:10, marginBottom:10}}>Districts</div>
        <div style={{display:'flex', flexWrap:'wrap', gap:6}}>
          {districts.map(d => (
            <span key={d.name} className={`chip ${d.active ? 'active' : ''}`} style={{fontSize:12, padding:'5px 11px'}}>
              {d.name} <span style={{opacity:0.6, fontFamily:'var(--font-mono)', fontSize:10, marginLeft:4}}>{d.count}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Property count */}
      <div style={{padding:'16px 20px 10px', display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
        <div>
          <div className="serif-display" style={{fontSize:30, lineHeight:1}}>
            178 <span className="italic-accent" style={{color:'var(--slate-500)', fontSize:18}}>properties</span>
          </div>
          <div className="eyebrow" style={{fontSize:10, marginTop:4}}>in view · Ikoyi focus</div>
        </div>
        <span className="chip" style={{fontSize:11.5}}>Sort <Icon.Chevron size={11}/></span>
      </div>

      {/* List */}
      <div style={{flex:1, overflow:'auto', padding:'8px 12px 18px'}} className="no-scroll">
        {list.map((p, i) => (
          <div key={p.id}
               style={{
                 display:'flex', gap:12, padding:'10px',
                 borderRadius:'var(--r-md)',
                 background: i===0 ? 'white' : 'transparent',
                 border: i===0 ? '1px solid rgba(255,77,93,0.25)' : '1px solid transparent',
                 boxShadow: i===0 ? '0 6px 18px -8px rgba(11,16,36,0.18)' : 'none',
                 marginBottom:6, cursor:'pointer', position:'relative'
               }}>
            {i===0 && <div style={{position:'absolute', left:0, top:14, bottom:14, width:3, background:'var(--coral)', borderRadius:2}}/>}
            <div style={{
              width:72, height:72, borderRadius:'var(--r-md)', flexShrink:0,
              background:`url(${p.img}) center/cover, var(--slate-200)`
            }}/>
            <div style={{flex:1, minWidth:0}}>
              <div className="eyebrow" style={{fontSize:9.5, marginBottom:2}}>{p.location}</div>
              <div className="serif-display" style={{fontSize:18, marginBottom:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis'}}>
                {p.name}
              </div>
              <div style={{fontSize:12, color:'var(--slate-600)', display:'flex', gap:8, marginBottom:4}}>
                <span>{p.beds} bd</span><span>·</span><span>{p.baths} ba</span>
              </div>
              <div style={{fontSize:12.5, fontWeight:600, fontVariantNumeric:'tabular-nums', color: i===0 ? 'var(--coral)' : 'var(--ink)'}}>
                {p.price}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

Object.assign(window, { LeftRail });
