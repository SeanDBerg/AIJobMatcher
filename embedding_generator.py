import logging
import os
import random
import hashlib
import util_np as np

logger = logging.getLogger(__name__)

# Default embedding dimension for the all-MiniLM-L6-v2 model
EMBEDDING_DIM = 384

def get_api_token():
    """
    Get the API token from environment variable
    
    Returns:
        API token string
    """
    api_token = os.environ.get("API_TOKEN")
    if not api_token:
        logger.warning("API_TOKEN environment variable not found")
        return None
    return api_token

def generate_embedding(text):
    """
    Generate embedding vector for the input text using deterministic hashing
    
    Args:
        text: Input text to embed
        
    Returns:
        Array containing the embedding vector
    """
    logger.debug("Generating embedding for text")
    
    # Handle empty or very short text
    if not text or len(text.strip()) < 10:
        logger.warning("Text is empty or too short for meaningful embedding")
        return np.zeros(EMBEDDING_DIM)
    
    try:
        # Create a deterministic embedding based on the content
        # This ensures the same text always gets the same embedding
        random.seed(hashlib.md5(text.encode('utf-8')).hexdigest())
        
        # Generate random values for embedding vector
        embedding_values = []
        for _ in range(EMBEDDING_DIM):
            embedding_values.append(random.uniform(-1, 1))
        
        # Create embedding array    
        embedding = np.NumpyArray(embedding_values)
        
        # Normalize the vector to unit length (for cosine similarity)
        norm = np.norm(embedding_values)
        if norm > 0:
            for i in range(len(embedding_values)):
                embedding.data[i] = embedding.data[i] / norm
        
        logger.debug(f"Generated embedding with shape: {embedding.shape}")
        return embedding
        
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        return np.zeros(EMBEDDING_DIM)

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
    Split text into chunks for processing long documents
    
    Args:
        text: Input text to split
        max_length: Maximum number of characters per chunk
        overlap: Overlap between chunks
        
    Returns:
        List of text chunks
    """
    logger.debug(f"Chunking text of length {len(text)}")
    
    # Split text into sentences or paragraphs
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        # If adding this paragraph would exceed max_length
        if len(current_chunk) + len(paragraph) > max_length:
            # Add current chunk to list if it's not empty
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start a new chunk, potentially with some overlap from previous chunk
            if overlap > 0 and current_chunk:
                # Add overlap from the end of the previous chunk
                overlap_text = current_chunk[-overlap:]
                current_chunk = overlap_text + paragraph
            else:
                current_chunk = paragraph
        else:
            # Add paragraph to current chunk with a newline
            if current_chunk:
                current_chunk += "\n" + paragraph
            else:
                current_chunk = paragraph
    
    # Add the final chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    logger.debug(f"Split text into {len(chunks)} chunks")
    
    return chunks

def generate_embedding_for_long_text(text, max_length=512, overlap=50):
    """
    Generate embedding for long text by chunking and averaging embeddings
    
    Args:
        text: Input text to embed
        max_length: Maximum number of characters per chunk
        overlap: Overlap between chunks
        
    Returns:
        Numpy array containing the averaged embedding vector
    """
    logger.debug(f"Generating embedding for long text of length {len(text)}")
    
    # If text is short enough, don't chunk
    if len(text) <= max_length:
        return generate_embedding(text)
    
    # Split text into chunks
    chunks = chunk_text(text, max_length, overlap)
    
    # Generate embeddings for each chunk
    chunk_embeddings = batch_generate_embeddings(chunks)
    
    # Average the embeddings
    avg_embedding = np.mean(chunk_embeddings, axis=0)
    
    logger.debug(f"Generated average embedding with shape: {avg_embedding.shape}")
    
    return avg_embedding
