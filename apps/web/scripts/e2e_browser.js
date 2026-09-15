// AgriFlow browser E2E: login -> dashboard -> field -> record irrigation.
// Drives headless Chrome over CDP (port 9224). Zero npm deps.
const { connect } = require('C:/Users/devil/AppData/Local/hermes/skills/web/browser-cdp-automation/scripts/cdp_node_driver.js');
const http = require('http');

const PORT = 9224;
const WEB = 'http://localhost:3005';

function jfetch(url, method = 'GET') {
  return new Promise((res, rej) => {
    const req = http.request(url, { method }, r => {
      let d = ''; r.on('data', c => d += c); r.on('end', () => { try { res(JSON.parse(d)); } catch (e) { res(d); } });
    });
    req.on('error', rej); req.end();
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

let PASS = 0, FAIL = 0;
function check(name, cond, extra = '') {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name} ${extra}`);
  cond ? PASS++ : FAIL++;
}

async function setNativeValue(page, selector, value) {
  await page.eval(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return 'no-element';
    const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, ${JSON.stringify(value)});
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return 'ok';
  })()`);
}

async function main() {
  await jfetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent('?url=' + WEB + '/login')}`.replace('/json/new?%3Furl%3D', '/json/new?url='));
  const pages = await jfetch(`http://127.0.0.1:${PORT}/json`);
  let tab = pages.find(t => t.type === 'page');
  if (!tab) throw new Error('no tab opened');
  const page = await connect(PORT);
  await page.send('Page.enable');
  await page.send('Page.navigate', { url: WEB + '/login' });
  await sleep(2000);
  // suite isolation: wipe app state first (skill rule: reset at suite start)
  await page.eval('localStorage.clear(); sessionStorage.clear();');
  await page.send('Page.reload');
  await sleep(3000);

  // 1. login form present
  let html = await page.eval('document.body.innerText.slice(0,1200)');
  check('login page renders', /AgriFlow/i.test(html) && /password/i.test(html), '');

  // 2. fill demo farmer credentials and submit
  await setNativeValue(page, 'input[type="email"], input[name="email"], input[autocomplete="username"]', 'farmer@demo.agriflow.dev');
  await setNativeValue(page, 'input[type="password"]', 'DemoFarmer#1');
  html = await page.eval('document.body.innerText.slice(0,200)');
  await page.eval('(() => { const b=[...document.querySelectorAll("button")].find(x=>/log ?in|sign ?in/i.test(x.innerText)); if(b){b.click(); return "clicked"} return "no-button"; })()');
  await sleep(15000);

  // 3. dashboard: farm + recommendation + demo banner
  html = await page.eval('document.body.innerText');
  check('dashboard shows farm', /Green Valley/i.test(html));
  check('irrigation decision visible', /irrigat/i.test(html), '');
  check('data honestly labeled demo', /demo/i.test(html));
  check('confidence + reasons present', /confidence/i.test(html));

  // 4. navigate to a field detail page (charts lazy behind expander button)
  await page.send('Page.navigate', { url: WEB + '/fields/1' });
  await sleep(8000);
  html = await page.eval('document.body.innerText');
  check('field detail loads', /Field A|Wheat/i.test(html));
  await page.eval(`(() => { const b=[...document.querySelectorAll('button')].find(x=>/\\u{1F4C8}/u.test(x.innerText)); if(b) b.click(); })()`);
  await sleep(6000);
  const svg = await page.eval('document.querySelectorAll("svg").length');
  check('charts rendered', Number(svg) >= 2, `svg count=${svg}`);

  // 5. record irrigation form reachable
  await page.send('Page.navigate', { url: WEB + '/fields/1/record-irrigation' });
  await sleep(3000);
  html = await page.eval('document.body.innerText');
  check('record irrigation form', /irrigat/i.test(html) && (await page.eval('document.querySelectorAll("input").length')) >= 2);

  // 6. language switch to Hindi exists (header toggle renders "हि")
  await page.send('Page.navigate', { url: WEB + '/' });
  await sleep(4000);
  const nav = await page.eval('document.body.innerText');
  check('hindi toggle present', /हि/.test(nav));
  const switched = await page.eval('(() => { const b=[...document.querySelectorAll("button,a")].find(x=>x.innerText.trim()==="हि"); if(b){b.click(); return 1} return 0; })()');
  await sleep(2500);
  const hi = await page.eval('document.body.innerText');
  check('hindi switch works', switched && /सिंचन|मिट्टी|नम|खेत/i.test(hi));

  console.log(`\n${PASS} passed, ${FAIL} failed`);
  page.close();
  process.exit(FAIL ? 1 : 0);
}
main().catch(e => { console.error('FATAL', e.message); process.exit(1); });
