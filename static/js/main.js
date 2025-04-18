




// unused

document.addEventListener('DOMContentLoaded', function() {
    // Toggle buttons for job description details
    const toggleButtons = document.querySelectorAll('.toggle-details');

    toggleButtons.forEach(button => {
        button.addEventListener('click', function() {
            const isCollapsed = button.getAttribute('aria-expanded') === 'false';

            if (isCollapsed) {
                button.textContent = 'Hide Details';
            } else {
                button.textContent = 'Show Details';
            }
        });
    });

    // File input validation
    const resumeInput = document.getElementById('resume');

    if (resumeInput) {
        resumeInput.addEventListener('change', function() {
            const file = this.files[0];
            const fileTypeError = document.getElementById('file-type-error');

            if (file) {
                const fileName = file.name;
                const fileExtension = fileName.split('.').pop().toLowerCase();

                // Check if file type is allowed
                if (!['pdf', 'docx', 'txt'].includes(fileExtension)) {
                    alert('Please upload a PDF, DOCX, or TXT file.');
                    this.value = ''; // Clear the file input
                }
            }
        });
    }
});

function getJobMatchesForResume(resumeId) {
  $('#syncStatus').show().removeClass('alert-success alert-danger').addClass('alert-info');
  $('#syncStatusText').html('<i class="fas fa-spinner fa-spin"></i> Matching resume to jobs...');

  $.ajax({
    url: '/api/match-jobs',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ resume_id: resumeId }),
    success: function(response) {
      if (response.success) {
        updateJobMatchPercentages(response.matches);
        $('#syncStatus').removeClass('alert-info').addClass('alert-success');
        $('#syncStatusText').html(`<i class="fas fa-check-circle"></i> Resume matched to ${Object.keys(response.matches).length} jobs successfully.`);
        setTimeout(() => $('#syncStatus').fadeOut(), 3000);
      } else {
        $('#syncStatus').removeClass('alert-info').addClass('alert-danger');
        $('#syncStatusText').html(`<i class="fas fa-exclamation-circle"></i> Error: ${response.error || 'Unknown error'}`);
      }
    },
    error: function(xhr) {
      const msg = xhr.responseJSON?.error || xhr.statusText || 'Unknown error';
      $('#syncStatus').removeClass('alert-info').addClass('alert-danger');
      $('#syncStatusText').html(`<i class="fas fa-times-circle"></i> Error: ${msg}`);
    }
  });
}

function updateJobMatchPercentages(matches) {
  $('.job-table').each(function() {
    const tableId = '#' + $(this).attr('id');
    if (tableId === '#batchSummaryTable') return;
    if (!$.fn.DataTable.isDataTable(tableId)) return;

    const table = $(tableId).DataTable();
    let updatedRows = 0;

    $(tableId + ' tbody tr.job-row').each(function() {
      const jobRow = $(this);
      const jobId = jobRow.data('job-id');

      let matchPercentage = matches[jobId] || 0;
      if (!matchPercentage && jobId && typeof jobId === 'string' && jobId.includes('-')) {
        const baseId = jobId.split('-')[1];
        matchPercentage = matches[baseId] || 0;
      }

      const formattedMatch = matchPercentage + '%';
      const cell = table.cell(jobRow.find('td:eq(6)'));
      cell.data(formattedMatch);
      updatedRows++;
    });

    if (updatedRows > 0) {
      try {
        table.order([6, 'desc']).draw(false);
      } catch (err) {
        console.error("Error reordering table:", err);
      }
    }
  });
}

function handleJobViewEvents() {
  $('.view-job').click(function() {
    const jobId = $(this).data('job-id');
    showJobDetails(jobId);
  });
}

function showJobDetails(jobId) {
  const activeTab = $('.nav-tabs .active').attr('id');
  let job = {};
  if (activeTab === 'all-jobs-tab') {
    job = allJobs[jobId];
  } else if (activeTab === 'recent-tab') {
    job = recentJobs[jobId];
  } else if (activeTab === 'remote-tab') {
    job = remoteJobs[jobId];
  }

  if (!job) {
    $('#jobDetails').html('<div class="alert alert-danger">Job details not found.</div>');
    return;
  }

  const detailsHtml = `
    <div class="mb-4">
      <h3>${job.title}</h3>
      <p class="text-muted">${job.company} • ${job.location} • ${job.is_remote ? '<span class="badge bg-success">Remote</span>' : ''}</p>
      ${job.salary_range ? `<p class="badge bg-info">${job.salary_range}</p>` : ''}
      <p class="text-muted">Posted: ${job.posted_date}</p>
      ${job.match_percentage ? `<p class="badge bg-success">Match: ${job.match_percentage}%</p>` : ''}
    </div>
    <h4>Job Description</h4>
    <div class="mb-4 job-description">
      ${job.description || 'No description available.'}
    </div>
    ${job.skills && job.skills.length > 0 ? `
      <h4>Skills</h4>
      <div class="mb-4">
        ${job.skills.map(skill => `<span class="badge bg-secondary me-1">${skill}</span>`).join('')}
      </div>` : ''}
  `;

  $('#jobDetails').html(detailsHtml);
  $('#jobApplyLink').attr('href', job.url);
}