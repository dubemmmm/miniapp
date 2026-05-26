/* ChromeHeader — shared top nav for editorial screens */
const ChromeHeader = ({title="CW REAL ESTATE", initials="AD", active="Map view"}) => (
  <header style={{
    display:'flex', alignItems:'center', justifyContent:'space-between',
    padding:'24px 40px 0', position:'relative', zIndex:700
  }}>
    <div style={{display:'flex', alignItems:'center', gap:10}}>
      <div style={{
        width:36, height:36, borderRadius:10,
        background:'linear-gradient(135deg, var(--coral) 0%, var(--coral-700) 100%)',
        display:'flex', alignItems:'center', justifyContent:'center',
        color:'white', fontWeight:700, fontSize:16,
        fontFamily:'var(--font-display)', fontStyle:'italic',
        boxShadow:'var(--shadow-coral)'
      }}>cw</div>
      <div className="eyebrow ink" style={{letterSpacing:'0.25em', fontSize:11.5}}>{title}</div>
    </div>
    <nav style={{display:'flex', alignItems:'center', gap:6, fontSize:13.5, color:'var(--slate-600)'}}>
      {["Portfolio","Map view","Saved","Concierge"].map(item => (
        <a key={item} style={{
          color: item === active ? 'var(--ink)' : 'var(--slate-600)',
          fontWeight: item === active ? 500 : 400,
          padding:'8px 14px'
        }}>{item}</a>
      ))}
    </nav>
    <div style={{display:'flex', alignItems:'center', gap:10}}>
      <button style={{
        width:38, height:38, borderRadius:'50%', border:'1px solid var(--slate-200)',
        background:'rgba(255,255,255,0.7)', cursor:'pointer',
        display:'inline-flex', alignItems:'center', justifyContent:'center'
      }}>
        <Icon.Heart size={15}/>
      </button>
      <div style={{
        width:40, height:40, borderRadius:'50%', background:'var(--coral)', color:'white',
        display:'inline-flex', alignItems:'center', justifyContent:'center',
        fontWeight:600, fontSize:13, letterSpacing:'0.05em',
        boxShadow:'var(--shadow-coral)'
      }}>{initials}</div>
    </div>
  </header>
);

Object.assign(window, { ChromeHeader });
