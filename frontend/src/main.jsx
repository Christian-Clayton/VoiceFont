import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api} from './api';
import Calibration from './Calibration';
import Speech from './Speech';
import Experiments from './Experiments';
import './styles.css';

function App() {
  const [view, setView] = useState('calibrate');
  const [message, updateMessage] = useState('');
  const [error, setError] = useState(false);
  const setMessage = (text, failed = false) => {updateMessage(text);setError(failed);};
  const [profiles, setProfiles] = useState([]);
  const [voice, setVoice] = useState('');
  const [locked, setLocked] = useState(false);
  const refresh = () => api('/profiles').then(setProfiles).catch(e => setMessage(e.message));
  useEffect(() => {refresh();}, []);
  function navigate(next) {
    if (locked) {setMessage('Save the unsaved take, or stop and discard it before changing views.'); return;}
    setView(next); refresh();
  }
  return <><a className="skip-link" href="#main">Skip to workspace</a>
    <header className="topbar"><a className="brand" href="/calibrate"><span className="brand-mark">vf</span>VoiceFont<span className="local-badge">LOCAL</span></a>
      <nav aria-label="Workspace">{[['calibrate','Calibrate'],['library','Voice library'],['speech','Create speech'],['experiments','Acoustic ML']].map(([id,label]) => <button key={id} id={'nav-'+id} className={'nav-button '+(view===id?'active':'')} aria-current={view===id?'page':undefined} onClick={()=>navigate(id)}>{label}</button>)}</nav><span className="private-note">Your voice. On your machine.</span></header>
    <div id="message" className={"notice"+(error?" error":"")} role="status" hidden={!message}>{message}</div>
    <main id="main"><div hidden={view!=='calibrate'}><Calibration notify={setMessage} onLock={setLocked} onFinalize={()=>{refresh();setView('library');}} /></div>
    <section id="view-library" className="single-view" hidden={view!=='library'}><div className="eyebrow">YOUR LOCAL COLLECTION</div><h1>Voice library</h1><p>Profiles from your authorised recordings. All audio stays local.</p><div className="button-row"><button id="new-calibration" onClick={()=>navigate('calibrate')}>Record a voice</button><button id="refresh-library" onClick={refresh}>Refresh library</button></div><div id="profiles-list">{!profiles.length && <p>No voice profiles yet.</p>}{profiles.map(p=><article className="profile-row" key={p.voice_id}><div><h2>{p.name}</h2><p>{p.voice_id}</p></div><button onClick={()=>{setVoice(p.voice_id);navigate('speech');}}>Create speech</button></article>)}</div></section>
    <div hidden={view!=='speech'}><Speech active={view==='speech'} profiles={profiles} voice={voice} setVoice={setVoice} notify={setMessage}/></div>
    <section id="experiments-panel" className="single-view" hidden={view!=='experiments'}><details id="experiments-details" open><summary>Optional · Local acoustic ML experiment</summary><Experiments active={view==='experiments'} notify={setMessage}/></details></section></main></>;
}
createRoot(document.getElementById('root')).render(<App/>);
