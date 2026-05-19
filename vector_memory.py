import math
import re
from memory_db import get_all_memory

INDEXED_MEMORIES = []
ALL_WORDS = set()

def tokenize(text):
    return re.findall(r'\w+', text.lower())

def build_index():
    global INDEXED_MEMORIES, ALL_WORDS
    memories = get_all_memory()
    documents = [m['content'] for m in memories]
    
    if not documents:
        INDEXED_MEMORIES = []
        ALL_WORDS = set()
        return

    tokenized_docs = [tokenize(doc) for doc in documents]
    ALL_WORDS = set(word for doc in tokenized_docs for word in doc)
    
    df = {}
    for word in ALL_WORDS:
        df[word] = sum(1 for doc in tokenized_docs if word in doc)
        
    num_docs = len(documents)
    idf = {}
    for word, count in df.items():
        idf[word] = math.log(num_docs / (1 + count))
        
    INDEXED_MEMORIES = []
    for i, doc in enumerate(documents):
        tokens = tokenized_docs[i]
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
            
        tfidf = {}
        for word in ALL_WORDS:
            if word in tf:
                tfidf[word] = tf[word] * idf[word]
            else:
                tfidf[word] = 0.0
                
        norm = math.sqrt(sum(v**2 for v in tfidf.values()))
        if norm > 0:
            for word in tfidf:
                tfidf[word] /= norm
                
        INDEXED_MEMORIES.append({
            "content": doc,
            "tfidf": tfidf
        })

def search_memory(query, top_n=3):
    global INDEXED_MEMORIES, ALL_WORDS
    if not INDEXED_MEMORIES:
        build_index()
        if not INDEXED_MEMORIES:
            return []
            
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
        
    q_tf = {}
    for token in query_tokens:
        q_tf[token] = q_tf.get(token, 0) + 1
        
    memories = get_all_memory()
    documents = [m['content'] for m in memories]
    tokenized_docs = [tokenize(doc) for doc in documents]
    num_docs = len(documents)
    
    idf = {}
    for word in ALL_WORDS:
        count = sum(1 for doc in tokenized_docs if word in doc)
        idf[word] = math.log(num_docs / (1 + count))
        
    q_tfidf = {}
    for word in ALL_WORDS:
        if word in q_tf:
            q_tfidf[word] = q_tf[word] * idf.get(word, 0.0)
        else:
            q_tfidf[word] = 0.0
            
    q_norm = math.sqrt(sum(v**2 for v in q_tfidf.values()))
    if q_norm > 0:
        for word in q_tfidf:
            q_tfidf[word] /= q_norm
            
    results = []
    for doc_info in INDEXED_MEMORIES:
        score = sum(q_tfidf[word] * doc_info['tfidf'][word] for word in ALL_WORDS)
        if score > 0.05:  # low threshold to catch single-word queries
            results.append((score, doc_info['content']))
            
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:top_n]]
