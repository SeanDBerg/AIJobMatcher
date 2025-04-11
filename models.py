# model.py
from datetime import datetime

# This file would normally contain SQLAlchemy models
# For this project, we're using simple data structures instead of a database
# Defining classes to represent our data structures

class Resume:
    """Class representing a parsed resume"""
    def __init__(self, text, filename, parsed_date=None):
        self.text = text
        self.filename = filename
        self.parsed_date = parsed_date or datetime.now()
        self.embedding = None
        self.embedding_narrative = None
        self.embedding_skills = None
    
    def to_dict(self):
        return {
            'text': self.text,
            'filename': self.filename,
            'parsed_date': self.parsed_date.isoformat(),
        }

# Class representing a job listing
class Job:
    def __init__(self, title, company, description, location, is_remote=False, 
                 posted_date=None, url="", skills=None, salary_range=None):
        self.title = title
        self.company = company
        self.description = description
        self.location = location
        self.is_remote = is_remote
        self.posted_date = posted_date or datetime.now()
        self.url = url
        self.skills = skills or []
        self.salary_range = salary_range or ""
        self.embedding = None
        self.embedding_narrative = None
        self.embedding_skills = None
    
    def to_dict(self, include_embeddings=False):
        job_dict = {
            'title': self.title,
            'company': self.company,
            'description': self.description,
            'location': self.location,
            'is_remote': self.is_remote,
            'posted_date': self.posted_date.isoformat() if isinstance(self.posted_date, datetime) else self.posted_date,
            'url': self.url,
            'skills': self.skills,
            'salary_range': self.salary_range
        }

        if include_embeddings:
            job_dict['embedding_narrative'] = (
                self.embedding_narrative.tolist() if self.embedding_narrative is not None else None
            )
            job_dict['embedding_skills'] = (
                self.embedding_skills.tolist() if self.embedding_skills is not None else None
            )

        return job_dict


class JobMatch:
    """Class representing a match between a resume and job"""
    def __init__(self, job, similarity_score):
        self.job = job
        self.similarity_score = similarity_score
    
    def to_dict(self):
        return {
            'job': self.job.to_dict(),
            'similarity_score': self.similarity_score
        }
