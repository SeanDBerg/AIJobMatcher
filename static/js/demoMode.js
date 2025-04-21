// demoMode.js - Handles static demo mode job injection and table refresh

(function () {
  const JOB_INDEX_PATH = "/static/job_data/adzuna/index.json";
  const JOB_BATCH_PATH = (id) => `/static/job_data/adzuna/batch_${id}.json`;
  const MAX_ATTEMPTS = 10;
  const JOB_COUNT_MIN = 6;
  const JOB_COUNT_MAX = 9;

  function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function randomRecentDate(days = 10) {
    return new Date(Date.now() - Math.random() * days * 86400000).toISOString().split("T")[0];
  }

  function pickRandomItem(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function showStatus(message, type = 'info') {
    $('#syncStatus').show()
      .removeClass('alert-success alert-danger alert-info alert-warning')
      .addClass(`alert-${type}`);
    $('#syncStatusText').html(message);
    setTimeout(() => $('#syncStatus').fadeOut(), 3000);
  }

  function fetchBatchJob(batchIds, selectedJobs, targetCount, attempt = 0) {
    if (selectedJobs.length >= targetCount || attempt >= MAX_ATTEMPTS) {
      finalizeDemoJobs(selectedJobs);
      return;
    }

    const randomBatchId = pickRandomItem(batchIds);
    $.getJSON(JOB_BATCH_PATH(randomBatchId))
      .done(batch => {
        const valid = batch.filter(job => job && typeof job === 'object');
        const picked = pickRandomItem(valid);
        if (picked) selectedJobs.push(picked);
        fetchBatchJob(batchIds, selectedJobs, targetCount, attempt + 1);
      })
      .fail(() => {
        fetchBatchJob(batchIds, selectedJobs, targetCount, attempt + 1);
      });
  }

  function finalizeDemoJobs(jobs) {
    const now = Date.now();
    const demoJobs = {};
    jobs.forEach((job, i) => {
      const id = `demo-${now}-${i}`;
      demoJobs[id] = {
        ...job,
        posted_date: randomRecentDate(10),
        match_percentage: getRandomInt(60, 90)
      };
    });

    renderDemoJobs(demoJobs);
    showStatus("Demo sync complete. Jobs added for session only.", "info");
  }

  function renderDemoJobs(demoJobs) {
    console.log("🔄 [renderDemoJobs] called. Current job count:", Object.keys(window.allJobs).length);
    console.log("📥 New demo jobs:", Object.keys(demoJobs).length);

    // Merge into global list
    window.allJobs = { ...window.allJobs, ...demoJobs };

    // Rebuild remote job list
    window.remoteJobs = Object.fromEntries(
      Object.entries(window.allJobs).filter(([_, j]) => j.is_remote)
    );

    const $tbody = $('#jobsTable tbody');
    $tbody.empty(); // Clear DOM rows only

    // ✅ Render ALL accumulated jobs from window.allJobs
    Object.entries(window.allJobs).forEach(([id, job]) => {
      console.log("⬇️ Adding row:", id, job);
      $tbody.append(`
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
            <a href="${job.url}" target="_blank" class="btn btn-sm btn-outline-primary">
              <i class="fas fa-external-link-alt"></i> Apply
            </a>
          </td>
        </tr>
      `);
      handleJobToggleEvents();
    });

    // Destroy and defer reinit
    if ($.fn.DataTable.isDataTable('#jobsTable')) {
      $('#jobsTable').DataTable().clear().destroy();
    }

    // ✅ Ensure DOM updates complete before DataTable is applied
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        $('#jobsTable').DataTable({
          retrieve: true,
          destroy: true,
          pageLength: 10,
          lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
          order: [[4, 'desc']],
          drawCallback: function () {
            const table = $('#jobsTable').DataTable();
            const info = table.page.info();
            const $container = $('#jobsTable').closest('.tab-pane');
            $container.find('.currentPageValue').text(info.page + 1);
            $container.find('.totalPagesValue').text(info.pages);
            $container.find('.jobsFoundValue').text(info.recordsDisplay);
          }
        });

        console.log("✅ DataTable reinitialized with rows:", $('#jobsTable tbody tr').length);

        handleJobToggleEvents();
        renderRemoteJobs();
      });
    });

  }

  // Main trigger for demo job sync
  window.demoSyncJobs = function () {
    console.log("✅ demoMode.js: using modular demoSyncJobs");
    $.getJSON(JOB_INDEX_PATH)
      .done(index => {
        const batchIds = Object.keys(index.batches || {});
        const count = getRandomInt(JOB_COUNT_MIN, JOB_COUNT_MAX);
        fetchBatchJob(batchIds, [], count);
        console.log("🔁 Starting demo sync using modular handler...");
      })
      .fail(() => showStatus("Failed to load demo job index.", "danger"));
  };

})();
