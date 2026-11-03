const fs = require('fs');
const path = require('path');
const {chromium} = require(process.env.EA_PLAYWRIGHT || 'playwright');
const root = path.resolve(__dirname, '..');
const file = p => path.join(root, p);

(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto('http://127.0.0.1:8765');
    await page.click('#connect');
    await page.waitForFunction(() => document.querySelector('#connectionText').textContent.includes('已就绪'), null, {timeout:90000});
    await page.click('#run');
    await page.waitForFunction(() => document.querySelector('#verdictText').textContent === '检测到异常', null, {timeout:60000});
    await page.waitForTimeout(300);
    await page.screenshot({path:file('report/figures/frontend_fpga_defect.png'),fullPage:true});
    const defect = await page.locator('#score').textContent();
    if (defect !== '0.345157') throw Error(defect);
    await page.click('[data-sample="n17_03"]');
    await page.click('#run');
    await page.waitForFunction(() => document.querySelector('#verdictText').textContent === '合格', null, {timeout:60000});
    await page.waitForTimeout(300);
    await page.screenshot({path:file('report/figures/frontend_fpga_normal.png'),fullPage:true});
    const normal = await page.locator('#score').textContent();
    if (normal !== '0.073264') throw Error(normal);
    await page.click('#present');
    await page.screenshot({path:file('report/figures/frontend_presentation.png'),fullPage:true});
    await page.click('#present');
    await page.click('[data-page="evidence"]:visible');
    if (!(await page.locator('#historicalAccuracy').textContent()).includes('66.67')) throw Error('Stale accuracy card');
    await page.screenshot({path:file('report/figures/frontend_evidence.png'),fullPage:true});
    await page.setViewportSize({width:800,height:1000});
    await page.click('[data-page="workbench"]:visible');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow) throw Error('Horizontal overflow');
    await page.selectOption('#backend','int8_reference');
    await page.setInputFiles('#file',file('data/samples/n17_03.png'));
    await page.click('#run');
    await page.waitForFunction(() => document.querySelector('#verdictText').textContent === '合格', null, {timeout:60000});
    const pendingDownload = page.waitForEvent('download');
    await page.click('#export');
    await (await pendingDownload).saveAs(file('sim/results/frontend_export.csv'));
    const evidence = await page.evaluate(() => fetch('/api/evidence').then(r=>r.json()));
    if (evidence.received_accuracy.board.count !== 75) throw Error('Missing board accuracy evidence');
    const caps = await page.evaluate(() => ({camera:typeof navigator.mediaDevices?.getUserMedia==='function',screenCapture:typeof navigator.mediaDevices?.getDisplayMedia==='function',recorder:typeof MediaRecorder==='function'}));
    if (errors.length) throw Error(JSON.stringify(errors));
    const record = {status:'FRONTEND_FPGA_AND_REFERENCE_E2E_PASSED',delivery_root:root,
      fpga_defect_score:defect,fpga_normal_score:normal,mobile_horizontal_overflow:overflow,javascript_errors:errors,
      browser_capabilities:caps,received_board_images:evidence.received_accuracy.board.count,
      camera_physical_capture:'not tested; requires user camera permission',
      screen_recording:'API available; requires user screen selection',timestamp:new Date().toISOString()};
    fs.writeFileSync(file('sim/results/frontend_validation.json'),JSON.stringify(record,null,2));
    console.log(JSON.stringify(record));
  } finally { await browser.close(); }
})().catch(e => { console.error(e);process.exitCode=1; });
