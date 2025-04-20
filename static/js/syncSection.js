// syncSection.js

// Stores the current list of keywords
let keywordProfiles = {};
let activeProfile = '';
let keywordsList = [];

function tryLoadKeywords() {
  const saved = localStorage.getItem('job_search_keywords_list');
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

  $('#keywords').keypress(function (e) {
    if (e.which === 13) {
      e.preventDefault();
      addKeyword();
    }
  });

  $(document).on('click', '#keywordsList .btn-close', function () {
    const index = $(this).data('index');
    keywordsList.splice(index, 1);
    renderKeywords();
    persistProfiles(); // 🟢 Updated
  });

  $('#syncJobsBtn').off('click').on('click', function (e) {
    e.preventDefault();
    if (window.APP_CONTEXT?.isDemo) {
      demoSyncJobs();
    } else {
      syncJobs();
    }
  });

  // 🔽 New for profile support
  $('#addProfileBtn').click(addProfile);
  $('#profileDropdown').change(function () {
    activeProfile = $(this).val();
    keywordsList = keywordProfiles[activeProfile] || [];
    renderKeywords();
  });

  // 🔽 Load profiles on startup
  loadProfiles();
}


function populateCategoryDropdown() {
  const categorySelect = $('#category');
  const stored = localStorage.getItem('job_search_category');

  $.getJSON('/static/job_data/adzuna/adzuna_categories.json', function (categories) {
    categorySelect.empty();
    categorySelect.append(`<option value="">All Categories</option>`);
    categories.forEach(cat => {
      const selected = (stored && stored === cat.tag) ? 'selected' : '';
      categorySelect.append(`<option value="${cat.tag}" ${selected}>${cat.label}</option>`);
    });
  }).fail(function () {
    categorySelect.empty().append(`<option value="">[Error loading categories]</option>`);
  });
}

function addKeyword() {
  const keyword = $('#keywords').val().trim();
  if (keyword && !keywordsList.includes(keyword)) {
    keywordsList.push(keyword);
    renderKeywords();

    if (!window.APP_CONTEXT?.isDemo) {
        persistProfiles();
    } else {
      showStatus('Keyword added (demo only — not saved).', 'info');
    }

    $('#keywords').val('');
  } else {
    showStatus('Keyword already in list or empty.', 'warning');
  }
}

function renderKeywords() {
  const $container = $('#keywordsList');
  $container.empty();
  keywordsList.forEach((keyword, index) => {
    const badge = `<div class="badge bg-primary me-2 p-2 d-inline-flex align-items-center">
      ${keyword}
      <button type="button" class="btn-close btn-close-white ms-2" data-index="${index}"></button>
    </div>`;
    $container.append(badge);
  });
  $('#keywordsListData').val(JSON.stringify(keywordsList));
}

function persistKeywords() {
  localStorage.setItem('job_search_keywords_list', JSON.stringify(keywordsList));
  // Only call API in non-demo mode
  if (!window.APP_CONTEXT?.isDemo) {
    $.ajax({
      url: '/api/jobs/save_keywords_list',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({ keywords_list: keywordsList }),
      success: (res) => {
        showStatus(res.message || "Settings saved.", res.success ? "success" : "warning");
      },
      error: (xhr) => {
        const msg = xhr.responseJSON?.error || xhr.statusText || 'Unknown error';
        showStatus(`Error saving settings: ${msg}`, 'danger');
      }
    });
  }
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
    max_days_old: 1,
    remote_only: $('#remote_only').is(':checked'),
    max_pages: parseInt($('#maxPages').val()),
    category: $('#category').val()
  };
  showStatus('Syncing jobs...', 'info');
  $.ajax({
    url: '/api/jobs/sync',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify(payload),
    success: (res) => {
      if (res.success) {
        showStatus("Sync complete. Reloading...", "success");
        setTimeout(() => location.reload(), 3000);
      } else {
        showStatus(`Error: ${res.error}`, "danger");
      }
    },
    error: (xhr) => {
      const msg = xhr.responseJSON?.error || xhr.statusText || 'Unknown error';
      showStatus(`Error: ${msg}`, 'danger');
    }
  });
}

function renderRemoteJobs() {
  const $remoteTbody = $('#remoteJobsTable tbody');
  $remoteTbody.empty();

  Object.entries(window.remoteJobs || {}).forEach(([jobId, job]) => {
    const tr = `
      <tr class="job-row" data-job-id="${jobId}">
        <td>${job.title}</td>
        <td>${job.company}</td>
        <td>${job.location}</td>
        <td>${job.is_remote ? 'Yes' : 'No'}</td>
        <td>${job.posted_date}</td>
        <td>${job.salary_range || 'Not specified'}</td>
        <td>${job.match_percentage || 0}%</td>
        <td>
          <button class="btn btn-sm btn-outline-info toggle-job-details" data-job-id="${jobId}">
            <i class="fas fa-eye"></i> View
          </button>
          <a href="${job.url}" target="_blank" class="btn btn-sm btn-outline-primary">
            <i class="fas fa-external-link-alt"></i> Apply
          </a>
        </td>
      </tr>`;
    $remoteTbody.append(tr);
  });

  if ($.fn.DataTable.isDataTable('#remoteJobsTable')) {
    $('#remoteJobsTable').DataTable().clear().destroy();
  }

  initJobTables();
}


function updateJobsTable() {
  const $tbody = $('#jobsTable tbody');
  $tbody.empty();

  Object.entries(window.allJobs || {}).forEach(([id, job]) => {
    const row = `
      <tr class="job-row" data-job-id="${id}">
        <td>${job.title}</td>
        <td>${job.company}</td>
        <td>${job.location}</td>
        <td>${job.is_remote ? 'Yes' : 'No'}</td>
        <td>${job.posted_date}</td>
        <td>${job.salary_range || 'Not specified'}</td>
        <td>${job.match_percentage || 0}%</td>
        <td>
          <button class="btn btn-sm btn-outline-info toggle-job-details" data-job-id="${id}">
            <i class="fas fa-eye"></i> View
          </button>
          <a href="${job.url}" target="_blank" class="btn btn-sm btn-outline-primary" data-bs-toggle="tooltip" title="Visit Job Listing">
            <i class="fas fa-external-link-alt"></i> Apply
          </a>
        </td>
      </tr>`;
    $tbody.append(row);
  });

  initJobTables();           // reapply DataTables
  handleJobToggleEvents();   // reapply toggle logic
}

function loadProfiles() {
  const storedProfiles = localStorage.getItem('job_search_keyword_profiles');
  if (storedProfiles) {
    try {
      keywordProfiles = JSON.parse(storedProfiles);
    } catch (e) {
      console.error("Failed to parse profiles:", e);
      keywordProfiles = {};
    }
  }

  const storedActive = localStorage.getItem('job_search_active_profile');
  activeProfile = storedActive || Object.keys(keywordProfiles)[0] || 'default';

  if (!keywordProfiles[activeProfile]) {
    keywordProfiles[activeProfile] = [];
  }

  keywordsList = keywordProfiles[activeProfile];
  renderProfileDropdown();
  renderKeywords();
}

function renderProfileDropdown() {
  const $dropdown = $('#profileDropdown');
  $dropdown.empty();

  Object.keys(keywordProfiles).forEach(name => {
    const selected = name === activeProfile ? 'selected' : '';
    $dropdown.append(`<option value="${name}" ${selected}>${name}</option>`);
  });
}

function addProfile() {
  const name = $('#profileName').val().trim();
  if (name && !keywordProfiles[name]) {
    keywordProfiles[name] = [];
    activeProfile = name;
    keywordsList = [];
    persistProfiles();
    renderProfileDropdown();
    renderKeywords();
    showStatus(`Profile '${name}' created.`, 'success');
    $('#profileName').val('');
  } else {
    showStatus('Profile name already exists or is empty.', 'warning');
  }
}

$('#profileDropdown').on('change', function () {
  activeProfile = $(this).val();
  keywordsList = keywordProfiles[activeProfile] || [];
  renderKeywords();
});

function persistProfiles() {
  keywordProfiles[activeProfile] = keywordsList;
  localStorage.setItem('job_search_keyword_profiles', JSON.stringify(keywordProfiles));
  localStorage.setItem('job_search_active_profile', activeProfile);
}


// Save job search parameters
function saveJobSearch() {
    renderKeywords();
    // Get form values
    const keywords = $('#keywords').val();
    const location = $('#location').val();
    const country = $('#country').val();
    const remoteOnly = $('#remote_only').is(':checked') ? '1' : '';
    const maxPages = $('#maxPages').val();
    const category = $('#category').val();
    localStorage.setItem('job_search_category', category);
  
    // Get keywords list from hidden input
    try {
      const keywordsListData = $('#keywordsListData').val();
      if (keywordsListData) {
          keywordsList = JSON.parse(keywordsListData);  // Uses existing global variable
      }
    } catch (e) {
      console.error("Error parsing keywords list in saveJobSearch:", e);
    }
  

    // Store values in session/browser storage for persistence
    localStorage.setItem('job_search_keywords', keywords);
    localStorage.setItem('job_search_keywords_list', JSON.stringify(keywordsList));
    localStorage.setItem('job_search_location', location);
    localStorage.setItem('job_search_country', country);
    localStorage.setItem('job_search_remote_only', remoteOnly);
    localStorage.setItem('job_search_max_pages', maxPages);

    // Show confirmation message
    showStatus(
      window.APP_CONTEXT?.isDemo
        ? '<i class="fas fa-info-circle"></i> Settings accepted (demo mode only).'
        : '<i class="fas fa-check-circle"></i> Settings saved successfully.',
      'success'
    );
}

function loadSavedSearch() {
    $('#keywords').val(localStorage.getItem('job_search_keywords') || '');
    $('#location').val(localStorage.getItem('job_search_location') || '');
    $('#country').val(localStorage.getItem('job_search_country') || '');
    $('#remote_only').prop('checked', localStorage.getItem('job_search_remote_only') === '1');
    $('#maxPages').val(localStorage.getItem('job_search_max_pages') || '');
    $('#category').val(localStorage.getItem('job_search_category') || '');
}

$(document).ready(function () {
  console.log('✅ syncSection.js loaded and DOM ready');
  tryLoadKeywords();
  attachEventHandlers();
  loadSavedSearch(); // Initialize saved search
  renderKeywords(); // ensure visibility
  populateCategoryDropdown(); // Load Adzuna categories
});


