from typing import Literal, List, Dict, Any, Tuple, TypedDict, Optional
import json
import re
import sqlite3
import hashlib
import uuid
import datetime
import time
import hashlib
from dataclasses import dataclass
from itertools import combinations
from langchain.graphs import Neo4jGraph
from langchain_neo4j.vectorstores.neo4j_vector import remove_lucene_chars
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

class GraphRAGState(TypedDict):
    processing_start_time: float
    question: str
    chat_history: List[Tuple[str, str]]
    entities: List[str]
    structured_data: str
    relevant_documents: List[str]
    final_prompt: str
    final_answer: str
    curr_agent: str

@dataclass
class PatientInteraction:
    id: str
    timestamp: str
    question: str
    prompt: str
    chatcbot_answers: str
    processing_time: float
    success: bool
    error_message: Optional[str] = None

# Agent 1: Extract entities from patient question
class EntityExtractionAgent:
    def __init__(self, llm):
        self.llm = llm
        self.prompt = PromptTemplate.from_template("""
        Bạn là một chuyên viên y tế với nhiệm vụ là trích xuất các thực thể y tế quan trọng từ câu hỏi bệnh nhân.

        Các thực thể y tế có thể bao gồm:
            - Tên bệnh, triệu chứng bệnh
            - Thuốc 
            - Phương thức chữa bệnh 
            - Tên các loại hóa học
            - Cơ quan, bộ phận cơ thể
            - Bác sĩ, chuyên khoa

        Câu hỏi bệnh nhân: 
        {question}
        
        Hãy trả về kết quả dưới dạng JSON:
        {{'entities': [ 'entity 1', 'entity 2', ...]}}
        Nếu bạn không thể trích xuất các thực thể y tế từ câu hỏi bệnh nhân, vẫn phải trả về kết quả dưới dạng JSON:
        {{'entities': []}}                                                
        """)

    def extract_entities(self, state: GraphRAGState) -> GraphRAGState:
        try:
            prompt = self.prompt.format(question= state['question'])
            response = self.llm.invoke(prompt)

            # Parse the JSON response
            cleaned_text = re.sub(r'```(?:json)?\s*\n?(.*?)\n?```', r'\1', response.content, flags= re.DOTALL).replace("'", '"')
            entities = json.loads(cleaned_text)
            entities = entities.get('entities', [])
            state['entities'] = entities
            state['curr_agent'] = "entity_extraction_agent"
            WorkflowMonitor.print_state(state)
        except Exception as e:
            print(f"Error in entity extraction agent: {e}")
            state['entities'] = []
        
        return state

class GraphRetrievalAgent:
    def __init__(self, graph: Neo4jGraph):
        self.graph = graph
    
    def generate_full_text_query(self, input:str)-> str:
        full_text_query = ""
        words =[w for w in remove_lucene_chars(input).split() if w]
        for word in words[:-1]:
            full_text_query += f"{word}~2 AND "
        full_text_query += f"{words[-1]}~2"
        return full_text_query.strip()
    
    def autimatum_query(self, input_entity: str, limit: int) -> List[Any]:
        query = self.generate_full_text_query(input_entity)
        response = self.graph.query(
            '''
            CALL db.index.fulltext.queryNodes("entity", $query, {limit:10})
            YIELD node, score
            CALL {
            WITH node
            MATCH (node)-[r:!MENTIONS]->(neighbor)
            RETURN node.id + ' - ' + type(r) + ' -> ' + neighbor.id AS output
            UNION ALL
            WITH node
            MATCH (node)<-[r:!MENTIONS]-(neighbor)
            RETURN neighbor.id + ' - ' + type(r) + ' -> ' + node.id AS output
            }
            RETURN output LIMIT $limit
            ''', {"query": query, "limit": limit})
        entity_results = [el['output'] for el in response]
        return entity_results

    def retrieve_structured_data(self, state: GraphRAGState) -> GraphRAGState:
        result = ""
        try:
            entities = state.get('entities', [])

            # For the case when there are no entities
            if not entities:
                result = "No structured data found"
            # For the case when there is only one entity
            elif len(entities) == 1:
                entity = entities[0]
                entity_results = self.autimatum_query(input_entity= entity, limit = 10)
                if entity_results:
                    result += f"\nRelationship related to entity: {entity}\n"
                    result += "\n".join(entity_results) + "\n"
                else:
                    print("You stupid")
            
            # For the case when there are multiple entities
            else:
                two_cases_comb = list(combinations(entities, 2))
                for comb in two_cases_comb:
                    result += f"Relationship between {comb[0]} and {comb[1]}:\n"
                    start_node = comb[0]
                    end_node = comb[1]
                    response = self.graph.query(
                        '''
                        MATCH p = (startNode)-[*1..2]-(endNode)
                        WHERE startNode.id = $start_node AND endNode.id = $end_node
                        RETURN p, relationships(p) as rels
                        ''', {"start_node": start_node, "end_node": end_node}
                    )
                    records = [record for record in response]
                    # In the case there are no connections between the two entities, perform autimatum
                    if not records:
                        result += f'No connection between {start_node} and {end_node} found\n'
                        result += f"Relationship related to entity: {start_node}\n"
                        entity_result1 = self.autimatum_query(input_entity= start_node, limit= 3)
                        result += "\n".join(entity_result1) + "\n"
                        result += f"Relationship related to entity: {end_node}\n"
                        entity_result2 = self.autimatum_query(input_entity= end_node, limit= 3)
                        result += "\n".join(entity_result2) + "\n"
                    else:
                        relationships_lst = []
                        for record in records:
                            relationships = record['rels']
                            for rel in relationships:
                                

                                # This is for GraphDataBase
                                # node_lst = []
                                # for node in rel.nodes:
                                #     id_node = node["id"]

                                #     # Test if the node has the id of the document
                                #     is_letter = bool(re.search(r'[a-zA-Z]', id_node))
                                #     is_num = bool(re.search(r"\d", id_node))
                                #     if is_letter and is_num and "title" in node:
                                #         node_lst.append(node['title'])
                                #     else:
                                #         node_lst.append(node['id'])

                                # This is for Neo4jGraph
                                
                                first_node = rel[0].get("id", "")
                                is_letter = bool(re.search(r'[a-zA-Z]', first_node))
                                is_num = bool(re.search(r"\d", first_node))
                                if is_letter and is_num and "title" in rel[0]:
                                    first_node = rel[0].get("title", "")
                                rel_type = rel[1]
                                second_node = rel[2].get("id", "")

                                format_txt = f"{first_node} -[:{rel_type}]-> {second_node}"
                                relationships_lst.append(format_txt)
                        result += "\n".join(relationships_lst) + "\n"
            state['structured_data'] = result
            state['curr_agent'] = "graph_retrieval_agent"
            print("The final result of the graph retrieval agent: ", result)
            WorkflowMonitor.print_state(state)
        except Exception as e:
            print(f"Error in graph retrieval agent: {e}")

        return state

class DocumentRetrievalAgent:
    def __init__(self, vector_idx):
        self.vector_idx = vector_idx
    
    def retrieve_relevant_documents(self, state: GraphRAGState) -> GraphRAGState:
        try:
            question = state['question']

            docs = self.vector_idx.similarity_search(question, k = 2)
            relevant_documents = [doc.page_content for doc in docs]
            state['relevant_documents'] = relevant_documents
            state['curr_agent'] = "document_retrieval_agent"

            WorkflowMonitor.print_state(state)
        except Exception as e:
            print(f"Error in document retrieval agent: {e}")
        return state


class AnswerGenerationAgent:
    def __init__(self, llm):
        self.llm = llm
        self.answer_prompt = PromptTemplate.from_template("""
        Bạn là một trợ lý sức khỏe chuyên nghiệp. Nhiệm vụ của bạn là tạo ra câu trả lời toàn diện cho câu hỏi của bệnh nhân 
        bằng cách kết hợp thông tin từ đồ thị kiến thức và tài liệu liên quan.
        
        Câu hỏi của bệnh nhân:
        {question}
        
        Thông tin từ đồ thị kiến thức (các mối quan hệ và thực thể):
        {structured_data}
        
        Tài liệu liên quan:
        {documents}
        
        Hướng dẫn:
        1. Sử dụng cả thông tin từ đồ thị và tài liệu để trả lời
        2. Ưu tiên thông tin từ đồ thị kiến thức vì nó có cấu trúc và độ chính xác cao
        3. Bổ sung thông tin từ tài liệu để làm rõ hoặc cung cấp chi tiết thêm
        4. Trả lời một cách rõ ràng, dễ hiểu cho bệnh nhân
        5. Nếu không có thông tin đủ để trả lời, hãy nói rõ điều đó
        
        Câu trả lời:
        """)
    
    def generate_answer(self, state: GraphRAGState) -> GraphRAGState:
        try:
            question = state["question"]
            structured_data = state.get("structured_data", "")
            documents = state.get("relevant_documents", [])

            document_text = "\n\n".join([f"Tài liệu {i+1}:\n{doc}" for i, doc in enumerate(documents)])
            prompt = self.answer_prompt.format(
                question= question,
                structured_data=structured_data,
                documents= document_text
            )
            response = self.llm.invoke(prompt)
            final_answer = response.content
            
            state["final_prompt"] = prompt
            state["final_answer"] = final_answer
            state["curr_agent"] = "answer_generation_agent"

            WorkflowMonitor.print_state(state)
        except Exception as e:
            print(f"Error in answer generation agent: {e}")
            state["final_answer"] = "Không tìm được câu trả lời"
        
        return state

# Log the patient interation with the chatbot
class QuestionLogger:
    def __init__(self, db_path: str = r"data\logger_interaction.db"):
        self.db_path = db_path
        self.init_database()
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create the main table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_interaction (
            id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            patient_ques TEXT NOT NULL,
            patient_ques_hash TEXT NOT NULL,
            chatbot_ans TEXT NOT NULL,
            input_prompt TEXT NOT NULL,
            success BOOLEAN,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )               
        """)

        # Create table for frequent question
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS frequent_question (
            question_hash TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1,
            first_asked TEXT,
            last_asked TEXT
        )
        """)

        # Create index
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_time ON patient_interaction (timestamp)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_question ON patient_interaction (patient_ques_hash)
        """)
        conn.commit()
        conn.close()

    def generate_question_hash(self, question: str) -> str:
        normalized = " ".join(question.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def log_question(self, state: GraphRAGState, processing_time: float) -> GraphRAGState:
        try:
            question = state['question']
            id = str(uuid.uuid4())
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            question_hash = self.generate_question_hash(question = question)

            log = PatientInteraction(
                id = id,
                timestamp= timestamp,
                question= question,
                prompt= state["final_prompt"],
                chatcbot_answers= state["final_answer"],
                processing_time= processing_time,
                success= bool(state["final_answer"].strip()),
                error_message= None
            )
        
            self.save_to_database(log = log, question_hash= question_hash)
            self.update_frequent_question(question_hash= question_hash)

            state['curr_agent'] = "data_logger"
        except Exception as e:
            print(f"Error in logging question: {e}")
        

    def save_to_database(self, log: PatientInteraction, question_hash: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO patient_interaction
        (id, timestamp, patient_ques, patient_ques_hash, chatbot_ans, input_prompt)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            log.id,
            log.timestamp,
            log.question,
            question_hash,
            log.chatcbot_answers,
            log.prompt
        ))

        conn.commit()
        conn.close()
    
    def update_frequent_question(self, question_hash: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT count FROM frequent_question WHERE question_hash = ?""", (question_hash,))
        result = cursor.fetchone()
        curr_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if result:
            count = result
            new_count += 1
            # Set the new reocord
            cursor.execute("""
            UPDATE frequent_question SET count = ?, last_asked = ? WHERE question_hash = ?
            """, (new_count, curr_time, question_hash))
        else:
            # Insert new record
            cursor.execute("""
            INSERT INTO frequent_question (question_hash, count, first_asked, last_asked)
            VALUES (?, 1, ?, ?)
            """, (question_hash, curr_time, curr_time))

        conn.commit()
        conn.close()


class WorkflowMonitor:
    """Monitor and debug the workflow execution"""
    @staticmethod
    def print_state(state: GraphRAGState):
        """Print current state for debugging"""
        print(f"\n{'='*50}")
        print(f"Current Agent: {state.get('curr_agent', 'Unknown')}")
        print(f"Question: {state.get('question', '')[:100]}...")
        print(f"Entities: {state.get('entities', [])}")
        print(f"Structured Data Length: {len(state.get('structured_data', ''))}")
        print(f"Documents Count: {len(state.get('relevant_documents', []))}")
        print(f"Answer Length: {len(state.get('final_answer', ''))}")
        print(f"{'='*50}\n")


class GraphRAGWorkflow:
    def __init__(self, llm, graph, vector_idx, db_path: str = r"data\logger_interaction.db"):
        self.llm = llm
        self.graph = graph
        self.vector_idx = vector_idx
        self.logger = QuestionLogger(db_path= db_path)

        # Initialize agents
        self.entity_extraction_agent = EntityExtractionAgent(llm=llm)
        self.graph_retrieval_agent = GraphRetrievalAgent(graph=graph)
        self.document_retrieval_agent = DocumentRetrievalAgent(vector_idx=vector_idx)
        self.answer_generation_agent = AnswerGenerationAgent(llm=llm)
        self.workflow = self.workflow()

    def logging(self, state: GraphRAGState) -> GraphRAGState:
        processing_time = time.time() - state.get('processing_start_time', 0)
        return self.logger.log_question(state= state, processing_time= processing_time)


    def workflow(self):
        checkpointer = InMemorySaver()
        graph_builder = StateGraph(GraphRAGState)
        
        # Add nodes
        graph_builder.add_node("entity_extraction_agent", self.entity_extraction_agent.extract_entities)
        graph_builder.add_node("graph_retrieval_agent", self.graph_retrieval_agent.retrieve_structured_data)
        graph_builder.add_node("document_retrieval_agent", self.document_retrieval_agent.retrieve_relevant_documents)
        graph_builder.add_node("answer_generation_agent", self.answer_generation_agent.generate_answer)
        graph_builder.add_node("data_logger", self.logging)

        graph_builder.set_entry_point("entity_extraction_agent")

        # First set a sequential flow of the agents
        graph_builder.add_edge("entity_extraction_agent", "graph_retrieval_agent")
        graph_builder.add_edge("graph_retrieval_agent", "document_retrieval_agent")
        graph_builder.add_edge("document_retrieval_agent", "answer_generation_agent")
        graph_builder.add_edge("answer_generation_agent", "data_logger")
        graph_builder.add_edge("data_logger", END)
        return graph_builder.compile(checkpointer= checkpointer)
        
    def process_question(self, question: str, debug_mode: bool, chat_history: List[Tuple[str, str]] = None) -> str:
        
        # Initialize state
        initiate_state = GraphRAGState(
            processing_start_time= time.time(),
            question= question,
            chat_history= chat_history or [],
            entities= [],
            structured_data= "",
            relevant_documents= [],
            final_prompt = "",
            final_answer=  "",
            curr_agent= ""
        )
        if debug_mode:
            print(self.workflow.get_graph().draw_ascii())
        else:
            # Run the workflow 
            final_state = self.workflow.invoke(initiate_state, config = {"configurable": {"thread_id": "1"}})
            return final_state['final_answer']
    
