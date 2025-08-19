from typing import Iterable, Optional, List, Generator, Dict, Any
from neo4j import GraphDatabase, Driver, Session 

from langchain.schema import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_groq import ChatGroq
from langchain_community.graphs import Neo4jGraph

from underthesea import word_tokenize
import os 
import re
import json
from dotenv import load_dotenv
load_dotenv(override= True)

def format_data(path_data: str) -> Iterable:
    """Load JSON data with fallback."""
    encodings = ['utf-8-sig', 'latin-1', 'utf-8']

    for encoding in encodings:
        try:
            with open(path_data, encoding= encoding) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return []
        
def split_chunk(data: str, chunk_size: int = 500, overlap: int = 20) -> List[str]:
    """
    Split data into chunks of 500 words with overlap of 20 words.
    Args:
        data (str): The input data to be split into chunks.
        chunk_size (int): The size of each chunk in words.
        overlap (int): The number of words to overlap between chunks.
    Returns:
        chunks (List[str]): A list of chunks of data.
    """

    if not data.strip():
        print("Data is empty")
        return []
    
    start_index = 0
    chunks = []
    data_encoded = word_tokenize(data)
    step = chunk_size - overlap
    
    while start_index < len(data_encoded):
        end_index = min(start_index + chunk_size, len(data_encoded))
        chunk = data_encoded[start_index:end_index]
        chunks.append(" ".join(chunk))
        if end_index >= len(data_encoded):
            break
        start_index += step
    return chunks

def create_chunk(data: Document) -> List[Document]:
    chunked_page_content = split_chunk(data = data.page_content)
    return [
        Document(page_content=chunked_value, metadata=data.metadata) for chunked_value in chunked_page_content
    ]

def process_documents_to_chunks(documents: Iterable[Document]) -> Generator[Document, None, None]:
    for doc in documents:
        yield from create_chunk(data = doc)

def process_documents_to_graph(chunks: Iterable[Document], llm_transformer: LLMGraphTransformer, batch_size: int = 10) -> Generator[object, None, None]:
    batch = []
    for index, chunk in enumerate(chunks):
        batch.append(chunk)
        if len(batch) >= batch_size:
            try:
                graph_document = llm_transformer.convert_to_graph_documents(batch)
                yield from graph_document
                print(f"Processed batch end at chunk {index}")
            except Exception as e:
                print(f"Error Processed batch end at chunk {index}: {e}")
                for j, single_chunk in enumerate(batch):
                    try:
                        single_graph_document = llm_transformer.convert_to_graph_documents([single_chunk])
                        yield from single_graph_document
                    except Exception as e:
                        print(f"Error in chunk {j}: {e}")
            finally:
                batch.clear()
    
    # Get the remain batch
    if batch:
        try:
            graph_document = llm_transformer.convert_to_graph_documents(batch)
            yield from graph_document
            print(f"Processed final batch")
        except Exception as e:
            print("Error processing final batch: ", e)

# Create node manually if fail
def create_node(session: Session, value: Dict[str, Any]):
    label = value['labels'][0]
    text = value['text']
    summary = value['summary']
    id = value['id']
    title = value['title']

    default_cypher = f'''
    CREATE (n:{label} {{id: "{id}", text: "{text}", title: "{title}", summary: "{summary}" }})
    '''
    session.run(default_cypher)


if __name__ == "__main__":
    # Initialize
    filepath = r"data\WikiHow_concatenated_fixed_4.json"
    llm_graph = ChatGroq(temperature = 0, model="gemma2-9b-it")
    llm_transformer = LLMGraphTransformer(llm_graph)    
    graph = Neo4jGraph(
        url= os.getenv("NEO4J_URI"),
        username=os.getenv("NEO4J_USERNAME"),
        password=os.getenv("NEO4J_PASSWORD")
    )

    # Load JSON data
    data = format_data(filepath)
    
    # Load data to chunks and to graph
    document_chunks = process_documents_to_chunks(documents= data)
    graph_documents = process_documents_to_graph(chunks= document_chunks, 
                                                 llm_transformer= llm_transformer)
    
    # Add to the graph
    print("Adding to the graph")
    graph.add_graph_documents(
        graph_documents= list(graph_documents),
        baseEntityLabel= True,
        include_source= True
    )

    

