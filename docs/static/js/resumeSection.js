$(document).ready(function () {
  $('#resumeList').on('click', '.delete-resume', function () {
    const resumeItem = $(this).closest('.list-group-item');
    const resumeId = resumeItem.find('.resume-select-link').data('resume-id');

    if (!resumeId) {
      alert("Resume ID missing. Cannot delete.");
      return;
    }

    if (!confirm("Are you sure you want to delete this resume? This cannot be undone.")) {
      return;
    }

    $.post(`/delete_resume/${resumeId}`, function () {
      location.reload();  // or remove the item from the DOM dynamically
    }).fail(function (xhr) {
      alert(`Error deleting resume: ${xhr.responseText || xhr.statusText}`);
    });
  });
});