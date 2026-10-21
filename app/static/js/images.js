// IBS Book Writer - "Insert image" dialog: pick a picture, crop it, resize it, place it in the text.
//
// The first half is pure maths and text handling (tested with Node, see tests/js/). The second half
// wires it to the dialog in templates/chapters/_image_dialog.html.
(function (root) {
    'use strict';

    // ------------------------------------------------------------------ pure helpers
    function clamp(value, low, high) { return Math.min(high, Math.max(low, value)); }
    function round4(n) { return Math.round(n * 10000) / 10000; }

    var RATIOS = {'free': null, '1:1': 1, '4:3': 4 / 3, '16:9': 16 / 9, '3:4': 3 / 4};

    // The rectangle between an anchor corner and the pointer, kept inside bounds {w, h}. With a ratio
    // (width / height) it is the largest box of that shape that fits the dragged area.
    function rectFromCorners(ax, ay, px, py, bounds, ratio) {
        ax = clamp(ax, 0, bounds.w); ay = clamp(ay, 0, bounds.h);
        px = clamp(px, 0, bounds.w); py = clamp(py, 0, bounds.h);
        var dx = px - ax, dy = py - ay;
        var sx = dx < 0 ? -1 : 1, sy = dy < 0 ? -1 : 1;
        var w = Math.abs(dx), h = Math.abs(dy);
        if (ratio) {
            if (w / ratio > h) { w = h * ratio; } else { h = w / ratio; }
            var maxW = sx < 0 ? ax : bounds.w - ax;
            var maxH = sy < 0 ? ay : bounds.h - ay;
            if (w > maxW) { w = maxW; h = w / ratio; }
            if (h > maxH) { h = maxH; w = h * ratio; }
        }
        return {x: sx < 0 ? ax - w : ax, y: sy < 0 ? ay - h : ay, w: w, h: h};
    }

    function moveRect(rect, dx, dy, bounds) {
        return {x: clamp(rect.x + dx, 0, bounds.w - rect.w), y: clamp(rect.y + dy, 0, bounds.h - rect.h),
                w: rect.w, h: rect.h};
    }

    // Dragging a corner keeps the opposite corner where it is.
    function resizeRect(rect, handle, px, py, bounds, ratio) {
        var ax = handle.indexOf('w') >= 0 ? rect.x + rect.w : rect.x;
        var ay = handle.indexOf('n') >= 0 ? rect.y + rect.h : rect.y;
        return rectFromCorners(ax, ay, px, py, bounds, ratio);
    }

    function toFractions(rect, bounds) {
        return {x: round4(rect.x / bounds.w), y: round4(rect.y / bounds.h),
                w: round4(rect.w / bounds.w), h: round4(rect.h / bounds.h)};
    }

    function fromFractions(f, bounds) {
        return {x: f.x * bounds.w, y: f.y * bounds.h, w: f.w * bounds.w, h: f.h * bounds.h};
    }

    // A crop worth saving: at least 1% each way, and not the whole picture.
    function isUsableCrop(f) {
        if (!f || !(f.w >= 0.01) || !(f.h >= 0.01)) { return false; }
        return !(f.x <= 0.0001 && f.y <= 0.0001 && f.w >= 0.9999 && f.h >= 0.9999);
    }

    function formatCrop(f) {
        return [f.x, f.y, f.w, f.h].map(function (n) { return String(Number(round4(n).toFixed(4))); }).join(',');
    }

    function cleanText(text) {
        return String(text || '').replace(/[\r\n]+/g, ' ').replace(/[\[\]]/g, '').replace(/"/g, "'").trim();
    }

    // ![description](image:12 "Caption"){: data-crop="x,y,w,h" data-w="60" .img-left}
    function buildMarkdown(o) {
        var title = cleanText(o.caption);
        var alt = cleanText(o.alt) || title;
        var md = '![' + alt + '](image:' + o.id + (title ? ' "' + title + '"' : '') + ')';
        var attrs = [];
        if (o.crop && isUsableCrop(o.crop)) { attrs.push('data-crop="' + formatCrop(o.crop) + '"'); }
        if (o.width && o.width >= 10 && o.width < 100) { attrs.push('data-w="' + Math.round(o.width) + '"'); }
        if (o.align === 'left' || o.align === 'right') { attrs.push('.img-' + o.align); }
        return attrs.length ? md + '{: ' + attrs.join(' ') + '}' : md;
    }

    var TOKEN = /!\[([^\]]*)\]\(image:(\d+)(?:\s+"([^"]*)")?\)(\{:[^}]*\})?/g;

    // The picture reference at (or touching) position `caret` of `text`, or null.
    function parseMarkdownAt(text, caret) {
        var match;
        TOKEN.lastIndex = 0;
        while ((match = TOKEN.exec(text)) !== null) {
            var start = match.index, end = start + match[0].length;
            if (caret >= start && caret <= end) {
                var attrs = match[4] || '';
                var crop = /data-crop="([^"]*)"/.exec(attrs);
                var width = /data-w="(\d+)"/.exec(attrs);
                var align = /\.img-(left|right|center)\b/.exec(attrs);
                var parts = crop ? crop[1].split(',').map(Number) : null;
                return {
                    start: start, end: end, id: Number(match[2]), alt: match[1], caption: match[3] || '',
                    crop: parts && parts.length === 4 && parts.every(isFinite)
                        ? {x: parts[0], y: parts[1], w: parts[2], h: parts[3]} : null,
                    width: width ? Number(width[1]) : 100,
                    align: align ? align[1] : 'center'
                };
            }
        }
        return null;
    }

    // Text to insert so a figure stands alone in its paragraph.
    function insertionText(before, markdown, after, ownLine) {
        if (!ownLine) { return markdown; }
        var lead = before.length === 0 || /\n\n$/.test(before) ? '' : (/\n$/.test(before) ? '\n' : '\n\n');
        var tail = after.length === 0 || /^\n\n/.test(after) ? '' : (/^\n/.test(after) ? '\n' : '\n\n');
        return lead + markdown + tail;
    }

    var api = {
        clamp: clamp, rectFromCorners: rectFromCorners, moveRect: moveRect, resizeRect: resizeRect,
        toFractions: toFractions, fromFractions: fromFractions, isUsableCrop: isUsableCrop,
        formatCrop: formatCrop, buildMarkdown: buildMarkdown, parseMarkdownAt: parseMarkdownAt,
        insertionText: insertionText, RATIOS: RATIOS
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
    root.IBSImages = api;
    if (typeof document === 'undefined') { return; }

    // ------------------------------------------------------------------ the dialog
    function $(id) { return document.getElementById(id); }

    document.addEventListener('DOMContentLoaded', function () {
        var modalEl = $('imageModal');
        if (!modalEl || typeof bootstrap === 'undefined') { return; }
        var modal = new bootstrap.Modal(modalEl);
        var stepPick = $('img-step-pick'), stepEdit = $('img-step-edit');
        var grid = $('img-grid'), message = $('img-upload-msg');
        var stageImg = $('img-stage-img'), overlay = $('crop-overlay'), box = $('crop-box');
        var ratioSelect = $('img-ratio'), widthInput = $('img-width'), widthLabel = $('img-width-label');
        var captionInput = $('img-caption'), altInput = $('img-alt'), ownLine = $('img-own-line');
        var preview = $('img-markdown'), backButton = $('img-back'), insertButton = $('img-insert');
        var state = {textarea: null, replace: null, asset: null, rect: null, drag: null, library: [], pendingCrop: null};

        function bounds() { return {w: stageImg.clientWidth, h: stageImg.clientHeight}; }
        function ratio() { return RATIOS[ratioSelect.value] || null; }
        function align() {
            var checked = modalEl.querySelector('input[name="img-align"]:checked');
            return checked ? checked.value : 'center';
        }
        function options() {
            var b = bounds();
            return {
                id: state.asset ? state.asset.id : 0, alt: altInput.value, caption: captionInput.value,
                crop: state.rect && b.w > 0 && b.h > 0 ? toFractions(state.rect, b) : null,
                width: Number(widthInput.value), align: align()
            };
        }

        function refresh() {
            // A saved crop is placed once the picture can be measured: while the dialog is still fading in
            // (or the picture is still loading) its size is 0, which would wipe the crop out.
            var b = bounds();
            if (state.pendingCrop && b.w > 0 && b.h > 0) {
                state.rect = fromFractions(state.pendingCrop, b);
                state.pendingCrop = null;
            }
            widthLabel.textContent = widthInput.value + '%';
            if (state.rect) {
                box.hidden = false;
                box.style.left = state.rect.x + 'px'; box.style.top = state.rect.y + 'px';
                box.style.width = state.rect.w + 'px'; box.style.height = state.rect.h + 'px';
            } else {
                box.hidden = true;
            }
            preview.textContent = state.asset ? buildMarkdown(options()) : '';
            state.lastBounds = bounds();
        }

        function show(step) {
            stepPick.hidden = step !== 'pick';
            stepEdit.hidden = step !== 'edit';
            insertButton.hidden = step !== 'edit';
            backButton.hidden = step !== 'edit';
            $('img-insert-label').textContent = state.replace ? 'Update' : 'Insert';
        }

        function renderGrid() {
            grid.textContent = '';
            if (!state.library.length) {
                message.textContent = 'Your media library is empty. Upload a picture to begin.';
            }
            state.library.forEach(function (asset) {
                var col = document.createElement('div');
                col.className = 'col-6 col-md-3 col-lg-2';
                var button = document.createElement('button');
                button.type = 'button'; button.className = 'img-pick'; button.title = asset.name;
                var img = document.createElement('img'); img.src = asset.url; img.alt = '';
                var label = document.createElement('span'); label.textContent = asset.name;
                button.appendChild(img); button.appendChild(label);
                button.addEventListener('click', function () { choose(asset, null); });
                col.appendChild(button); grid.appendChild(col);
            });
        }

        function loadLibrary() {
            return fetch('/media/library.json', {credentials: 'same-origin'}).then(function (r) { return r.json(); })
                .then(function (data) { state.library = data.assets || []; renderGrid(); });
        }

        // Show the edit step for `asset`, optionally restoring the settings of an existing reference.
        function choose(asset, existing) {
            state.asset = asset; state.rect = null; state.drag = null;
            state.pendingCrop = existing && existing.crop ? existing.crop : null;
            captionInput.value = existing ? existing.caption : '';
            altInput.value = existing && existing.alt !== existing.caption ? existing.alt : '';
            widthInput.value = existing ? existing.width : 100;
            var radio = $('img-align-' + (existing ? existing.align : 'center'));
            if (radio) { radio.checked = true; }
            ratioSelect.value = 'free';
            ownLine.checked = true;
            stageImg.onload = refresh;
            stageImg.src = asset.url;
            show('edit');
            refresh();
        }

        // ---- opening the dialog from a text box
        function openFor(textarea) {
            state.textarea = textarea; state.replace = null; state.asset = null;
            var found = parseMarkdownAt(textarea.value, textarea.selectionStart || 0);
            message.textContent = 'Or choose one from your media library.';
            show('pick');
            modal.show();
            loadLibrary().then(function () {
                if (!found) { return; }
                var asset = state.library.filter(function (a) { return a.id === found.id; })[0];
                if (asset) { state.replace = {start: found.start, end: found.end}; choose(asset, found); }
            });
        }

        document.addEventListener('click', function (event) {
            var button = event.target.closest ? event.target.closest('[data-insert-image]') : null;
            if (!button) { return; }
            var form = button.closest('form') || document;
            var textarea = form.querySelector('textarea[name="content_text"]');
            if (textarea) { openFor(textarea); }
        });

        backButton.addEventListener('click', function () { state.replace = null; show('pick'); });
        modalEl.addEventListener('shown.bs.modal', refresh);          // the dialog is now laid out

        // ---- upload from inside the dialog
        $('img-upload').addEventListener('change', function (event) {
            var files = event.target.files;
            if (!files.length) { return; }
            var body = new FormData();
            Array.prototype.forEach.call(files, function (file) { body.append('image', file); });
            message.textContent = 'Uploading...';
            fetch('/media/upload.json', {method: 'POST', body: body, credentials: 'same-origin',
                                          headers: {'X-CSRFToken': csrfToken()}})
                .then(function (r) { return r.json().then(function (data) { return {ok: r.ok, data: data}; }); })
                .then(function (result) {
                    event.target.value = '';
                    var errors = (result.data.errors || []).join(' ');
                    var created = result.data.assets || [];
                    message.textContent = errors || (created.length + ' uploaded.');
                    return loadLibrary().then(function () {
                        if (created.length === 1) {
                            var asset = state.library.filter(function (a) { return a.id === created[0].id; })[0];
                            if (asset) { choose(asset, null); }
                        }
                    });
                })
                .catch(function () { message.textContent = 'The upload failed. Please try again.'; });
        });

        // ---- the crop rectangle: drag to draw, drag inside to move, drag a corner to resize
        function pointIn(event) {
            var r = stageImg.getBoundingClientRect();
            return {x: clamp(event.clientX - r.left, 0, r.width), y: clamp(event.clientY - r.top, 0, r.height)};
        }
        function inside(p, rect) { return p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h; }

        overlay.addEventListener('pointerdown', function (event) {
            var p = pointIn(event), handle = event.target.getAttribute ? event.target.getAttribute('data-h') : null;
            if (handle && state.rect) { state.drag = {type: 'resize', handle: handle}; }
            else if (state.rect && inside(p, state.rect)) { state.drag = {type: 'move', last: p}; }
            else { state.drag = {type: 'new', anchor: p}; state.rect = null; }
            overlay.setPointerCapture(event.pointerId);
            event.preventDefault();
        });
        overlay.addEventListener('pointermove', function (event) {
            if (!state.drag) { return; }
            var p = pointIn(event), b = bounds();
            if (state.drag.type === 'new') {
                state.rect = rectFromCorners(state.drag.anchor.x, state.drag.anchor.y, p.x, p.y, b, ratio());
            } else if (state.drag.type === 'move') {
                state.rect = moveRect(state.rect, p.x - state.drag.last.x, p.y - state.drag.last.y, b);
                state.drag.last = p;
            } else {
                state.rect = resizeRect(state.rect, state.drag.handle, p.x, p.y, b, ratio());
            }
            refresh();
        });
        function endDrag() {
            if (!state.drag) { return; }
            if (state.rect && (state.rect.w < 8 || state.rect.h < 8)) { state.rect = null; }   // a click clears it
            state.drag = null;
            refresh();
        }
        overlay.addEventListener('pointerup', endDrag);
        overlay.addEventListener('pointercancel', endDrag);

        ratioSelect.addEventListener('change', function () {
            if (state.rect && ratio()) {
                state.rect = rectFromCorners(state.rect.x, state.rect.y, state.rect.x + state.rect.w,
                                             state.rect.y + state.rect.h, bounds(), ratio());
            }
            refresh();
        });
        $('img-clear-crop').addEventListener('click', function () { state.rect = null; refresh(); });
        [widthInput, captionInput, altInput].forEach(function (el) { el.addEventListener('input', refresh); });
        modalEl.querySelectorAll('input[name="img-align"]').forEach(function (el) { el.addEventListener('change', refresh); });
        window.addEventListener('resize', function () {
            if (state.rect && state.lastBounds) {
                state.rect = fromFractions(toFractions(state.rect, state.lastBounds), bounds());
            }
            state.lastBounds = bounds();
            refresh();
        });

        // ---- put the Markdown in the text box
        insertButton.addEventListener('click', function () {
            if (!state.asset || !state.textarea) { return; }
            var markdown = buildMarkdown(options()), area = state.textarea, text = area.value, from, to, insert;
            if (state.replace) {
                from = state.replace.start; to = state.replace.end; insert = markdown;
            } else {
                from = area.selectionStart || 0; to = area.selectionEnd || from;
                insert = insertionText(text.slice(0, from), markdown, text.slice(to), ownLine.checked);
            }
            area.value = text.slice(0, from) + insert + text.slice(to);
            var caret = from + insert.length;
            area.focus(); area.setSelectionRange(caret, caret);
            area.dispatchEvent(new Event('input', {bubbles: true}));
            modal.hide();
        });
    });
}(typeof window !== 'undefined' ? window : globalThis));
