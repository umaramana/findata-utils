'use strict';
// Reuse Puppeteer from the receipt generator — no separate npm install needed.
const puppeteer = require('../insight_receiptgenerator/node_modules/puppeteer');
const path = require('path');

const args = process.argv.slice(2);
const modeArg = args.find(a => a.startsWith('--mode='));
const mode = modeArg ? modeArg.split('=')[1] : 'pdf';
const [htmlFile, outFile] = args.filter(a => !a.startsWith('--'));

if (!htmlFile || !outFile) {
  console.error('Usage: node render_report.js <html_file> <output_file> [--mode=pdf|png]');
  process.exit(1);
}

(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 900 });
    await page.goto('file://' + path.resolve(htmlFile), { waitUntil: 'networkidle0' });

    if (mode === 'png') {
      // Nudge card is a single fixed-size element, not a flowing multi-page
      // document — screenshot just its bounding box rather than the whole
      // (arbitrarily tall) 1200px viewport.
      const card = await page.$('#nudge-card');
      if (!card) {
        throw new Error('#nudge-card element not found in template');
      }
      await card.screenshot({ path: outFile, omitBackground: false });
      console.log('PNG written to', outFile);
      return;
    }

    // Let content define the page height so the PDF is one continuous flow.
    // Flex min-height:100% can cause scrollHeight to underreport — take the max
    // of all three height measures and add a small buffer to prevent clipping.
    const contentHeight = await page.evaluate(() => Math.max(
      document.body.scrollHeight,
      document.body.offsetHeight,
      document.documentElement.scrollHeight,
      document.documentElement.offsetHeight,
    ));

    // Small buffer (not the old +60) — the scrollHeight-underreport quirk
    // above is real, but a full 60px was overcorrecting into a visible gap.
    await page.pdf({
      path: outFile,
      printBackground: true,
      width: '1200px',
      height: `${Math.max(contentHeight, 900) + 10}px`,
    });
    console.log('PDF written to', outFile);
  } finally {
    await browser.close();
  }
})().catch(err => { console.error(err); process.exit(1); });
