const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
 const root=path.resolve(__dirname,'..');
 const python=process.env.PYTHON || (process.platform==='win32'?'python':'python3');
 const server=spawn(python,['server.py'],{cwd:root,stdio:'ignore'});
 let browser;
 try {
  for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:8765/revision')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  const options={headless:true};
  if(process.env.CHROME_PATH) options.executablePath=process.env.CHROME_PATH;
  browser=await chromium.launch(options);
  const page=await browser.newPage({viewport:{width:1280,height:720},hasTouch:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const hour=Math.floor(Date.now()/3600000)*3600;
  const day=Math.floor(Date.now()/86400000)*86400;
  const arr=(n,fn)=>Array.from({length:n},(_,i)=>fn(i));
  const fixture={timezone:'America/Phoenix',current:{time:hour,temperature_2m:32,relative_humidity_2m:24,apparent_temperature:31,is_day:1,weather_code:0,wind_speed_10m:16,wind_direction_10m:225},hourly:{time:arr(192,i=>hour+i*3600),temperature_2m:arr(192,i=>30-i%12),precipitation_probability:arr(192,i=>i%4*10),weather_code:arr(192,i=>i%4),is_day:arr(192,i=>i%24<12?1:0)},daily:{time:arr(8,i=>day+i*86400),temperature_2m_max:arr(8,i=>34+i%3),temperature_2m_min:arr(8,i=>22+i%3),weather_code:arr(8,i=>[0,2,3,61,95,71,0,0][i]),precipitation_probability_max:arr(8,i=>i*10),uv_index_max:arr(8,()=>7.6),sunrise:arr(8,i=>day+i*86400+13*3600),sunset:arr(8,i=>day+i*86400+26*3600)}};
  let offline=false;
  await page.route('https://api.open-meteo.com/**',route=>offline?route.abort():route.fulfill({json:fixture}));
  await page.route('https://geocoding-api.open-meteo.com/**',route=>route.fulfill({json:{results:[{name:'Tokyo',admin1:'Tokyo',country_code:'JP',latitude:35.68,longitude:139.69,timezone:'Asia/Tokyo'}]}}));
  await page.goto('http://127.0.0.1:8765/weather.html');
  await page.waitForFunction(()=>document.getElementById('temperature').textContent==='90°');
  assert.equal(await page.locator('.hour').count(),12);
  assert.equal(await page.locator('.day').count(),7);
  const overflow=await page.evaluate(()=>({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,outside:[...document.querySelectorAll('#app *')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&(r.bottom>720.5||r.right>1280.5||r.left<0||r.top<0)}).map(e=>e.id||e.className)}));
  assert.deepEqual(overflow,{width:1280,height:720,outside:[]});
  fs.mkdirSync(path.join(root,'test-results'),{recursive:true});
  await page.screenshot({path:path.join(root,'test-results/dashboard.png')});
  await page.locator('#units').click();assert.equal(await page.locator('#temperature').textContent(),'32°');
  await page.locator('#city').click();
  for(const key of ['T','O','K','Y','O'])await page.locator('#keyboard button').filter({hasText:new RegExp('^'+key+'$')}).click();
  assert.equal(await page.locator('#search').inputValue(),'TOKYO');
  await page.locator('#search-form button').click();await page.getByRole('button',{name:'Tokyo, Tokyo, JP',exact:true}).waitFor();
  await page.screenshot({path:path.join(root,'test-results/city-selector.png')});
  assert(await page.locator('#city-dialog').evaluate(e=>e.scrollHeight<=e.clientHeight));
  await page.getByRole('button',{name:'Tokyo, Tokyo, JP',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('temperature').textContent==='32°');
  await page.reload();await page.waitForFunction(()=>document.getElementById('temperature').textContent==='32°');
  assert.match(await page.locator('#city').textContent(),/Tokyo/);
  offline=true;await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Offline'));
  assert.equal(await page.locator('#temperature').textContent(),'32°');
  await page.reload();await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Offline'));
  assert.equal(await page.locator('#temperature').textContent(),'32°');
  await page.route('http://127.0.0.1:8765/revision',route=>route.fulfill({body:'a'.repeat(64)}));
  await Promise.all([page.waitForEvent('load'),page.evaluate(()=>checkRevision())]);
  assert.deepEqual(errors,[]);
  console.log('PASS: 1280x720 layout, 12 hours, 7 days, touch search, units, persistence, offline cache, revision reload; no JS errors.');
 } finally {if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
