// jobSection.js – Handles cleanup and export buttons in the jobSection

function exportJobs() {
  alert('Export feature to be implemented.');
}

function cleanupOldJobs() {
  if (!confirm('This will delete jobs older than 90 days. Proceed?')) return;

  $('#syncStatus').show().removeClass().addClass('alert alert-info');
  $('#syncStatusText').text('Cleaning up old jobs...');

  $.post('/api/adzuna/cleanup', JSON.stringify({ max_age: 90 }), function (res) {
    if (res.success) {
      $('#syncStatus').removeClass().addClass('alert alert-success');
      $('#syncStatusText').html(`${res.jobs_removed} jobs removed. Reloading...`);
      setTimeout(() => location.reload(), 2000);
    } else {
      $('#syncStatus').removeClass().addClass('alert alert-danger');
      $('#syncStatusText').html(`Error: ${res.error || 'Unknown error'}`);
    }
  }).fail((xhr) => {
    const msg = xhr.responseJSON?.error || xhr.statusText || 'Unknown error';
    $('#syncStatus').removeClass().addClass('alert alert-danger');
    $('#syncStatusText').html(`Error: ${msg}`);
  });
}

// ✅ Attach handlers after DOM is ready
$(document).ready(function () {
  console.log('✅ jobSection.js loaded and DOM ready');
  $('#cleanupBtn').click(cleanupOldJobs);
  $('#exportBtn').click(exportJobs);
});
