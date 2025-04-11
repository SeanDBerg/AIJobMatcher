document.addEventListener('DOMContentLoaded', function() {
    // Initialize DataTables with proper configuration
    $('.job-table').each(function() {
        const tableId = $(this).attr('id');
        if (!tableId) return;
        
        // Skip empty tables or tables with just "No jobs found" message
        const rows = $(this).find('tbody tr');
        if (rows.length === 0 || (rows.length === 1 && rows.find('td[colspan]').length > 0)) {
            return;
        }

        try {
            const table = $(this).DataTable({
                pageLength: 10,
                order: [[6, 'desc']], // Sort by match percentage
                columnDefs: [
                    {
                        targets: 6, // Match percentage column
                        type: 'numeric',
                        render: function(data) {
                            return data ? parseFloat(data) : 0;
                        }
                    }
                ],
                initComplete: function() {
                    // Ensure table cells are properly indexed
                    this.api().cells().every(function() {
                        $(this.node()).attr('data-dt-column', this.index().column);
                    });
                }
            });
            
            // Store table reference
            if (!window.jobTables) window.jobTables = {};
            window.jobTables[tableId] = table;
        } catch (error) {
            console.error(`Error initializing table ${tableId}:`, error);
        }
    });

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
