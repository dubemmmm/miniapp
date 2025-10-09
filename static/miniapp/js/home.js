// home.js

const syncAirtableBtn = document.getElementById('syncAirtableBtn');
const syncStatus = document.getElementById('syncStatus');

if (syncAirtableBtn) {
  syncAirtableBtn.addEventListener('click', async () => {
    syncStatus.textContent = 'Syncing with Airtable...';
    syncAirtableBtn.disabled = true;

    try {
      const response = await fetch(URLS.syncAirtable, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CSRF_TOKEN,
          'Accept': 'application/json',
        },
        body: JSON.stringify({}),
      });

      // Make sure we can parse JSON (even on errors)
      const result = await response.json().catch(() => ({}));

      if (response.ok && result.success) {
        syncStatus.textContent = 'Sync completed successfully! Reloading page...';
        setTimeout(() => window.location.reload(), 1200);
      } else {
        const msg = result.error || `Request failed with status ${response.status}`;
        throw new Error(msg);
      }
    } catch (error) {
      console.error('Error syncing Airtable:', error);
      syncStatus.textContent = `Error: ${error.message}`;
      syncAirtableBtn.disabled = false;
    }
  });
}