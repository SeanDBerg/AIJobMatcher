// jobSection.js – Handles cleanup and export buttons in the jobSection

function initBatchDeleteHandlers() {
  $('.delete-batch').click(function () {
    const batchId = $(this).data('batch-id');
    if (!confirm(`Delete batch ${batchId}? This cannot be undone.`)) return;

    $('#syncStatus').show().removeClass().addClass('alert alert-info');
    $('#syncStatusText').text(`Deleting batch ${batchId}...`);

    fetch(`/api/adzuna/batch/${batchId}`, {
      method: 'DELETE'
    }).then(res => res.json()).then(data => {
      if (data.success) {
        $('#syncStatus').removeClass().addClass('alert alert-success');
        $('#syncStatusText').html(`Batch ${batchId} deleted successfully. Reloading...`);
        setTimeout(() => location.reload(), 1500);
      } else {
        $('#syncStatus').removeClass().addClass('alert alert-danger');
        $('#syncStatusText').html(`Error deleting batch: ${data.error}`);
      }
    }).catch(err => {
      $('#syncStatus').removeClass().addClass('alert alert-danger');
      $('#syncStatusText').html(`Request failed: ${err}`);
    });
  });
}

function attachTableStatusHandlers(tableId) {
  const table = $(`#${tableId}`).DataTable();

  table.on('draw', function () {
    const pageInfo = table.page.info();

    const container = $(`#${tableId}`).closest('.tab-pane');
    container.find('.currentPageValue').text(pageInfo.page + 1);
    container.find('.totalPagesValue').text(pageInfo.pages);
    container.find('.jobsFoundValue').text(pageInfo.recordsDisplay);
  });

  // Trigger draw immediately on load
  table.draw();
}

function handleJobToggleEvents() {
  $('.toggle-job-details').off('click').on('click', function () {
    const jobId = $(this).data('job-id');
    const detailsRow = $(`#job-details-${jobId}`);

    if (detailsRow.hasClass('d-none')) {
      $('.job-details-row').addClass('d-none'); // Hide others
      detailsRow.removeClass('d-none');
      $(this).html('<i class="fas fa-eye-slash"></i> Hide');
    } else {
      detailsRow.addClass('d-none');
      $(this).html('<i class="fas fa-eye"></i> View');
    }
  });
}

function initJobTables() {
  try {
    // Generic table initializer
    function setupTable(tableId, orderColumn) {
      if ($.fn.DataTable.isDataTable(`#${tableId}`)) {
        $(`#${tableId}`).DataTable().destroy();
      }

      if ($(`#${tableId} tbody tr`).length > 1) {
        const table = $(`#${tableId}`).DataTable({
          pageLength: 10,
          lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
          order: [[orderColumn, 'desc']]
        });

        attachTableStatusHandlers(tableId);  // ✅ From previous step
      }
    }

    setupTable('jobsTable', 4);          
    setupTable('remoteJobsTable', 4);    
    setupTable('batchSummaryTable', 1);

    $('.view-job').click(function () {
      const jobId = $(this).data('job-id');
      showJobDetails(jobId);  // ✅ Assumes showJobDetails is defined globally
    });
  } catch (e) {
    console.error("Error initializing DataTables:", e);
  }
}

function handleJobToggleEvents() {
  $('.toggle-job-details').off('click').on('click', function () {
    const jobId = $(this).data('job-id');
    const jobRow = $(this).closest('tr');
    const existingDetailRow = $(`#inline-detail-row`);

    // Hide previous detail row if it's showing
    if (existingDetailRow.length) {
      if (existingDetailRow.data('job-id') === jobId) {
        existingDetailRow.remove();
        $(this).html('<i class="fas fa-eye"></i> View');
        return;
      } else {
        existingDetailRow.remove();
        $('.toggle-job-details').html('<i class="fas fa-eye"></i> View');
      }
    }

    $(this).html('<i class="fas fa-eye-slash"></i> Hide');

    // Reconstruct the HTML dynamically to look up the job
    const job = window.allJobs?.[jobId] || window.recentJobs?.[jobId] || window.remoteJobs?.[jobId];
    if (!job) return;

    const detailsHtml = `
      <tr id="inline-detail-row" class="bg-light" data-job-id="${jobId}">
        <td colspan="8">
          <div class="job-details-content p-3">
            <h5>${job.title} at ${job.company}</h5>
            ${job.skills?.length ? `
              <div class="mb-3">
                <strong>Skills:</strong>
                <div class="mt-1">
                  ${job.skills.map(skill => `<span class="badge bg-secondary me-1 mb-1">${skill}</span>`).join('')}
                </div>
              </div>` : ''}
            <div class="mb-3">
              <strong>Description:</strong>
              <div class="job-description mt-2">
                ${job.description || 'No description available.'}
              </div>
            </div>
            <div class="text-end">
              <a href="${job.url}" target="_blank" class="btn btn-primary">
                <i class="fas fa-external-link-alt me-1"></i> Apply for This Position
              </a>
            </div>
          </div>
        </td>
      </tr>
    `;

    const $newRow = $(detailsHtml);
    jobRow.after($newRow);

    // Animate only the inner content, not the row
    $newRow.find('.job-details-content').hide().fadeIn(200);
  });
}


// ✅ Attach handlers after DOM is ready
$(document).ready(function () {
  console.log('✅ jobSection.js loaded and DOM ready');

  initBatchDeleteHandlers();

  // ✅ Safely skip table reinit in demo mode
  if (!window.APP_CONTEXT || !window.APP_CONTEXT.isDemo) {
    initJobTables();
  }

  handleJobToggleEvents();
});







