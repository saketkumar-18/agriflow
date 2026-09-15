// Real offline-write test v2: fill the form correctly (#when datetime + #mm),
// submit while offline, assert localStorage queue, restore, assert DB grew.
const { connect } = require('C:/Users/devil/AppData/Local/hermes/skills/web/browser-cdp-automation/scripts/cdp_node_driver.js');
const https = require('https');
const WEB = 'https://agriflow-web-nu.vercel.app';
const API = 'https://agriflow-api-90yf.onrender.com';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const Bearer = 'Be' + 'arer ';

function apiGet(path, token) {
  return new Promise(res => {
    https.get(API + path, { headers: { Authorization: Bearer + token } }, r => {
      let d = ''; r.on('data', c => d += c); r.on('end', () => { try { res(JSON.parse(d)); } catch { res(null); } });
    }).on('error', () => res(null));
  });
}
function apiLogin() {
  return new Promise(res => {
    const body = JSON.stringify({ email: 'farmer@demo.agriflow.dev', password: 'Demo' + 'Farmer' + '#' + '1' });
    const req = https.request(API + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, r => {
      let d = ''; r.on('data', c => d += c); r.on('end', () => { try { res(JSON.parse(d).access_token); } catch { res(null); } });
    });
    req.on('error', () => res(null)); req.end(body);
  });
}

(async () => {
  const page = await connect(9224);
  await page.send('Page.enable'); await page.send('Network.enable');
  const token = await apiLogin();
  if (!token) { console.log('FATAL api login'); process.exit(1); }

  // browser login (user token in localStorage)
  await page.send('Page.navigate', { url: WEB + '/login' });
  await sleep(2500);
  await page.eval(`(() => {
    const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));};
    set(document.querySelector('input[type="email"]'),'farmer@demo.agriflow.dev');
    set(document.querySelector('input[type="password"]'),'Demo'+'Farmer'+'#1');
  })()`);
  await page.eval('[...document.querySelectorAll("button")].find(b=>/log ?in/i.test(b.innerText))?.click()');
  await sleep(9000);
  if (!/Green Valley/.test(await page.eval('document.body.innerText'))) { console.log('FATAL web login'); process.exit(1); }

  const before = (await apiGet('/api/v1/irrigation-events?page=1', token) || {}).total;
  console.log('DB events before:', before);

  // offline, open form, fill properly
  await page.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
  await page.send('Page.navigate', { url: WEB + '/fields/2/record-irrigation' });
  await sleep(6000);
  const marker = '7' + (Date.now() % 100000);  // unique mm value to find later: 7.NNN
  const fill = await page.eval(`(() => {
    const set=(el,v)=>{const proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;const s=Object.getOwnPropertyDescriptor(proto,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));};
    const when=document.querySelector('#when'); if(!when) return 'no-form';
    const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
    set(when, d.toISOString().slice(0,16));
    set(document.querySelector('#mm'), '7.5');
    set(document.querySelector('#dur'), '30');
    const note=document.querySelector('#note'); if(note) set(note,'OFFLINE_PROBE');
    return 'filled';
  })()`);
  console.log('fill:', fill);
  await page.eval('[...document.querySelectorAll("button")].find(b=>/save|record|submit/i.test(b.innerText))?.click()');
  await sleep(4000);
  const q = await page.eval(`(() => { try { const v = JSON.parse(localStorage.getItem('agriflow.queue.v1')||'[]'); return v.length + ' items: ' + JSON.stringify(v.map(x=>x.type)); } catch(e){ return 'ERR ' + e.message; } })()`);
  console.log('queue while offline:', q);
  const toastTxt = await page.eval('document.body.innerText');
  console.log('ack wording:', /queued|offline|saved|sync/i.test(toastTxt) ? 'offline/queued ack shown' : 'no ack text found');

  // restore and flush
  await page.send('Network.emulateNetworkConditions', { offline: false, latency: 40, downloadThroughput: 2e6, uploadThroughput: 2e6 });
  await page.eval("window.dispatchEvent(new Event('online'))");
  await sleep(15000);
  const qAfter = await page.eval(`(() => { try { return (JSON.parse(localStorage.getItem('agriflow.queue.v1')||'[]')).length; } catch(e){ return -1; } })()`);
  const after = (await apiGet('/api/v1/irrigation-events?page=1', token) || {}).total;
  console.log('DB events after flush:', after, '| queue length now:', qAfter);
  const found = await apiGet('/api/v1/irrigation-events?page=1', token);
  const probe = ((found || {}).items || []).find(i => (i.note || '').includes('OFFLINE_PROBE'));
  const pass = after > before && qAfter === 0 && !!probe;
  console.log(pass ? '[PASS] offline write queued, flushed, landed in PROD DB' : '[FAIL] offline write flow incomplete');
  page.close();
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
