from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Neo4jVector
from langchain.graphs import Neo4jGraph
import os
from dotenv import load_dotenv
load_dotenv(override= True)
base_model_name = 'keepitreal/vietnamese-sbert'

model_kwargs = {'device': "cpu"}
encode_kwargs = {'normalize_embeddings': False}
model_embedding = HuggingFaceEmbeddings(model_name = base_model_name, 
                                        model_kwargs = model_kwargs,
                                        encode_kwargs = encode_kwargs)

graph = Neo4jGraph(
    url= os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USERNAME"),
    password=os.getenv("NEO4J_PASSWORD")
)

vector_index = Neo4jVector.from_existing_graph(
    model_embedding,
    search_type="hybrid",
    node_label="Document",
    text_node_properties=['text'],
    embedding_node_property = "embedding")