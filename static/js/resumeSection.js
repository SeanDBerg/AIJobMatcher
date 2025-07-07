/* Purpose: Handle resume delete and upload actions, with demo-mode short-circuit. */
$(document).ready(function () {
  /* Purpose: Delete a resume (live) or show demo alert (static). */
  $('#resumeList').on('click', '.delete-resume', function () {
    const resumeItem = $(this).closest('.list-group-item');
    const resumeId   = resumeItem.find('.resume-select-link').data('resume-id');

    if (!resumeId) {
      alert("Resume ID missing. Cannot delete.");
      return;
    }

    if (!confirm("Are you sure you want to delete this resume? This cannot be undone.")) {
      return;
    }

    /* ------------------------------------------------------------
       DEMO SHORT-CIRCUIT
       ------------------------------------------------------------ */
    if (window.IS_DEMO) {
      alert("Demo mode: delete is disabled.");
      return; // stop here in static demo
    }

    /* LIVE SERVER CALL (unchanged) */
    $.post(`/delete_resume/${resumeId}`, function () {
      location.reload();  // or remove the item from the DOM dynamically
    }).fail(function (xhr) {
      alert(`Error deleting resume: ${xhr.responseText || xhr.statusText}`);
    });
  });

  /* Purpose: Upload a resume (live) or show demo alert (static). */
  $('#uploadForm').on('submit', function (e) {
    e.preventDefault();

    const fileInput = $('#resumeFile')[0];
    if (!fileInput.files.length) {
      alert("Please choose a file before uploading.");
      return;
    }

    /* DEMO SHORT-CIRCUIT */
    if (window.IS_DEMO) {
      alert("Demo mode: upload is disabled.");
      return; // stop here in static demo
    }

    /* LIVE SERVER CALL (unchanged) */
    const formData = new FormData(this);

    $.ajax({
      url: '/upload_resume',
      type: 'POST',
      data: formData,
      processData: false,
      contentType: false,
      success: function () {
        alert("Upload successful.");
        location.reload();
      },
      error: function (xhr) {
        alert(`Error uploading resume: ${xhr.responseText || xhr.statusText}`);
      }
    });
  });
});
