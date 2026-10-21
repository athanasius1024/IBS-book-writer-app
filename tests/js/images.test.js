// Unit tests for the crop maths and Markdown helpers behind the Insert image dialog.
// Run with:  node --test tests/js/images.test.js     (pytest runs this too, see tests/test_js.py)
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../app/static/js/images.js');

const bounds = {w: 400, h: 300};
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} is not close to ${b}`);

test('dragging in either direction gives the same rectangle', () => {
    assert.deepEqual(m.rectFromCorners(50, 40, 250, 190, bounds, null), {x: 50, y: 40, w: 200, h: 150});
    assert.deepEqual(m.rectFromCorners(250, 190, 50, 40, bounds, null), {x: 50, y: 40, w: 200, h: 150});
});

test('the rectangle never leaves the picture', () => {
    const r = m.rectFromCorners(300, 200, 999, 999, bounds, null);
    assert.deepEqual(r, {x: 300, y: 200, w: 100, h: 100});
    const s = m.rectFromCorners(100, 100, -50, -50, bounds, null);
    assert.deepEqual(s, {x: 0, y: 0, w: 100, h: 100});
});

test('a locked shape is kept, fits the drag and stays inside the picture', () => {
    const square = m.rectFromCorners(50, 40, 250, 100, bounds, 1);
    near(square.w, square.h); assert.equal(square.w, 60);
    for (const ratio of [4 / 3, 16 / 9, 3 / 4, 1]) {
        for (const [px, py] of [[500, 400], [-50, -50], [10, 290], [390, 5]]) {
            const r = m.rectFromCorners(200, 150, px, py, bounds, ratio);
            near(r.w / r.h, ratio, 1e-9);
            assert.ok(r.x >= -1e-9 && r.y >= -1e-9 && r.x + r.w <= bounds.w + 1e-9 && r.y + r.h <= bounds.h + 1e-9);
        }
    }
});

test('moving clamps to the picture and keeps the size', () => {
    assert.deepEqual(m.moveRect({x: 50, y: 50, w: 100, h: 100}, 500, -500, bounds), {x: 300, y: 0, w: 100, h: 100});
    assert.deepEqual(m.moveRect({x: 50, y: 50, w: 100, h: 100}, 10, 20, bounds), {x: 60, y: 70, w: 100, h: 100});
});

test('resizing a corner keeps the opposite corner fixed', () => {
    const r = {x: 50, y: 50, w: 100, h: 100};
    assert.deepEqual(m.resizeRect(r, 'se', 200, 180, bounds, null), {x: 50, y: 50, w: 150, h: 130});
    assert.deepEqual(m.resizeRect(r, 'nw', 20, 10, bounds, null), {x: 20, y: 10, w: 130, h: 140});
    assert.deepEqual(m.resizeRect(r, 'ne', 220, 20, bounds, null), {x: 50, y: 20, w: 170, h: 130});
    assert.deepEqual(m.resizeRect(r, 'sw', 10, 200, bounds, null), {x: 10, y: 50, w: 140, h: 150});
    // dragging a corner past the opposite one flips the box without losing the fixed corner
    assert.deepEqual(m.resizeRect(r, 'se', 20, 20, bounds, null), {x: 20, y: 20, w: 30, h: 30});
});

test('fractions convert both ways and the crop is formatted compactly', () => {
    const f = m.toFractions({x: 40, y: 30, w: 200, h: 150}, bounds);
    assert.deepEqual(f, {x: 0.1, y: 0.1, w: 0.5, h: 0.5});
    assert.equal(m.formatCrop(f), '0.1,0.1,0.5,0.5');
    assert.deepEqual(m.fromFractions(f, bounds), {x: 40, y: 30, w: 200, h: 150});
    assert.equal(m.formatCrop({x: 0, y: 0, w: 1, h: 0.3333333}), '0,0,1,0.3333');
});

test('only a real crop is worth saving', () => {
    assert.equal(m.isUsableCrop(null), false);
    assert.equal(m.isUsableCrop({x: 0, y: 0, w: 1, h: 1}), false);
    assert.equal(m.isUsableCrop({x: 0.2, y: 0.2, w: 0.005, h: 0.5}), false);
    assert.equal(m.isUsableCrop({x: 0, y: 0, w: 0.5, h: 1}), true);
});

test('the Markdown has only the settings that were changed', () => {
    assert.equal(m.buildMarkdown({id: 7, caption: '', alt: '', crop: null, width: 100, align: 'center'}), '![](image:7)');
    assert.equal(m.buildMarkdown({id: 7, caption: 'A cat', alt: '', crop: null, width: 100, align: 'center'}),
                 '![A cat](image:7 "A cat")');
    assert.equal(m.buildMarkdown({id: 12, caption: 'Cap', alt: 'Desc', crop: {x: 0.1, y: 0.2, w: 0.5, h: 0.5}, width: 60, align: 'left'}),
                 '![Desc](image:12 "Cap"){: data-crop="0.1,0.2,0.5,0.5" data-w="60" .img-left}');
    assert.equal(m.buildMarkdown({id: 3, caption: '', alt: 'x', crop: {x: 0, y: 0, w: 1, h: 1}, width: 100, align: 'right'}),
                 '![x](image:3){: .img-right}');
});

test('text that would break the Markdown is cleaned', () => {
    const md = m.buildMarkdown({id: 1, caption: 'The "big" [one]\nsecond line', alt: '', crop: null, width: 100, align: 'center'});
    assert.equal(md, '![The \'big\' one second line](image:1 "The \'big\' one second line")');
    assert.ok(!/\n/.test(md));
});

test('an existing picture reference is found at the caret and read back exactly', () => {
    const md = m.buildMarkdown({id: 12, caption: 'Cap', alt: 'Desc', crop: {x: 0.1, y: 0.2, w: 0.5, h: 0.4}, width: 60, align: 'right'});
    const text = 'Intro.\n\n' + md + '\n\nOutro.';
    const found = m.parseMarkdownAt(text, 12);
    assert.deepEqual(found, {start: 8, end: 8 + md.length, id: 12, alt: 'Desc', caption: 'Cap',
                             crop: {x: 0.1, y: 0.2, w: 0.5, h: 0.4}, width: 60, align: 'right'});
    assert.equal(text.slice(found.start, found.end), md);
    assert.equal(m.parseMarkdownAt(text, 2), null);
    assert.equal(m.parseMarkdownAt(text, text.length), null);
    assert.equal(m.parseMarkdownAt('![x](image:5)', 0).width, 100);
    assert.equal(m.parseMarkdownAt('![x](image:5)', 0).align, 'center');
});

test('two pictures in one text are told apart by the caret', () => {
    const text = '![a](image:1) and ![b](image:2){: .img-left}';
    assert.equal(m.parseMarkdownAt(text, 3).id, 1);
    assert.equal(m.parseMarkdownAt(text, 30).id, 2);
});

test('a figure is put on its own paragraph; an inline picture is put exactly at the caret', () => {
    assert.equal(m.insertionText('Hello world', '![a](image:1)', ' and more', true), '\n\n![a](image:1)\n\n');
    assert.equal(m.insertionText('Hello\n', '![a](image:1)', '\nmore', true), '\n![a](image:1)\n');
    assert.equal(m.insertionText('', '![a](image:1)', '', true), '![a](image:1)');
    assert.equal(m.insertionText('A\n\n', '![a](image:1)', '\n\nB', true), '![a](image:1)');
    assert.equal(m.insertionText('Hello ', '![a](image:1)', ' there', false), '![a](image:1)');
});
