// IBS Book Writer - UI helpers.

// ---- Flash alerts: auto-dismiss after 6 seconds ----
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.container.mt-3 .alert').forEach(function (alert) {
        setTimeout(function () {
            bootstrap.Alert.getOrCreateInstance(alert).close();
        }, 6000);
    });
});

// ---- "Add content" form: show only the selected block type's fields ----
function syncBlockType(form) {
    const select = form.querySelector('#block-type-select');
    if (!select) return;
    form.querySelectorAll('fieldset.block-fields').forEach(function (group) {
        const active = group.dataset.type === select.value;
        group.disabled = !active;   // disabled fields are not submitted
        group.hidden = !active;
    });
}

document.addEventListener('change', function (event) {
    if (event.target.id === 'block-type-select') syncBlockType(event.target.form);
});

// Reset "add" forms after a successful HTMX request.
document.addEventListener('htmx:afterRequest', function (event) {
    const el = event.detail.elt;
    if (event.detail.successful && el && el.hasAttribute && el.hasAttribute('data-reset-on-success')) {
        el.reset();
        syncBlockType(el);
        const empty = document.getElementById('no-blocks');
        if (empty) empty.remove();
    }
});

// ---- Server-side errors for HTMX calls ----
document.addEventListener('htmx:responseError', function (event) {
    const xhr = event.detail.xhr;
    const text = (xhr.responseText || '').trim();
    const plain = text && text.length < 300 && text.charAt(0) !== '<';
    let message = 'Something went wrong (' + xhr.status + ').';
    if ((xhr.status === 409 || xhr.status === 400) && plain) message = text;
    else if (xhr.status === 400) message = 'Please check what you entered and try again.';
    else if (xhr.status === 401 || xhr.status === 302) message = 'Your session expired. Please log in again.';
    alert(message);
});

// ---- Undo after deleting a content block (button or Ctrl+Z) ----
let undoState = null;     // {url, fields}
let pendingDelete = null; // captured just before the DELETE request goes out
let undoTimer = null;

function csrfToken() {
    try {
        return JSON.parse(document.body.getAttribute('hx-headers'))['X-CSRFToken'];
    } catch (e) {
        return '';
    }
}

function clearUndo() {
    undoState = null;
    clearTimeout(undoTimer);
    const toast = document.getElementById('undo-toast');
    if (toast) toast.remove();
}

function showUndo(state) {
    clearUndo();
    undoState = state;
    const toast = document.createElement('div');
    toast.id = 'undo-toast';
    toast.className = 'alert alert-warning alert-dismissible fade show position-fixed bottom-0 end-0 m-3 undo-toast';
    toast.innerHTML =
        '<strong>Content block deleted</strong>' +
        '<button type="button" class="btn btn-sm btn-primary ms-3" id="undo-button">' +
        '<i class="bi bi-arrow-counterclockwise"></i> Undo (Ctrl+Z)</button>' +
        '<button type="button" class="btn-close" aria-label="Close"></button>';
    document.body.appendChild(toast);
    toast.querySelector('#undo-button').addEventListener('click', undoDelete);
    toast.querySelector('.btn-close').addEventListener('click', clearUndo);
    undoTimer = setTimeout(clearUndo, 10000);
}

function undoDelete() {
    if (!undoState) return;
    const state = undoState;
    const body = new FormData();
    Object.keys(state.fields).forEach(function (key) {
        const value = state.fields[key];
        if (value !== '' && value !== null && value !== undefined) body.append(key, value);
    });
    fetch(state.url, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken(), 'HX-Request': 'true'},
        body: body,
    }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        clearUndo();
        window.location.reload();  // re-render so the block returns to its old position
    }).catch(function () {
        alert('Could not restore the block.');
    });
}

document.addEventListener('htmx:beforeRequest', function (event) {
    const elt = event.detail.elt;
    pendingDelete = null;
    if (elt && elt.classList && elt.classList.contains('btn-delete-block')) {
        const card = elt.closest('.content-block');
        try {
            pendingDelete = {elt: elt, state: JSON.parse(card.dataset.restore)};
        } catch (e) {
            pendingDelete = null;
        }
    }
});

document.addEventListener('htmx:afterRequest', function (event) {
    if (pendingDelete && event.detail.elt === pendingDelete.elt) {
        if (event.detail.successful) showUndo(pendingDelete.state);
        pendingDelete = null;
    }
});

document.addEventListener('keydown', function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z' || !undoState) return;
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (['INPUT', 'TEXTAREA', 'SELECT'].indexOf(tag) !== -1) return;  // keep native text undo
    event.preventDefault();
    undoDelete();
});
