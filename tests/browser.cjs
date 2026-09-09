const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||(process.platform==='win32'?'python':'python3');
 const server=spawn(python,['server.py'],{cwd:root,stdio:'ignore'});let browser;
 try{
  for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:8765/revision')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1280,height:720},hasTouch:true});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const hour=Math.floor(Date.now()/3600000)*3600,day=Math.floor(Date.now()/86400000)*86400;
  const arr=(n,fn)=>Array.from({length:n},(_,i)=>fn(i));
  const fixture={timezone:'America/Phoenix',current:{time:hour,temperature_2m:32,relative_humidity_2m:24,apparent_temperature:31,is_day:1,weather_code:0,wind_speed_10m:16,wind_direction_10m:225},hourly:{time:arr(192,i=>hour+i*3600),temperature_2m:arr(192,i=>30-i%12),precipitation_probability:arr(192,i=>i%4*10),weather_code:arr(192,i=>i%4),is_day:arr(192,i=>i%24<12?1:0)},daily:{time:arr(8,i=>day+i*86400),temperature_2m_max:arr(8,i=>34+i%3),temperature_2m_min:arr(8,i=>22+i%3),weather_code:arr(8,i=>[0,2,3,61,95,71,0,0][i]),precipitation_probability_max:arr(8,i=>i*10),uv_index_max:arr(8,()=>7.6),sunrise:arr(8,i=>day+i*86400+13*3600),sunset:arr(8,i=>day+i*86400+26*3600),wind_speed_10m_max:arr(8,()=>20)}};
  let offline=false,airMissing=false;
  await page.route('https://api.open-meteo.com/**',route=>offline?route.abort():route.fulfill({json:{...fixture,timezone:route.request().url().includes('latitude=35.68')?'Asia/Tokyo':'America/Phoenix'}}));
  await page.route('https://air-quality-api.open-meteo.com/**',route=>route.fulfill({json:{current:airMissing?{us_aqi:null,pm2_5:null,pm10:null}:{us_aqi:42,pm2_5:6.5,pm10:12.1}}}));
  await page.route('https://api.weather.gov/**',route=>route.fulfill({json:{features:[{properties:{event:'Heat advisory',headline:'Test heat advisory',description:'Test alert description',instruction:'Test instructions'}}]}}));
  await page.route('https://geocoding-api.open-meteo.com/**',route=>route.fulfill({json:{results:[{name:'Tokyo',admin1:'Tokyo',country_code:'JP',latitude:35.68,longitude:139.69,timezone:'Asia/Tokyo'}]}}));
  await page.route('https://embed.windy.com/**',route=>route.fulfill({body:'<!doctype html><html><body style="background:#133241;color:white">Interactive radar provider (test fixture)</body></html>',contentType:'text/html'}));
  await page.goto('http://127.0.0.1:8765/weather.html');
  await page.waitForFunction(()=>document.getElementById('temp').textContent==='90°');
  assert.equal(await page.locator('.hour').count(),12);assert.equal(await page.locator('.day').count(),7);
  async function checkLayout(name){
   const outside=await page.evaluate(()=>[...document.querySelectorAll('#app *')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&(r.bottom>720.5||r.right>1280.5||r.left<0||r.top<0)}).map(e=>e.id||e.className));
   assert.deepEqual(outside,[],name+' has clipped content');
   assert.deepEqual(await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.scrollHeight]),[1280,720]);
   fs.mkdirSync(path.join(root,'test-results'),{recursive:true});await page.screenshot({path:path.join(root,'test-results',name+'.png')});
  }
  await page.locator('#alertbar.show').waitFor();await checkLayout('home-v2');
  await page.locator('#alertbar').click();await page.locator('#alertsDialog[open]').waitFor();assert.match(await page.locator('#alertText').textContent(),/Test instructions/);await page.locator('#closeAlerts').click();
  await page.locator('[data-view="forecastView"]').click();await checkLayout('details-v2');await page.waitForFunction(()=>document.getElementById('aqi').textContent==='42');
  await page.locator('[data-view="radarView"]').click();await checkLayout('radar-v2');assert.match(await page.locator('#radarFrame').getAttribute('src'),/overlay=radar/);assert.match(await page.locator('#radarFrame').getAttribute('src'),/lat=33.4484/);
  await page.locator('[data-view="settingsView"]').click();await checkLayout('settings-v2');
  await page.locator('#unitSetting').selectOption('C');await page.locator('#clockSetting').selectOption('24');await page.locator('#refreshSetting').selectOption('5');
  await page.locator('#openKeyboard').click();for(const key of ['T','O','K','Y','O'])await page.locator('#touchKeyboard button').filter({hasText:new RegExp('^'+key+'$')}).click();
  assert.equal(await page.locator('#cityInput').inputValue(),'TOKYO');await page.locator('#touchKeyboard button').filter({hasText:/^Search$/}).click();
  await page.getByRole('button',{name:/Tokyo, Tokyo, JP/}).waitFor();await checkLayout('search-v2');
  await page.getByRole('button',{name:/Tokyo, Tokyo, JP/}).click();await page.waitForFunction(()=>document.getElementById('temp').textContent==='32°');
  await page.reload();await page.waitForFunction(()=>document.getElementById('temp').textContent==='32°');assert.match(await page.locator('#locationLabel').textContent(),/Tokyo/);
  assert(!/AM|PM/.test(await page.locator('#clock').textContent()));
  const sunriseExpected=await page.evaluate(epoch=>new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Tokyo',hour:'numeric',minute:'2-digit',hour12:false}).format(epoch*1000),fixture.daily.sunrise[0]);
  // Selected-city sunrise and daylight use epoch seconds, independent of host timezone.
  const actualSunrise=await page.evaluate(()=>timeFmt(wxData.daily.sunrise[0]));assert.equal(actualSunrise,sunriseExpected);
  offline=true;airMissing=true;await page.evaluate(()=>loadWeather(false));await page.waitForFunction(()=>document.getElementById('updated').textContent.includes('Offline'));assert.equal(await page.locator('#temp').textContent(),'32°');
  await page.waitForFunction(()=>document.getElementById('aqi').textContent==='--');assert.match(await page.locator('#aqiLabel').textContent(),/unavailable/);
  await page.reload();await page.waitForFunction(()=>document.getElementById('updated').textContent.includes('Offline'));assert.equal(await page.locator('#temp').textContent(),'32°');
  let exitRequest;
  await page.route('**/exit',async route=>{exitRequest=route.request();await route.fulfill({status:202,body:'Weather kiosk stopping'});});
  await page.locator('[data-view="settingsView"]').click();await page.waitForFunction(()=>!document.getElementById('exitDesktop').disabled);await page.locator('#exitDesktop').click();await page.waitForFunction(()=>document.getElementById('exitStatus').textContent.includes('Returning'));
  assert.equal(exitRequest.method(),'POST');assert(exitRequest.headers()['x-weather-token']);
  await page.route('http://127.0.0.1:8765/revision',route=>route.fulfill({body:'a'.repeat(64)}));await Promise.all([page.waitForEvent('load'),page.evaluate(()=>checkRevision())]);
  assert.deepEqual(errors,[]);
  // A failed first request must schedule a retry even with no cache.
  await page.unroute('http://127.0.0.1:8765/revision');await page.evaluate(()=>localStorage.clear());await page.clock.install();await page.reload();await page.waitForFunction(()=>document.getElementById('updated').textContent.includes('retrying'));
  offline=false;await page.clock.fastForward(61000);await page.waitForFunction(()=>document.getElementById('temp').textContent==='90°');
  console.log('PASS: all four 1280x720 tabs, radar URL, graphs, alerts, touch search, settings, timezones, offline/cache/retry, exit POST and revision reload.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
