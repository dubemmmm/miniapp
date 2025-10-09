// miniapp/js/manage_shared_lists.js

// Toast notification system
class ToastManager {
    static show(message, type = 'success') {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        const toastIcon = document.getElementById('toastIcon');
        
        // Set icon based on type
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            info: 'fas fa-info-circle'
        };
        
        toast.className = `toast ${type}`;
        toastMessage.textContent = message;
        toastIcon.className = icons[type] || icons.success;
        
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
}

// Copy to clipboard functionality
async function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    const button = event.target.closest('button');
    const originalHTML = button.innerHTML;
    
    try {
        // Modern clipboard API
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(element.value);
        } else {
            // Fallback for older browsers or non-HTTPS
            element.select();
            element.setSelectionRange(0, 99999);
            document.execCommand('copy');
        }
        
        // Visual feedback
        button.innerHTML = '<i class="fas fa-check"></i>';
        button.classList.remove('btn-primary');
        button.classList.add('btn-success');
        
        ToastManager.show('URL copied to clipboard', 'success');
        
        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('btn-success');
            button.classList.add('btn-primary');
        }, 2000);
        
    } catch (err) {
        console.error('Failed to copy: ', err);
        ToastManager.show('Failed to copy URL. Please copy manually.', 'error');
    }
}

// Toggle list status
async function toggleListStatus(listId, isCurrentlyActive) {
    const action = isCurrentlyActive ? 'deactivate' : 'activate';
    const button = document.getElementById(`toggleBtn${listId}`);
    
    if (!confirm(`Are you sure you want to ${action} this shared list?`)) {
        return;
    }
    
    const originalHTML = button.innerHTML;
    
    try {
        // Show loading state
        button.disabled = true;
        button.innerHTML = '<div class="loading-spinner"></div>';
        
        const response = await fetch(`/manage-shares/toggle/${listId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
                'Accept': 'application/json'
            },
            body: JSON.stringify({ active: !isCurrentlyActive })
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        ToastManager.show(data.message || `List ${action}d successfully`, 'success');
        
        // Reload page to reflect changes
        setTimeout(() => location.reload(), 1000);
        
    } catch (error) {
        console.error('Toggle error:', error);
        ToastManager.show(`Failed to ${action} list: ${error.message}`, 'error');
        
        // Reset button state
        button.disabled = false;
        button.innerHTML = originalHTML;
    }
}

// Delete list
async function deleteList(listId) {
    if (!confirm('Are you sure you want to delete this shared list? This action cannot be undone.')) {
        return;
    }
    
    const button = document.getElementById(`deleteBtn${listId}`);
    const originalHTML = button.innerHTML;
    
    try {
        // Show loading state
        button.disabled = true;
        button.innerHTML = '<div class="loading-spinner"></div>';
        
        const response = await fetch(`/manage-shares/delete/${listId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        ToastManager.show(data.message || 'List deleted successfully', 'success');
        
        // Reload page to reflect changes
        setTimeout(() => location.reload(), 1000);
        
    } catch (error) {
        console.error('Delete error:', error);
        ToastManager.show(`Failed to delete list: ${error.message}`, 'error');
        
        // Reset button state
        button.disabled = false;
        button.innerHTML = originalHTML;
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Add any initialization code here
    console.log('Shared Lists Management page loaded');
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
            e.preventDefault();
            location.reload();
        }
    });
});

// Handle network errors globally
window.addEventListener('online', () => {
    ToastManager.show('Connection restored', 'success');
});

window.addEventListener('offline', () => {
    ToastManager.show('Connection lost. Some features may not work.', 'error');
});