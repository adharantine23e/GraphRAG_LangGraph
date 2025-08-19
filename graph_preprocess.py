from neo4j import GraphDatabase
from graph_utils import *
import os

driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
        )
try:
  preprocessor = GraphPreprocessor(
            driver=driver
        )
        
  # Run full preprocessing
  with driver.session() as session:
    preprocessor.graph_preprocessing(session = session)
except Exception as e:
  logger.error(f"Unexpected error: {e}")
finally:
  driver.close()