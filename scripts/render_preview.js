// Renders scripts/social-preview.html to docs/social-preview.png (1280x640).
// Usage: node scripts/render_preview.js   (needs the playwright package with Chromium available)
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
  await page.goto('file://' + path.join(root, 'scripts', 'social-preview.html'));
  await page.screenshot({ path: path.join(root, 'docs', 'social-preview.png') });
  await browser.close();
})();
