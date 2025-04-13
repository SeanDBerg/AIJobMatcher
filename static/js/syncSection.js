// syncSection.js

// Stores the current list of keywords
let keywordsList = [];

function tryLoadKeywords() {
  const saved = $('#keywordsListData').val();
  if (saved) {
    try {
      keywordsList = JSON.parse(saved);
      renderKeywords();
    } catch (e) {
      console.error("Error parsing stored keywords:", e);
    }
  }
}

function attachEventHandlers() {
  $('#addKeywordBtn').click(addKeyword);

  $('#keywords').keypress(function(e) {
    if (e.which === 13) {
      e.preventDefault();
      addKeyword();
    }
  });

  $(document).on('click', '#keywordsList .btn-close', function () {
    const index = $(this).data('index');
    keywordsList.splice(index, 1);
    renderKeywords();
    persistKeywords();
  });

  $('#syncJobsBtn').click(syncJobs);
  $('#cleanupBtn').click(cleanupOldJobs);
}

function addKeyword() {
  const keyword = $('#keywords').val().trim();
  if (keyword && !keywordsList.includes(keyword)) {
    keywordsList.push(keyword);
    renderKeywords();
    persistKeywords();
    $('#keywords').val('');
  } else {
    showStatus('Keyword already in list.', 'warning');
  }
}

function renderKeywords() {
  const $container = $('#keywordsList');
  $container.empty();
  keywordsList.forEach((keyword, index) => {
    const badge = `<div class="badge bg-primary me-2 mb-2 p-2">
      ${keyword}
      <button type="button" class="btn-close btn-close-white ms-2" data-index="${index}"></button>
    </div>`;
    $container.append(badge);
  });
  $('#keywordsListData').val(JSON.stringify(keywordsList));
}

function persistKeywords() {
  localStorage.setItem('job_search_keywords_list', JSON.stringify(keywordsList));
  $.post('/api/save_keywords_list', JSON.stringify({ keywords_list: keywordsList }), 'json');
}

function showStatus(message, type = 'info') {
  $('#syncStatus').show()
    .removeClass('alert-success alert-danger alert-info alert-warning')
    .addClass(`alert-${type}`);
  $('#syncStatusText').html(message);
  setTimeout(() => $('#syncStatus').fadeOut(), 3000);
}

function syncJobs() {
  const payload = {
    keywords: $('#keywords').val(),
    keywords_list: keywordsList,
    location: $('#location').val(),
    country: $('#country').val(),
    max_days_old: parseInt($('#max_days_old').val()),
    remote_only: $('#remote_only').is(':checked'),
    max_pages: parseInt($('#maxPages').val())
  };
  showStatus('Syncing jobs...', 'info');
  $.ajax({
    url: '/api/jobs/sync',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify(payload),
    success: (res) => {
      if (res.success) {
        showStatus('Sync complete. Reloading...', 'success');
        setTimeout(() => location.reload(), 3000);
      } else {
        showStatus(`Error: ${res.error}`, 'danger');
      }
    },
    error: (xhr) => {
      const msg = xhr.responseJSON?.error || xhr.statusText || 'Unknown error';
      showStatus(`Error: ${msg}`, 'danger');
    }
  });
}

// Save job search parameters
function saveJobSearch() {
    // Get form values
    const keywords = $('#keywords').val();
    const location = $('#location').val();
    const country = $('#country').val();
    const maxDaysOld = $('#max_days_old').val();
    const remoteOnly = $('#remote_only').is(':checked') ? '1' : '';
    const maxPages = $('#maxPages').val();

    // Get keywords list from hidden input
    let keywordsList = [];
    try {
        const keywordsListData = $('#keywordsListData').val();
        if (keywordsListData) {
            keywordsList = JSON.parse(keywordsListData);
        }
    } catch (e) {
        console.error("Error parsing keywords list in saveJobSearch:", e);
    }

    // Store values in session/browser storage for persistence
    localStorage.setItem('job_search_keywords', keywords);
    localStorage.setItem('job_search_keywords_list', JSON.stringify(keywordsList));
    localStorage.setItem('job_search_location', location);
    localStorage.setItem('job_search_country', country);
    localStorage.setItem('job_search_max_days_old', maxDaysOld);
    localStorage.setItem('job_search_remote_only', remoteOnly);
    localStorage.setItem('job_search_max_pages', maxPages);

    // Show confirmation message
    $('#syncStatus').show().removeClass('alert-info alert-danger').addClass('alert-success');
    $('#syncStatusText').html('<i class="fas fa-check-circle"></i> Settings saved successfully.');

    // Auto-hide after a few seconds
    setTimeout(function() {
        $('#syncStatus').fadeOut();
    }, 3000);
}

function loadSavedSearch() {
    $('#keywords').val(localStorage.getItem('job_search_keywords') || '');
    $('#location').val(localStorage.getItem('job_search_location') || '');
    $('#country').val(localStorage.getItem('job_search_country') || '');
    $('#max_days_old').val(localStorage.getItem('job_search_max_days_old') || '');
    $('#remote_only').prop('checked', localStorage.getItem('job_search_remote_only') === '1');
    $('#maxPages').val(localStorage.getItem('job_search_max_pages') || '');
}

$(document).ready(function () {
  tryLoadKeywords();
  attachEventHandlers();
  renderKeywords(); // ensure visibility
});
