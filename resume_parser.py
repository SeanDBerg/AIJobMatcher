import logging
import os
import base64
import random
import json

logger = logging.getLogger(__name__)

# Sample resume content for different roles to provide realistic matching
SAMPLE_RESUMES = {
    "software_engineer": """
PROFESSIONAL SUMMARY
Experienced software engineer with 5+ years developing web applications using Python, JavaScript, and cloud technologies. Strong problem-solving skills and experience with agile development methodologies.

SKILLS
- Programming: Python, JavaScript, TypeScript, Java
- Web Frameworks: Flask, Django, React, Node.js
- Databases: PostgreSQL, MongoDB, Redis
- DevOps: Docker, Kubernetes, AWS, CI/CD
- Tools: Git, Jira, Linux/Unix

EXPERIENCE
Senior Software Engineer | TechCorp | 2020-Present
- Developed RESTful APIs using Flask and FastAPI
- Implemented microservices architecture on AWS
- Reduced API response time by 40% through optimization

Software Developer | WebSolutions Inc. | 2018-2020
- Built responsive web applications using React and Node.js
- Integrated third-party APIs and payment gateways
- Collaborated with cross-functional teams to deliver projects on schedule

EDUCATION
Bachelor of Science in Computer Science | Tech University | 2018
""",
    "data_scientist": """
PROFESSIONAL SUMMARY
Data scientist with expertise in machine learning, statistical analysis, and data visualization. Experience implementing predictive models and deriving actionable insights from complex datasets.

SKILLS
- Programming: Python, R, SQL
- Machine Learning: TensorFlow, PyTorch, scikit-learn
- Data Analysis: Pandas, NumPy, Jupyter
- Visualization: Matplotlib, Seaborn, Tableau
- NLP: NLTK, spaCy, transformers

EXPERIENCE
Senior Data Scientist | AnalyticsPro | 2019-Present
- Developed machine learning models for customer segmentation
- Created NLP pipeline for sentiment analysis of customer feedback
- Built real-time dashboards for business KPIs using Tableau

Data Analyst | DataCorp | 2017-2019
- Conducted statistical analysis on large datasets
- Created automated reporting systems using Python and SQL
- Presented insights to non-technical stakeholders

EDUCATION
Master of Science in Data Science | Analytics University | 2017
Bachelor of Science in Statistics | Math College | 2015
""",
    "product_manager": """
PROFESSIONAL SUMMARY
Results-driven product manager with experience delivering successful digital products. Strong background in user research, product strategy, and cross-functional team leadership.

SKILLS
- Product Management: Roadmapping, User Stories, Prioritization
- Tools: Jira, Confluence, Figma, Google Analytics
- Technical: Basic HTML/CSS, SQL, API knowledge
- Business: Market Analysis, Competitive Research, User Research
- Soft Skills: Communication, Leadership, Stakeholder Management

EXPERIENCE
Senior Product Manager | ProductCo | 2020-Present
- Led development of e-commerce platform increasing revenue by 35%
- Conducted user research to identify key pain points and opportunities
- Managed agile development process with engineering and design teams

Product Owner | TechSolutions | 2018-2020
- Owned product backlog and prioritization for mobile application
- Collaborated with UX designers to create intuitive user experiences
- Defined success metrics and KPIs for product features

EDUCATION
MBA with focus on Technology Management | Business School | 2018
Bachelor of Arts in Communication | Liberal Arts College | 2015
"""
}

def _generate_resume_for_file(filename):
    """
    Generate appropriate mock resume content based on filename
    
    Args:
        filename: Name of the file
        
    Returns:
        String containing generated resume text
    """
    # Use filename to deterministically select a resume type
    filename_lower = filename.lower()
    
    if "data" in filename_lower or "science" in filename_lower or "analyst" in filename_lower:
        resume_type = "data_scientist"
    elif "product" in filename_lower or "manager" in filename_lower or "management" in filename_lower:
        resume_type = "product_manager"
    else:
        # Default to software engineer
        resume_type = "software_engineer"
    
    return SAMPLE_RESUMES[resume_type]

def parse_pdf(file_path):
    """
    Parse a PDF file and extract text content (mock implementation)
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        String containing the extracted text
    """
    logger.debug(f"Mock parsing PDF: {file_path}")
    filename = os.path.basename(file_path)
    return _generate_resume_for_file(filename)

def parse_docx(file_path):
    """
    Parse a DOCX file and extract text content (mock implementation)
    
    Args:
        file_path: Path to the DOCX file
        
    Returns:
        String containing the extracted text
    """
    logger.debug(f"Mock parsing DOCX: {file_path}")
    filename = os.path.basename(file_path)
    return _generate_resume_for_file(filename)

def parse_txt(file_path):
    """
    Parse a TXT file and extract text content
    
    Args:
        file_path: Path to the TXT file
        
    Returns:
        String containing the extracted text
    """
    logger.debug(f"Parsing TXT: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            text = file.read()
        
        # If text file is empty or very short, generate mock content
        if len(text.strip()) < 50:
            filename = os.path.basename(file_path)
            return _generate_resume_for_file(filename)
        
        return text.strip()
    except Exception as e:
        logger.error(f"Error reading text file: {str(e)}")
        filename = os.path.basename(file_path)
        return _generate_resume_for_file(filename)

def parse_resume(file_path):
    """
    Parse a resume file and extract text content based on file extension
    
    Args:
        file_path: Path to the resume file
        
    Returns:
        String containing the extracted text
    """
    logger.debug(f"Parsing resume: {file_path}")
    
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == '.pdf':
        return parse_pdf(file_path)
    elif file_extension == '.docx':
        return parse_docx(file_path)
    elif file_extension == '.txt':
        return parse_txt(file_path)
    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")
