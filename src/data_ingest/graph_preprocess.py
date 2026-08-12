from neo4j import GraphDatabase
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.utils.graph_utils import GraphPreprocessor

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