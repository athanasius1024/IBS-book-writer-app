// Drives the real "Insert image" dialog in Chromium: upload, draw / move / resize a crop, square lock,
// width, placement, caption, insert, save the block, then re-open the reference and update it.
//
// Optional (not part of pytest). To run it:
//   1. python tests/browser/serve_test_app.py                      # a throwaway app on http://127.0.0.1:5099
//   2. in any folder:  npm install puppeteer-core
//   3. NODE_PATH=<that folder>/node_modules CHROMIUM=/usr/bin/chromium node tests/browser/dialog.test.js
// Restart step 1 before every run: the script registers the user "uitester" on a clean database.
// Settings (environment): IBS_URL, CHROMIUM (path to Chrome/Chromium), TEST_IMAGE (a PNG about 400x300).
// A snap-packaged Chromium cannot read /tmp, so keep TEST_IMAGE somewhere under your home folder.
const puppeteer = require('puppeteer-core');
const BASE = process.env.IBS_URL || 'http://127.0.0.1:5099';
const CHROMIUM = process.env.CHROMIUM || '/usr/bin/chromium';
const TEST_IMAGE = process.env.TEST_IMAGE || require('path').join(__dirname, 'two-colours.png');
const results = [];
let fc0 = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  [' + detail + ']' : '')); };
const near = (a, b, eps) => Math.abs(a - b) <= eps;

(async () => {
    const browser = await puppeteer.launch({
        executablePath: CHROMIUM, headless: true,
        args: ['--no-sandbox', '--disable-gpu', '--window-size=1400,1000']
    });
    const page = await browser.newPage();
    await page.setViewport({width: 1400, height: 1000});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('dialog', d => d.accept());

    // --- sign up, create a book and a chapter
    await page.goto(BASE + '/register');
    await page.type('input[name=username]', 'uitester');
    await page.type('input[name=password]', 'correct-horse-battery');
    await page.type('input[name=confirm_password]', 'correct-horse-battery');
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    await page.goto(BASE + '/books/new');
    await page.type('input[name=title]', 'UI Test Book');
    await Promise.all([page.waitForNavigation(), page.click('main form button[type=submit]')]);
    await page.type('input[name=title][placeholder="New chapter title"]', 'Chapter One');
    await Promise.all([page.waitForNavigation(), page.click('form[action*="/chapters/new"] button')]);
    check('on the chapter page', /\/chapters\/\d+/.test(page.url()), page.url());

    // --- open the dialog, upload a picture
    await page.type('#add-block-form textarea[name=content_text]', 'Before. ');
    await page.click('#add-block-form [data-insert-image]');
    await page.waitForSelector('#imageModal.show', {visible: true});
    check('dialog opens on the library step', await page.$eval('#img-step-pick', e => !e.hidden));
    const input = await page.$('#img-upload');
    await input.uploadFile(TEST_IMAGE);
    await page.waitForFunction(() => !document.getElementById('img-step-edit').hidden, {timeout: 15000});
    await page.waitForFunction(() => { const i = document.getElementById('img-stage-img'); return i.complete && i.naturalWidth > 0; });
    check('an uploaded picture goes straight to the edit step', true);
    check('upload reached the library (one picture)', (await (await page.evaluate(() => fetch('/media/library.json').then(r => r.json()))).assets.length) === 1);

    // --- draw a crop: from 10%/10% of the picture to 60%/70%
    const img = await page.$('#img-stage-img');
    let box = await img.boundingBox();
    const fresh = async () => { box = await img.boundingBox(); };
    await new Promise(r => setTimeout(r, 700));      // let the dialog finish sliding in
    await fresh();
    check('picture is displayed', box.width > 100 && box.height > 80, `${Math.round(box.width)}x${Math.round(box.height)}`);
    const at = (fx, fy) => [box.x + box.width * fx, box.y + box.height * fy];
    await fresh();
    await page.mouse.move(...at(0.1, 0.1));
    await page.mouse.down();
    await page.mouse.move(...at(0.35, 0.4), {steps: 5});
    await page.mouse.move(...at(0.6, 0.7), {steps: 5});
    await page.mouse.up();
    let md = await page.$eval('#img-markdown', e => e.textContent);
    let crop = /data-crop="([\d.,]+)"/.exec(md);
    check('dragging draws a crop', !!crop, md);
    let f = crop ? crop[1].split(',').map(Number) : [];
    check('the crop matches the drag (10%,10% to 60%,70%)', near(f[0], 0.1, 0.02) && near(f[1], 0.1, 0.02) && near(f[2], 0.5, 0.02) && near(f[3], 0.6, 0.02), f.join(','));
    check('the crop box is visible', await page.$eval('#crop-box', e => !e.hidden));

    // --- move it by dragging inside
    await fresh();
    await page.mouse.move(...at(0.35, 0.4));
    await page.mouse.down();
    await page.mouse.move(...at(0.45, 0.3), {steps: 5});
    await page.mouse.up();
    md = await page.$eval('#img-markdown', e => e.textContent);
    f = /data-crop="([\d.,]+)"/.exec(md)[1].split(',').map(Number);
    check('dragging inside moves the crop and keeps its size', near(f[0], 0.2, 0.02) && near(f[1], 0.0, 0.02) && near(f[2], 0.5, 0.02) && near(f[3], 0.6, 0.02), f.join(','));

    // --- resize by a corner (south-east handle), the opposite corner stays
    const handle = await (await page.$('#crop-box .crop-h[data-h=se]')).boundingBox();
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(...at(0.6, 0.5), {steps: 5});
    await page.mouse.up();
    f = /data-crop="([\d.,]+)"/.exec(await page.$eval('#img-markdown', e => e.textContent))[1].split(',').map(Number);
    check('dragging a corner resizes, opposite corner fixed', near(f[0], 0.2, 0.02) && near(f[1], 0.0, 0.02) && near(f[2], 0.4, 0.02) && near(f[3], 0.5, 0.02), f.join(','));

    // --- lock the shape to a square: width in px must equal height in px
    await page.select('#img-ratio', '1:1');
    const rect = await page.$eval('#crop-box', e => ({w: e.offsetWidth, h: e.offsetHeight}));
    check('square lock gives equal pixel sides', near(rect.w, rect.h, 2), `${rect.w}x${rect.h}`);
    await page.select('#img-ratio', 'free');

    // --- clear by clicking outside the box
    await fresh();
    await page.mouse.click(...at(0.9, 0.9));
    check('a click outside the box clears the crop', await page.$eval('#crop-box', e => e.hidden));

    // --- final crop, width, placement, caption
    await fresh();
    await page.mouse.move(...at(0.25, 0.25));
    await page.mouse.down(); await page.mouse.move(...at(0.75, 0.75), {steps: 6}); await page.mouse.up();
    await page.$eval('#img-width', e => { e.value = '60'; e.dispatchEvent(new Event('input', {bubbles: true})); });
    await page.click('label[for=img-align-left]');
    await page.type('#img-caption', 'The middle of the picture');
    md = await page.$eval('#img-markdown', e => e.textContent);
    const finalCrop = /data-crop="([\d.,]+)"/.exec(md);
    const fc = finalCrop ? finalCrop[1].split(',').map(Number) : [];
    fc0 = fc;
    check('preview shows crop, width, placement and caption',
          near(fc[0], 0.25, 0.02) && near(fc[1], 0.25, 0.02) && near(fc[2], 0.5, 0.02) && near(fc[3], 0.5, 0.02)
          && /data-w="60"/.test(md) && /\.img-left/.test(md) && /"The middle of the picture"/.test(md), md);
    await page.click('#img-insert');
    await page.waitForSelector('#imageModal', {hidden: true});
    await page.waitForSelector('.modal-backdrop', {hidden: true});
    const text = await page.$eval('#add-block-form textarea[name=content_text]', e => e.value);
    check('the reference was put in the text on its own paragraph', /Before\.\s*\n\n!\[.*\]\(image:\d+ "The middle of the picture"\)\{: data-crop=/.test(text), JSON.stringify(text));

    // --- save the block and see the picture on the page
    await page.click('#add-block-form button[type=submit]');
    await page.waitForSelector('#blocks .content-block figure.inline-figure img', {timeout: 15000});
    await page.waitForFunction(() => { const i = document.querySelector('#blocks figure.inline-figure img'); return i && i.complete && i.naturalWidth > 0; });
    const shown = await page.$eval('#blocks figure.inline-figure img', i => ({src: i.getAttribute('src'), w: i.naturalWidth, h: i.naturalHeight}));
    const srcCrop = (/crop\?c=([\d.,]+)/.exec(shown.src) || [])[1];
    const sc = srcCrop ? srcCrop.split(',').map(Number) : [];
    check('the saved block shows the cropped copy, matching the crop that was drawn',
          /\/media\/\d+\/crop\?c=/.test(shown.src) && sc.length === 4 && sc.every((v, i) => near(v, fc0[i], 0.0001)), shown.src);
    check('the cropped copy is the right size for that crop (about 200x150)',
          near(shown.w, Math.round(sc[2] * 400), 2) && near(shown.h, Math.round(sc[3] * 300), 2) && near(shown.w, 200, 8) && near(shown.h, 150, 8), `${shown.w}x${shown.h}`);
    check('it has a caption and left placement', await page.$eval('#blocks figure.inline-figure', f => f.classList.contains('img-left') && f.querySelector('figcaption').textContent === 'The middle of the picture' && f.style.width === '60%'));
    await page.screenshot({path: '/tmp/ibs-dialog-block.png', fullPage: false});

    // --- re-open the reference from the edit form and update it
    await page.click('#blocks .content-block button[title=Edit]');
    await page.waitForSelector('#blocks .content-block textarea[name=content_text]');
    await page.$eval('#blocks .content-block textarea[name=content_text]', t => { const i = t.value.indexOf('![') + 3; t.focus(); t.setSelectionRange(i, i); });
    await page.click('#blocks .content-block [data-insert-image]');
    await page.waitForFunction(() => document.getElementById('img-step-edit') && !document.getElementById('img-step-edit').hidden, {timeout: 15000});
    await page.waitForFunction(() => { const i = document.getElementById('img-stage-img'); return i.complete && i.naturalWidth > 0 && !document.getElementById('crop-box').hidden; });
    await new Promise(r => setTimeout(r, 700));
    check('re-opening goes straight to the edit step with the crop restored', await page.$eval('#crop-box', e => !e.hidden && e.offsetWidth > 20 && e.offsetHeight > 20));
    const restored = await page.evaluate(() => ({
        width: document.getElementById('img-width').value, caption: document.getElementById('img-caption').value,
        align: document.querySelector('input[name=img-align]:checked').value, label: document.getElementById('img-insert-label').textContent,
        md: document.getElementById('img-markdown').textContent
    }));
    check('width, caption, placement and label are restored', restored.width === '60' && restored.caption === 'The middle of the picture' && restored.align === 'left' && restored.label === 'Update', JSON.stringify(restored));
    const rc = ((/data-crop="([\d.,]+)"/.exec(restored.md) || [])[1] || '').split(',').map(Number);
    check('the restored crop gives the same crop in the Markdown', rc.length === 4 && rc.every((v, i) => near(v, fc0[i], 0.01)), restored.md);
    await page.$eval('#img-caption', e => { e.value = 'A new caption'; e.dispatchEvent(new Event('input', {bubbles: true})); });
    await page.click('label[for=img-align-right]');
    await page.click('#img-insert');
    await page.waitForSelector('#imageModal', {hidden: true});
    await page.waitForSelector('.modal-backdrop', {hidden: true});
    const updated = await page.$eval('#blocks .content-block textarea[name=content_text]', e => e.value);
    check('the existing reference was replaced, not duplicated',
          (updated.match(/image:\d+/g) || []).length === 1 && /"A new caption"/.test(updated) && /\.img-right/.test(updated) && /^Before\./.test(updated), JSON.stringify(updated));
    await page.screenshot({path: '/tmp/ibs-dialog-edit.png'});
    check('no JavaScript errors on the page', errors.length === 0, errors.join(' | '));

    await browser.close();
    const failed = results.filter(r => !r).length;
    console.log(`\nRESULT: ${results.length - failed}/${results.length} browser checks passed`);
    process.exit(failed ? 1 : 0);
})().catch(e => { console.error('SCRIPT ERROR:', e); process.exit(2); });
