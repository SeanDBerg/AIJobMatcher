// resumeSection.js - Handles resume selection, activation, and job matching

let currentResumeId = null;

function initResumeSection() {
  attachResumeSelectionHandlers();
  autoActivateResumeFromURL();
  handleJobViewEvents();
  handleJobToggleEvents();
}

function attachResumeSelectionHandlers() {
  $('.resume-select-link').click(function(e) {
    e.preventDefault();
    const resumeId = $(this).data('resume-id');
    selectResume(resumeId);
  });
}

function autoActivateResumeFromURL() {
  const urlParams = new URLSearchParams(window.location.search);
  const activeResumeId = urlParams.get('active_resume_id');
  if (activeResumeId) {
    const resumeLink = $(`.resume-select-link[data-resume-id="${activeResumeId}"]`);
    if (resumeLink.length) {
      $('.resume-select-link').removeClass('active');
      resumeLink.addClass('active');
      currentResumeId = activeResumeId;
      setTimeout(() => getJobMatchesForResume(activeResumeId), 1000);
    }
  } else if ($('.resume-select-link').length) {
    const defaultLink = $('.resume-select-link').first();
    defaultLink.addClass('active');
    currentResumeId = defaultLink.data('resume-id');
  }
}

function selectResume(resumeId) {
  $('.resume-select-link').removeClass('active');
  $(`.resume-select-link[data-resume-id="${resumeId}"]`).addClass('active');
  currentResumeId = resumeId;

  $('#syncStatus').show().removeClass('alert-success alert-danger').addClass('alert-info');
  $('#syncStatusText').text('Matching resume to jobs...');
  // 🆕 Update session on server
  fetch('/api/set_resume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_id: resumeId })
  }).then(res => res.json()).then(data => {
    if (!data.success) {
      console.error("Failed to update resume_id in session:", data.error);
    }
  });

  getJobMatchesForResume(resumeId);

  const url = new URL(window.location);
  url.searchParams.set('active_resume_id', resumeId);
  window.history.pushState({}, '', url);
}


$(document).ready(initResumeSection);