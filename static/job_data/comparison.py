exclude_dirs = {'.venv', '__pycache__', '.git', '.pythonlibs', '.cache'}




@app.route('/upload_resume', methods=['POST'])
def upload_resume():
  ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
  # Check if a file was uploaded
  if 'resume' not in request.files:
    flash('No file part', 'danger')
    logger.info("upload_resume returning with no parameters")
    return redirect(url_for('index'))

  file = request.files['resume']

  # If user doesn't select a file
  if file.filename == '':
    flash('No file selected', 'danger')
    logger.info("upload_resume returning with no parameters")
    return redirect(url_for('index'))

  # Check if the file is allowed
  def allowed_file(filename):
    logger.info("allowed_file returning with filename=%s", filename)
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

  if file and allowed_file(file.filename):
    # Save file temporarily
    filename = secure_filename(file.filename)
    TEMP_FOLDER = tempfile.gettempdir()
    filepath = os.path.join(TEMP_FOLDER, filename)
    file.save(filepath)

    try:
      # Parse resume
      logger.debug(f"Parsing resume from {filepath}")
      try:
        resume_text = parse_resume(filepath)
      except FileParsingError as e:
        logger.error(f"Resume parsing error: {str(e)}")
        flash(f'Resume parsing error: {str(e)}', 'danger')
        return redirect(url_for('index'))
      except Exception as e:
        logger.error(f"Unexpected error parsing resume: {str(e)}")
        flash(f'Error parsing resume: {str(e)}', 'danger')
        return redirect(url_for('index'))

      # Generate embedding
      logger.debug("Generating embedding for resume")
      try:
        embeddings = generate_dual_embeddings(resume_text)
        resume_embedding_narrative = embeddings["narrative"]
        resume_embedding_skills = embeddings["skills"]
      except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        flash(f'Error analyzing resume content: {str(e)}', 'danger')
        return redirect(url_for('index'))

      # Get filters from form
      filters = {'remote': request.form.get('remote', '') == 'on', 'location': request.form.get('location', ''), 'keywords': request.form.get('keywords', '')}

      # Store resume in persistent storage
      try:
        # Create metadata with embedding (convert NumPy array to list for JSON serialization)
        metadata = {"embedding_narrative": resume_embedding_narrative.tolist(), "embedding_skills": resume_embedding_skills.tolist(), "filters": filters}

        # Store in persistent storage
        resume_id = resume_storage.store_resume(temp_filepath=filepath, filename=filename, content=resume_text, metadata=metadata)

        flash(f'Resume "{filename}" successfully uploaded and stored', 'success')

        # Check if user wants to find matching jobs immediately
        find_matches = request.form.get('find_matches', '') == 'on'

        if find_matches:
          # Get all job data using JobManager
          try:
            jobs = job_manager.get_recent_jobs(days=30)
            if not jobs:
              flash('No job data available to match against', 'warning')
              return redirect(url_for('index', resume_id=resume_id))
          except Exception as e:
            logger.error(f"Error retrieving job data: {str(e)}")
            flash(f'Error retrieving job data: {str(e)}', 'danger')
            return redirect(url_for('index', resume_id=resume_id))

          # Find matching jobs using JobManager
          try:
            resume_embeddings = {"narrative": resume_embedding_narrative, "skills": resume_embedding_skills}
            matching_jobs = job_manager.match_jobs_to_resume(resume_embeddings, jobs, filters, resume_text=resume_text)

            # Store resume text in session for display on results page
            session['resume_text'] = resume_text
            session['resume_id'] = resume_id

            # Clean up temp file
            if os.path.exists(filepath):
              os.remove(filepath)

            return render_template('results.html', jobs=matching_jobs, resume_text=resume_text, resume_id=resume_id)
          except Exception as e:
            logger.error(f"Error matching jobs: {str(e)}")
            flash(f'Error matching jobs: {str(e)}', 'danger')
            return redirect(url_for('index', resume_id=resume_id))
        else:
          # Clean up temp file
          if os.path.exists(filepath):
            os.remove(filepath)

          # Redirect to resume manager with this resume active
          return redirect(url_for('index', resume_id=resume_id))

      except Exception as e:
        logger.error(f"Error storing resume: {str(e)}")
        flash(f'Error storing resume: {str(e)}', 'danger')

        # Clean up temp file
        if os.path.exists(filepath):
          os.remove(filepath)

        return redirect(url_for('index'))

    except Exception as e:
      # Catch-all exception handler
      logger.error(f"Unexpected error processing resume: {str(e)}")
      flash(f'Unexpected error: {str(e)}', 'danger')

      # Make sure to clean up the temporary file
      try:
        if os.path.exists(filepath):
          os.remove(filepath)
      except Exception as cleanup_error:
        logger.error(f"Error removing temporary file: {str(cleanup_error)}")

      return redirect(url_for('index'))
  else:
    flash('Invalid file type. Please upload a PDF, DOCX, or TXT file.', 'danger')
    return redirect(url_for('index'))







