'use strict';
// Reuse Puppeteer from the receipt generator — no separate npm install needed.
const puppeteer = require('../insight_receiptgenerator/node_modules/puppeteer');
const path = require('path');

const [,, htmlFile, pdfFile] = process.argv;
if (!htmlFile || !pdfFile) {
  console.error('Usage: node render_report.js <html_file> <pdf_file>');
  process.exit(1);
}

(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 900 });
    await page.goto('file://' + path.resolve(htmlFile), { waitUntil: 'networkidle0' });

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
      path: pdfFile,
      printBackground: true,
      width: '1200px',
      height: `${Math.max(contentHeight, 900) + 10}px`,
    });
    console.log('PDF written to', pdfFile);
  } finally {
    await browser.close();
  }
})().catch(err => { console.error(err); process.exit(1); });
