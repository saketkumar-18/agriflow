const { connect } = require('C:/Users/devil/AppData/Local/hermes/skills/web/browser-cdp-automation/scripts/cdp_node_driver.js');
(async () => {
  const p = await connect(9224);
  await p.send('Page.enable');
  await p.send('Page.navigate', { url: 'http://localhost:3005/fields/1' });
  await new Promise(r => setTimeout(r, 12000));
  // click the "📈" history-expander button
  const clicked = await p.eval(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.innerText.includes('\\u{1F4C8}'));
    if (b) { b.click(); return 'clicked'; } return 'not-found';
  })()`);
  await new Promise(r => setTimeout(r, 12000));
  const svg = await p.eval('document.querySelectorAll("svg").length');
  const tables = await p.eval('document.querySelectorAll("table").length');
  console.log('expand:', clicked, '| svgs:', svg, '| sr-only tables:', tables);
  p.close();
  process.exit(svg >= 2 ? 0 : 1);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
