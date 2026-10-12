// Custom JavaScript for Terran Society Book Manager

// Initialize Bootstrap tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Enable all tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
});

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Confirm delete actions
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item?');
}

// HTMX event handlers
document.addEventListener('htmx:afterSwap', function(event) {
    // Add a brief highlight effect to newly added elements
    if (event.detail.target.id === 'duties-list') {
        const newElements = event.detail.target.querySelectorAll('.card');
        if (newElements.length > 0) {
            const lastElement = newElements[newElements.length - 1];
            lastElement.style.backgroundColor = '#d4edda';
            setTimeout(function() {
                lastElement.style.transition = 'background-color 0.5s';
                lastElement.style.backgroundColor = '';
            }, 500);
        }
    }
});

// Show loading spinner during HTMX requests
document.addEventListener('htmx:beforeRequest', function(event) {
    const target = event.detail.target;
    if (target) {
        target.style.opacity = '0.6';
    }
});

document.addEventListener('htmx:afterRequest', function(event) {
    const target = event.detail.target;
    if (target) {
        target.style.opacity = '1';
    }
});

// Form validation helper
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(function(field) {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });
    
    return isValid;
}

// Add event listener to remove validation error on input
document.addEventListener('DOMContentLoaded', function() {
    const inputs = document.querySelectorAll('input, textarea, select');
    inputs.forEach(function(input) {
        input.addEventListener('input', function() {
            this.classList.remove('is-invalid');
        });
    });
});

// Markdown preview toggle (for future enhancement)
function toggleMarkdownPreview(textareaId, previewId) {
    const textarea = document.getElementById(textareaId);
    const preview = document.getElementById(previewId);
    
    if (!textarea || !preview) return;
    
    // Simple markdown rendering (you can enhance this with a library like marked.js)
    const text = textarea.value;
    const html = text
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        .replace(/\n/gim, '<br>');
    
    preview.innerHTML = html;
}

// Smooth scroll to top
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

// Add scroll-to-top button if page is long
document.addEventListener('DOMContentLoaded', function() {
    if (document.body.scrollHeight > window.innerHeight * 2) {
        const button = document.createElement('button');
        button.innerHTML = '<i class="bi bi-arrow-up"></i>';
        button.className = 'btn btn-primary position-fixed bottom-0 end-0 m-3';
        button.style.display = 'none';
        button.onclick = scrollToTop;
        document.body.appendChild(button);
        
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                button.style.display = 'block';
            } else {
                button.style.display = 'none';
            }
        });
    }
});

// Filter table rows (for future enhancement)
function filterTable(inputId, tableId) {
    const input = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    
    if (!input || !table) return;
    
    const filter = input.value.toUpperCase();
    const rows = table.getElementsByTagName('tr');
    
    for (let i = 1; i < rows.length; i++) {
        const cells = rows[i].getElementsByTagName('td');
        let found = false;
        
        for (let j = 0; j < cells.length; j++) {
            if (cells[j].textContent.toUpperCase().indexOf(filter) > -1) {
                found = true;
                break;
            }
        }
        
        rows[i].style.display = found ? '' : 'none';
    }
}

// Copy to clipboard helper
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        // Show success toast or notification
        console.log('Copied to clipboard:', text);
    }).catch(function(err) {
        console.error('Failed to copy:', err);
    });
}

// Export data as JSON (for future enhancement)
function exportAsJSON(data, filename) {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'export.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// Print helper
function printElement(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    const printWindow = window.open('', '', 'height=600,width=800');
    printWindow.document.write('<html><head><title>Print</title>');
    printWindow.document.write('<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">');
    printWindow.document.write('</head><body>');
    printWindow.document.write(element.innerHTML);
    printWindow.document.write('</body></html>');
    printWindow.document.close();
    printWindow.print();
}

// Toggle duty edit mode
function toggleDutyEdit(id) {
    const viewDiv = document.getElementById(`duty-view-${id}`);
    const editDiv = document.getElementById(`duty-edit-${id}`);
    
    if (viewDiv.style.display === 'none') {
        viewDiv.style.display = 'block';
        editDiv.style.display = 'none';
    } else {
        viewDiv.style.display = 'none';
        editDiv.style.display = 'block';
    }
}

// Toggle explanation edit mode
function toggleRoleExplainEdit(id) {
    const viewDiv = document.getElementById(`role-explain-view-${id}`);
    const editDiv = document.getElementById(`role-explain-edit-${id}`);
    
    if (viewDiv.style.display === 'none') {
        viewDiv.style.display = 'block';
        editDiv.style.display = 'none';
    } else {
        viewDiv.style.display = 'none';
        editDiv.style.display = 'block';
    }
}

function toggleInstitutionExplainEdit(id) {
    const viewDiv = document.getElementById(`institution-explain-view-${id}`);
    const editDiv = document.getElementById(`institution-explain-edit-${id}`);
    
    if (viewDiv.style.display === 'none') {
        viewDiv.style.display = 'block';
        editDiv.style.display = 'none';
    } else {
        viewDiv.style.display = 'none';
        editDiv.style.display = 'block';
    }
}

function toggleTierExplainEdit(id) {
    const viewDiv = document.getElementById(`tier-explain-view-${id}`);
    const editDiv = document.getElementById(`tier-explain-edit-${id}`);
    
    if (viewDiv.style.display === 'none') {
        viewDiv.style.display = 'block';
        editDiv.style.display = 'none';
    } else {
        viewDiv.style.display = 'none';
        editDiv.style.display = 'block';
    }
}

// Undo functionality for deleted items (duties and explanations)
let deletedItem = null;
let undoTimeout = null;

// Save deleted duty for undo
function saveDeletedDuty(event, id, header, desc, sortOrder, roleId) {
    // Only save if the delete was successful
    if (event.detail.successful) {
        clearUndoNotification();
        
        deletedItem = {
            itemType: 'duty',
            id: id,
            header: header,
            desc: desc,
            sortOrder: sortOrder,
            roleId: roleId
        };
        
        showUndoNotification('duty');
        
        // Clear undo data after 10 seconds
        undoTimeout = setTimeout(() => {
            deletedItem = null;
            clearUndoNotification();
        }, 10000);
    }
}

function saveDeletedExplanation(event, type, id, header, desc, sortOrder, parentId) {
    // Only save if the delete was successful
    if (event.detail.successful) {
        clearUndoNotification();
        
        // Determine the parent ID field name
        let parentIdField;
        
        if (type === 'role') {
            parentIdField = 'role_id';
        } else if (type === 'institution') {
            parentIdField = 'institution_id';
        } else if (type === 'tier') {
            parentIdField = 'tier_id';
        }
        
        deletedItem = {
            itemType: 'explanation',
            type: type,
            id: id,
            header: header,
            desc: desc,
            sortOrder: sortOrder,
            parentIdField: parentIdField,
            parentId: parentId
        };
        
        showUndoNotification('explanation');
        
        // Clear undo data after 10 seconds
        undoTimeout = setTimeout(() => {
            deletedItem = null;
            clearUndoNotification();
        }, 10000);
    }
}

function showUndoNotification(itemType) {
    // Remove any existing notification
    clearUndoNotification();
    
    const message = itemType === 'duty' ? 'Duty deleted' : 'Explanation deleted';
    const notification = document.createElement('div');
    notification.id = 'undo-notification';
    notification.className = 'alert alert-warning alert-dismissible fade show position-fixed bottom-0 end-0 m-3';
    notification.style.zIndex = '9999';
    notification.innerHTML = `
        <strong>${message}</strong>
        <button type="button" class="btn btn-sm btn-primary ms-3" onclick="undoDelete()">
            <i class="bi bi-arrow-counterclockwise"></i> Undo (Ctrl+Z)
        </button>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
}

function clearUndoNotification() {
    const notification = document.getElementById('undo-notification');
    if (notification) {
        notification.remove();
    }
}

function undoDelete() {
    if (!deletedItem) return;
    
    if (deletedItem.itemType === 'duty') {
        // Restore duty
        const { header, desc, sortOrder, roleId } = deletedItem;
        
        const formData = new FormData();
        formData.append('role_id', roleId);
        formData.append('duty_header', header);
        formData.append('duty_desc', desc);
        formData.append('sort_order', sortOrder);
        
        fetch('/duties/restore', {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(html => {
            const listElement = document.querySelector('#duties-list');
            if (listElement) {
                listElement.insertAdjacentHTML('beforeend', html);
            }
            
            deletedItem = null;
            clearTimeout(undoTimeout);
            clearUndoNotification();
            
            showSuccessMessage('Duty restored!');
        })
        .catch(error => {
            console.error('Error restoring duty:', error);
            alert('Failed to restore duty');
        });
    } else if (deletedItem.itemType === 'explanation') {
        // Restore explanation
        const { type, header, desc, sortOrder, parentIdField, parentId } = deletedItem;
        
        // Determine restore URL and list target
        let restoreUrl, targetList;
        if (type === 'role') {
            restoreUrl = '/role-explains/restore';
            targetList = '#role-explains-list';
        } else if (type === 'institution') {
            restoreUrl = '/institution-explains/restore';
            targetList = '#institution-explains-list';
        } else if (type === 'tier') {
            restoreUrl = '/tier-explains/restore';
            targetList = '#tier-explains-list';
        }
        
        const formData = new FormData();
        formData.append(parentIdField, parentId);
        formData.append('explain_header', header);
        formData.append('explain_desc', desc);
        formData.append('sort_order', sortOrder);
        
        fetch(restoreUrl, {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(html => {
            const listElement = document.querySelector(targetList);
            if (listElement) {
                listElement.insertAdjacentHTML('beforeend', html);
            }
            
            deletedItem = null;
            clearTimeout(undoTimeout);
            clearUndoNotification();
            
            showSuccessMessage('Explanation restored!');
        })
        .catch(error => {
            console.error('Error restoring explanation:', error);
            alert('Failed to restore explanation');
        });
    }
}

function showSuccessMessage(message) {
    const successAlert = document.createElement('div');
    successAlert.className = 'alert alert-success alert-dismissible fade show position-fixed top-0 end-0 m-3';
    successAlert.style.zIndex = '9999';
    successAlert.innerHTML = `
        <strong>${message}</strong>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(successAlert);
    setTimeout(() => successAlert.remove(), 3000);
}

// Keyboard shortcut for undo (Ctrl+Z)
document.addEventListener('keydown', function(event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'z' && deletedItem) {
        event.preventDefault();
        undoDelete();
    }
});

console.log('Terran Society Book Manager loaded successfully');
