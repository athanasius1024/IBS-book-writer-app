// IBS Book Writer - small UI helpers.

// Auto-dismiss flash alerts after 6 seconds (not the persistent in-page ones).
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('main .container > .alert, .container.mt-3 .alert').forEach(function (alert) {
        setTimeout(function () {
            bootstrap.Alert.getOrCreateInstance(alert).close();
        }, 6000);
    });
});

// Reset "add" forms after a successful HTMX request.
document.addEventListener('htmx:afterRequest', function (event) {
    const el = event.detail.elt;
    if (event.detail.successful && el && el.hasAttribute && el.hasAttribute('data-reset-on-success')) {
        el.reset();
        const empty = document.getElementById('no-blocks');
        if (empty) empty.remove();
    }
});

// Surface server-side errors for HTMX calls (e.g. 409 "book is completed").
document.addEventListener('htmx:responseError', function (event) {
    const xhr = event.detail.xhr;
    const text = (xhr.responseText || '').trim();
    let message = 'Something went wrong (' + xhr.status + ').';
    if (xhr.status === 409 && text) message = text;
    else if (xhr.status === 400) message = 'Please check what you entered and try again.';
    else if (xhr.status === 401 || xhr.status === 302) message = 'Your session expired. Please log in again.';
    alert(message);
});

// Subtle dimming while an HTMX request is in flight.
document.addEventListener('htmx:beforeRequest', function (event) {
    if (event.detail.target) event.detail.target.style.opacity = '0.6';
});
document.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail.target) event.detail.target.style.opacity = '1';
});
