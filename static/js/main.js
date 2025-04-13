$(document).ready(function() {
    $('.job-table').each(function() {
        $(this).DataTable({
            pageLength: 10,
            order: [[6, 'desc']],
            columnDefs: [{
                targets: 6,
                render: function(data) {
                    let val = parseFloat(data);
                    return isNaN(val) ? '0%' : val + '%';
                }
            }]
        });
    });

    $('.toggle-job-details').click(function() {
        const jobId = $(this).data('job-id');
        const detailsRow = $('#job-details-' + jobId);
        detailsRow.toggleClass('d-none');
    });
});
