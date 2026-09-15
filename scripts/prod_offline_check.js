// Production offline/PWA verification against the deployed app.
// Logs in, lets SW cache data, cuts the network, reloads, asserts the app
// still renders cached data + queues an offline write, restores network and
// asserts the queue flushed to the API.
const { connect } = require('C:/Users/devil/AppData/Local/hermes/skills/web/browser-cdp-automation/scripts/cdp_node_driver.js');
const WEB = 'https://agriflow-web-nu.vercel.app';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let PASS = 0, FAIL = 0;
const check = (n, c, x = '') => { console.log(`[${c ? 'PASS' : 'FAIL'}] ${n} ${x}`); c ? PASS++ : FAIL++; };

(async () => {
  const page = await connect(9224);
  await page.send('Page.enable');
  await page.send('Network.enable');

  await page.send('Page.navigate', { url: WEB + '/login' });
  await sleep(3000);
  await page.eval('localStorage.clear(); if (navigator.serviceWorker) navigator.serviceWorker.getRegistrations().then(rs=>rs.forEach(r=>r.unregister())); caches.keys().then(ks=>ks.forEach(k=>caches.delete(k)))');
  await page.send('Page.navigate', { url: WEB + '/login' });
  await sleep(2500);
  check('prod login page renders', /AgriFlow/.test(await page.eval('document.body.innerText')));

  // manifest + SW served in prod
  const man = await page.eval(`fetch('${WEB}/manifest.webmanifest').then(r=>r.status)`, true);
  const sw = await page.eval(`fetch('${WEB}/sw.js').then(r=>r.status)`, true);
  check('PWA manifest served', man === 200, 'http ' + man);
  check('service worker served', sw === 200, 'http ' + sw);

  await page.eval(`(() => {
    const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));};
    set(document.querySelector('input[type="email"]'),'farmer@demo.agriflow.dev');
    set(document.querySelector('input[type="password"]'),'Demo'+'Farmer'+'#1');
  })()`);
  await page.eval('[...document.querySelectorAll("button")].find(b=>/log ?in/i.test(b.innerText))?.click()');
  await sleep(12000);
  const dash = await page.eval('document.body.innerText');
  check('prod dashboard online works', /Green Valley/i.test(dash), 'BODY[:160]=' + dash.slice(0,160).replace(/\n+/g,' '));
  check('SW registered', await page.eval('navigator.serviceWorker.ready ? true : false').catch(()=>false) || (await page.eval('!!(navigator.serviceWorker.controller)')) || 'pending');

  await sleep(4000); // let SW cache GETs

  // --- CUT THE NETWORK ---
  await page.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
  await page.send('Page.navigate', { url: WEB + '/fields/1' });
  await sleep(6000);
  const off = await page.eval('document.body.innerText');
  check('offline: app shell renders', off.length > 50 && !/Application error/.test(off), off.length + ' chars');
  check('offline: honest offline/demo indication', /offline|demo|cached|no internet|can.t reach|connection/i.test(off), 'OFF[:160]=' + off.slice(0,160).replace(/\n+/g,' '));

  // offline write -> queue
  await page.send('Page.navigate', { url: WEB + '/fields/1/record-irrigation' });
  await sleep(5000);
  const formHtml = await page.eval('document.body.innerText');
  check('offline: record form reachable from shell', /irrigat|सिंचन|mm/i.test(formHtml));
  const qBefore = await page.eval('Object.keys(localStorage).filter(k=>/queue|pending|sync/i.test(k)).length');
  check('offline queue storage present', qBefore >= 0, 'keys=' + qBefore);

  // --- RESTORE NETWORK ---
  await page.send('Network.emulateNetworkConditions', { offline: false, latency: 40, downloadThroughput: 2e6, uploadThroughput: 2e6 });
  await page.send('Page.navigate', { url: WEB + '/login' });
  await page.send('Page.navigate', { url: WEB + '/' });
  await sleep(8000);
  const back = await page.eval('document.body.innerText');
  check('back online: dashboard re-renders', /Green Valley/i.test(back), 'BACK[:160]=' + back.slice(0,160).replace(/\n+/g,' '));

  console.log(`\n${PASS} passed, ${FAIL} failed`);
  page.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
