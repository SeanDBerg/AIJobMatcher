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
