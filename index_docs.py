"""
Script per caricare documenti scientifici e ricerche nutrizionali in Pinecone.

Questo script legge tutti i file PDF e TXT dalla cartella data/,
li processa in chunk, crea gli embedding e li carica nel database vettoriale Pinecone.
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader

# Carica le variabili d'ambiente
load_dotenv()

# Configurazione dalle variabili d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")

# Validazione variabili d'ambiente
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY non trovata nelle variabili d'ambiente")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY non trovata nelle variabili d'ambiente")
if not PINECONE_INDEX_NAME:
    raise ValueError("PINECONE_INDEX_NAME non trovata nelle variabili d'ambiente")

# Inizializza i client
openai_client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

# Configurazione per il text splitter
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_MODEL = "text-embedding-3-small"
# text-embedding-3-small può essere configurato per diverse dimensioni
# Usa 1024 per compatibilità con l'indice esistente, o cambia l'indice a 1536
EMBEDDING_DIMENSION = 1024
BATCH_SIZE = 50

# Percorso della cartella data
DATA_DIR = Path("data")


def load_documents() -> List[Tuple[str, str]]:
    """
    Carica tutti i file PDF e TXT dalla cartella data/.
    
    Returns:
        List[Tuple[str, str]]: Lista di tuple (filepath, text_content)
    """
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"La cartella {DATA_DIR} non esiste. Creala e aggiungi i documenti.")
    
    documents = []
    pdf_files = list(DATA_DIR.glob("*.pdf"))
    txt_files = list(DATA_DIR.glob("*.txt"))
    
    all_files = pdf_files + txt_files
    
    if not all_files:
        print(f"[!] Nessun file PDF o TXT trovato in {DATA_DIR}")
        return documents
    
    print(f"[+] Trovati {len(pdf_files)} file PDF e {len(txt_files)} file TXT")
    
    for file_path in all_files:
        try:
            print(f"   [*] Caricamento: {file_path.name}")
            
            if file_path.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(file_path))
            elif file_path.suffix.lower() == ".txt":
                loader = TextLoader(str(file_path), encoding='utf-8')
            else:
                continue
            
            loaded_docs = loader.load()
            
            # Unisce tutto il testo del documento
            text_content = "\n\n".join([doc.page_content for doc in loaded_docs])
            
            if not text_content.strip():
                print(f"   [!] File vuoto ignorato: {file_path.name}")
                continue
            
            documents.append((str(file_path), text_content))
            print(f"   [OK] Caricato: {file_path.name} ({len(text_content)} caratteri)")
            
        except Exception as e:
            print(f"   [ERRORE] Errore nel caricamento di {file_path.name}: {str(e)}")
            continue
    
    return documents


def split_text_into_chunks(text: str) -> List[str]:
    """
    Divide il testo in chunk usando RecursiveCharacterTextSplitter.
    
    Args:
        text: Testo da dividere
        
    Returns:
        List[str]: Lista di chunk di testo
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = text_splitter.split_text(text)
    return chunks


def create_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Crea gli embedding per una lista di testi usando OpenAI.
    
    Args:
        texts: Lista di testi da convertire in embedding
        
    Returns:
        List[List[float]]: Lista di vettori embedding
    """
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIMENSION
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        raise Exception(f"Errore nella creazione degli embedding: {str(e)}")


def ensure_index_exists():
    """
    Verifica che l'indice Pinecone esista, altrimenti lo crea.
    """
    existing_indexes = [index.name for index in pc.list_indexes()]
    
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"[>] Creazione indice '{PINECONE_INDEX_NAME}' in Pinecone...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine"
        )
        print(f"[OK] Indice '{PINECONE_INDEX_NAME}' creato con successo")
    else:
        print(f"[OK] Indice '{PINECONE_INDEX_NAME}' già esistente")


def upsert_batch(index, vectors_batch: List[dict]):
    """
    Esegue l'upsert di un batch di vettori in Pinecone.
    
    Args:
        index: Indice Pinecone
        vectors_batch: Lista di dizionari con id, values e metadata
    """
    try:
        index.upsert(vectors=vectors_batch)
    except Exception as e:
        raise Exception(f"Errore nell'upsert su Pinecone: {str(e)}")


def main():
    """
    Funzione principale che orchetra il processo di indicizzazione.
    """
    print("[*] Caricamento documenti in Pinecone...\n")
    
    try:
        # 1. Assicura che l'indice esista
        ensure_index_exists()
        
        # 2. Carica i documenti
        documents = load_documents()
        
        if not documents:
            print("\n[!] Nessun documento da processare.")
            return
        
        # 3. Divide in chunk
        print(f"\n[*] Divisione dei documenti in chunk...")
        all_chunks = []
        for file_path, text in documents:
            chunks = split_text_into_chunks(text)
            all_chunks.extend(chunks)
            print(f"   [*] {Path(file_path).name}: {len(chunks)} chunk")
        
        if not all_chunks:
            print("\n[!] Nessun chunk generato dai documenti.")
            return
        
        print(f"\n[OK] Totale chunk generati: {len(all_chunks)}")
        
        # 4. Recupera l'indice Pinecone
        index = pc.Index(PINECONE_INDEX_NAME)
        
        # 5. Processa i chunk in batch
        print(f"\n[>] Creazione embedding e caricamento in Pinecone...")
        
        total_uploaded = 0
        chunk_id_counter = 1
        
        for i in range(0, len(all_chunks), BATCH_SIZE):
            batch_chunks = all_chunks[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"   [*] Batch {batch_num}/{total_batches}: processando {len(batch_chunks)} chunk...")
            
            try:
                # Crea gli embedding per il batch
                embeddings = create_embeddings(batch_chunks)
                
                # Prepara i vettori per Pinecone
                vectors_batch = []
                for chunk_text, embedding in zip(batch_chunks, embeddings):
                    vectors_batch.append({
                        "id": f"id-{chunk_id_counter}",
                        "values": embedding,
                        "metadata": {"text": chunk_text}
                    })
                    chunk_id_counter += 1
                
                # Esegue l'upsert
                upsert_batch(index, vectors_batch)
                total_uploaded += len(vectors_batch)
                
                print(f"   [OK] Batch {batch_num} caricato: {len(vectors_batch)} chunk")
                
            except Exception as e:
                print(f"   [ERRORE] Errore nel batch {batch_num}: {str(e)}")
                continue
        
        # 6. Output finale
        print(f"\n[*] Caricati {total_uploaded} chunk in totale.")
        print("[OK] Operazione completata: Knowledge base aggiornata!")
        
    except FileNotFoundError as e:
        print(f"\n[ERRORE] Errore: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERRORE] Errore critico: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

