# embedding_generator.py
import logging
import os
from sklearn.feature_extraction.text import HashingVectorizer
import numpy as np  # Use real numpy here unless you're simulating
import re
from scipy.sparse import csr_matrix  # for type hinting (optional)

logger = logging.getLogger(__name__)

# Set up the vectorizer once
vectorizer = HashingVectorizer(
    n_features=384,
    alternate_sign=False,
    norm='l2',
    stop_words='english',
    lowercase=True
)

def clean_text(text: str) -> str:
    """
    Normalize text for embedding:
    - Lowercase
    - Remove non-alphanumerics
    - Collapse whitespace
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Default embedding dimension for the all-MiniLM-L6-v2 model
EMBEDDING_DIM = 384
# Get the API token from environment variable
def get_api_token():
    api_token = os.environ.get("API_TOKEN")
    if not api_token:
        logger.warning("API_TOKEN environment variable not found")
        return None
    return api_token


# Generate embedding vector for the input text using deterministic hashing
def generate_embedding(text: str) -> np.ndarray:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 10:
        return np.zeros(384)

    try:
        embedding_sparse: csr_matrix = vectorizer.transform([cleaned])
        return embedding_sparse.toarray()[0]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Embedding generation failed: {e}")
        return np.zeros(384)

def batch_generate_embeddings(texts):
    """
    Generate embeddings for a batch of texts
    
    Args:
        texts: List of input texts to embed
        
    Returns:
        List of arrays containing the embedding vectors
    """
    logger.debug(f"Generating embeddings for {len(texts)} texts")
    
    embeddings = [generate_embedding(text) for text in texts]
    
    logger.debug(f"Generated {len(embeddings)} embeddings")
    
    return embeddings

def chunk_text(text, max_length=512, overlap=50):
    """
    Sentence-aware chunking that splits text into chunks close to max_length.
    """
    logger.debug(f"Chunking text of length {len(text)}")

    # Split into sentences using punctuation
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())

            if overlap > 0 and len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
                current_chunk = overlap_text + " " + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk += " " + sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    logger.debug(f"Chunked text into {len(chunks)} chunks")
    return chunks


def generate_embedding_for_long_text(text, max_length=512, overlap=50):
    cleaned = clean_text(text)

    if len(cleaned) <= max_length:
        return generate_embedding(cleaned)

    chunks = chunk_text(cleaned, max_length, overlap)
    embeddings = []

    for chunk in chunks:
        if len(chunk.strip()) < 10:
            continue  # skip meaningless or empty chunks
        emb = generate_embedding(chunk)
        if np.linalg.norm(emb) > 0:
            embeddings.append(emb)

    if not embeddings:
        logger.warning("No valid chunks found for embedding")
        return np.zeros(384)

    return np.mean(embeddings, axis=0)

def extract_skills(text: str, known_skills: set) -> set:
    """
    Extract matching skills from text using a known skills list.
    Args:
        text: Cleaned text input
        known_skills: A set of lowercase skill keywords
    Returns:
        Set of skills found in the text
    """
    tokens = text.lower().split()
    found = set()

    for token in tokens:
        if token in known_skills:
            found.add(token)

    return found

DEFAULT_SKILLS = {
    "python", "java", "c++", "c#", "javascript", "typescript",
    "react", "node", "sql", "postgresql", "mysql", "mongodb",
    "aws", "azure", "gcp", "docker", "kubernetes", "git",
    "flask", "django", "linux", "pandas", "numpy", "tensorflow",
    "scikit", "html", "css", "bash", "redis", "graphql"
}

def boost_score_with_skills(similarity: float, resume_text: str, job_text: str, known_skills=DEFAULT_SKILLS) -> float:
    resume_skills = extract_skills(resume_text, known_skills)
    job_skills = extract_skills(job_text, known_skills)
    overlap = resume_skills & job_skills

    if not overlap:
        return similarity

    boost = 0.05 * len(overlap)
    return min(similarity + boost, 1.0)

# Generate two embeddings: one for the full narrative, one for just the skills section.
def generate_dual_embeddings(text: str) -> dict:
    cleaned = clean_text(text)

    # Try to extract relevant "skills sections"
    # This is heuristic-based: finds common headers like 'skills' or 'technologies'
    skill_blocks = []
    skill_keywords = ['skills', 'technologies', 'tools', 'languages', 'proficiencies']
    lines = text.splitlines()
    collecting = False

    for line in lines:
        line_lower = line.strip().lower()
        if any(k in line_lower for k in skill_keywords):
            collecting = True
            continue
        if collecting:
            if line.strip() == "" or len(skill_blocks) > 5:
                break
            skill_blocks.append(line.strip())

    skill_text = " ".join(skill_blocks) if skill_blocks else cleaned  # fallback to cleaned

    return {
        "narrative": generate_embedding(cleaned),
        "skills": generate_embedding(clean_text(skill_text))
    }