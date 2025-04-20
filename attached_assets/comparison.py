# Ol demoMode.js
$(document).ready(function () {
  const isDemo = window.APP_CONTEXT?.isDemo;
  if (!isDemo) return;

  function showStatus(message, type = 'info') {
    $('#syncStatus').show()
      .removeClass('alert-success alert-danger alert-info alert-warning')
      .addClass(`alert-${type}`);
    $('#syncStatusText').html(message);
    setTimeout(() => $('#syncStatus').fadeOut(), 3000);
  }

  function addDemoResume() {
    const timestamp = new Date().toISOString().split('T')[0];
    const randomName = `Resume_${Math.floor(Math.random() * 10000)}.pdf`;
    const html = `
      <div class="list-group-item d-flex justify-content-between align-items-center">
        <a href="#" class="resume-select-link text-decoration-none">
          <div>
            <span>${randomName}</span>
            <small class="d-block text-muted">${timestamp}</small>
          </div>
        </a>
        <button type="button" class="btn btn-sm btn-danger delete-resume">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    `;
    $('#resumeList').prepend(html);
    $('#noResumesAlert').hide();
    showStatus("Resume added successfully (demo)", 'success');
  }

  function addDemoJobs() {
    const baseJobs = Object.values(window.allJobs || {});
    if (!baseJobs.length) return;

    const newJobs = [];
    const now = new Date();

    for (let i = 0; i < 7; i++) {
      const job = { ...baseJobs[Math.floor(Math.random() * baseJobs.length)] };
      job.title += " (Demo)";
      job.posted_date = new Date(now - Math.random() * 86400000).toISOString().split("T")[0];
      job.match_percentage = Math.floor(Math.random() * 40) + 60;
      newJobs.push(job);
    }

    newJobs.forEach((job) => {
      const row = `
        <tr class="job-row">
          <td>${job.title}</td>
          <td>${job.company}</td>
          <td>${job.location}</td>
          <td>${job.is_remote ? "Yes" : "No"}</td>
          <td>${job.posted_date}</td>
          <td>${job.salary_range || 'Not specified'}</td>
          <td>${job.match_percentage}%</td>
          <td>
            <button class="btn btn-sm btn-outline-info toggle-job-details">
              <i class="fas fa-eye"></i> View
            </button>
            <a href="${job.url}" target="_blank" class="btn btn-sm btn-outline-primary">
              <i class="fas fa-external-link-alt"></i> Apply
            </a>
          </td>
        </tr>`;
      $('#jobsTable tbody').prepend(row);
    });

    showStatus("Synced 7 sample jobs using default settings (demo)", 'success');
  }

  // ✅ Intercept Resume Upload Form
  $('#resume').closest('form').off('submit').on('submit', function (e) {
    e.preventDefault();
    addDemoResume();
  });

  // ✅ Intercept Sync Button
  $('#syncJobsBtn').off('click').on('click', function (e) {
    e.preventDefault();
    addDemoJobs();
  });

  // ✅ Enable everything for appearance
  $('#resume').prop('disabled', false);
  $('#jobSearchForm :input').prop('disabled', false);
  $('.delete-batch, .toggle-job-details').prop('disabled', false);
  $('.btn').removeClass('disabled');

  // ✅ Resume deletion simulation
  $(document).on('click', '.delete-resume', function () {
    $(this).closest('.list-group-item').remove();
    showStatus("Resume deleted (demo)", 'success');
  });
});





# Ol syncSection.js

function demoSyncJobs() {
  $.getJSON('/static/job_data/adzuna/index.json', function (index) {
    const allBatchIds = Object.keys(index.batches || {});
    const selectedJobs = [];
    const targetCount = Math.floor(Math.random() * 4) + 6;

    function fetchFromRandomBatch(attempts = 0) {
      if (selectedJobs.length >= targetCount || attempts >= 10) {
        const demoBatch = {};
        const timestamp = Date.now();
        selectedJobs.forEach((job, i) => {
          const jobId = `demo-${timestamp}-${i}`;
          job.posted_date = new Date(Date.now() - Math.random() * 864000000).toISOString();
          job.match_percentage = Math.floor(Math.random() * 21) + 70;
          demoBatch[jobId] = job;
        });

        renderDemoJobs(demoBatch);
        showStatus("Sync complete. Demo jobs added for this session.", "info");
        return;
      }

      const batchId = allBatchIds[Math.floor(Math.random() * allBatchIds.length)];
      $.getJSON(`/static/job_data/adzuna/batch_${batchId}.json`, function (batchJobs) {
        const sample = batchJobs.filter(j => j && typeof j === 'object');
        const randomJob = sample[Math.floor(Math.random() * sample.length)];
        if (randomJob) selectedJobs.push(randomJob);
        fetchFromRandomBatch(attempts + 1);
      }).fail(() => fetchFromRandomBatch(attempts + 1));
    }

    fetchFromRandomBatch();
  });
}

function renderDemoJobs(demoJobs) {
  // Merge into allJobs so that detail toggles and job lookups still work
  window.allJobs = {
    ...(window.allJobs || {}),
    ...demoJobs
  };

  // Also refresh remoteJobs
  window.remoteJobs = Object.fromEntries(
    Object.entries(window.allJobs).filter(([_, job]) => job.is_remote)
  );

  const $tbody = $('#jobsTable tbody');
  $tbody.empty();

  Object.entries(window.allJobs).forEach(([jobId, job]) => {
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
    $tbody.append(tr);
  });