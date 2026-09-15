const { connect } = require('C:/Users/devil/AppData/Local/hermes/skills/web/browser-cdp-automation/scripts/cdp_node_driver.js');
const fs = require('fs');
(async () => {
  const p = await connect(9224);
  await p.send('Page.enable');
  // ensure English dashboard with data
  await p.send('Page.navigate', { url: 'http://localhost:3005/login' });
  await new Promise(r => setTimeout(r, 2500));
  await p.eval('localStorage.clear()');
  await p.send('Page.reload');
  await new Promise(r => setTimeout(r, 2500));
  await p.eval(`(() => {
    const set=(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));};
    set(document.querySelector('input[type="email"]'),'farmer@demo.agriflow.dev');
    set(document.querySelector('input[type="password"]'),'Demo'+'Farmer'+'#1');
  })()`);
  await p.eval('[...document.querySelectorAll("button")].find(b=>/log ?in/i.test(b.innerText))?.click()');
  await new Promise(r => setTimeout(r, 6000));
  await p.send('Emulation.setDeviceMetricsOverride', { width: 420, height: 900, deviceScaleFactor: 2, mobile: true });
  await new Promise(r => setTimeout(r, 1500));
  const shot = await p.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('C:/Users/devil/Downloads/agriflow/docs/screenshot-dashboard.png', Buffer.from(shot.data, 'base64'));
  console.log('dashboard shot saved');
  // field detail with charts expanded
  await p.send('Page.navigate', { url: 'http://localhost:3005/fields/1' });
  await new Promise(r => setTimeout(r, 8000));
  await p.eval(`(() => { const b=[...document.querySelectorAll('button')].find(x=>/\\u{1F4C8}/u.test(x.innerText)); if(b) b.click(); })()`);
  await new Promise(r => setTimeout(r, 6000));
  await p.send('Emulation.setDeviceMetricsOverride', { width: 420, height: 1200, deviceScaleFactor: 2, mobile: true });
  await new Promise(r => setTimeout(r, 1000));
  const shot2 = await p.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('C:/Users/devil/Downloads/agriflow/docs/screenshot-field-charts.png', Buffer.from(shot2.data, 'base64'));
  console.log('field shot saved');
  p.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
