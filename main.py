import gradio as gr
import json
import time
from typing import Dict, Any
from dataclasses import asdict
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Neo4jVector
from langchain.graphs import Neo4jGraph
from chatbot import GraphRAGWorkflow
from dotenv import load_dotenv
load_dotenv(override=True)

class WorkflowVisualizer:
    def __init__(self, workflow: GraphRAGWorkflow):
        self.workflow = workflow
        self.current_state = None
        self.step_outputs = {}
        
    def process_with_visualization(self, question: str, user_id: str) -> Dict[str, Any]:
        """Process question and capture each step's output"""
        
        # Reset step outputs
        self.step_outputs = {
            "memory_load": {"status": "pending", "output": "", "timestamp": ""},
            "entity_extraction": {"status": "pending", "output": "", "timestamp": ""},
            "graph_retrieval": {"status": "pending", "output": "", "timestamp": ""},
            "document_retrieval": {"status": "pending", "output": "", "timestamp": ""},
            "answer_generation": {"status": "pending", "output": "", "timestamp": ""},
            "memory_store": {"status": "pending", "output": "", "timestamp": ""},
        }
        
        # Initialize state
        initial_state = {
            'processing_start_time': time.time(),
            'question': question,
            'user_id': user_id,
            'chat_history': [],
            'entities': [],
            'structured_data': "",
            'relevant_documents': [],
            'final_prompt': "",
            'final_answer': "",
            'curr_agent': "",
            'user_context': ""
        }
        
        # Process step by step with monitoring
        try:
            # Step 1: Memory Load
            start_time = time.time()
            state_after_memory = self.workflow.memory_agent.load_user_context(initial_state.copy())
            self.step_outputs["memory_load"] = {
                "status": "completed",
                "output": {
                    "user_context": state_after_memory.get('user_context', 'No previous context'),
                    "user_id": user_id,
                    "context_length": len(state_after_memory.get('user_context', ''))
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": state_after_memory.get('curr_agent', 'memory_load')
            }
            
            # Step 2: Entity Extraction
            start_time = time.time()
            state_after_entities = self.workflow.entity_extraction_agent.extract_entities(state_after_memory.copy())
            self.step_outputs["entity_extraction"] = {
                "status": "completed",
                "output": {
                    "entities": state_after_entities.get('entities', []),
                    "entity_count": len(state_after_entities.get('entities', [])),
                    "user_context_used": state_after_entities.get('user_context', '')
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": state_after_entities.get('curr_agent', 'entity_extraction')
            }
            
            # Step 3: Graph Retrieval
            start_time = time.time()
            state_after_graph = self.workflow.graph_retrieval_agent.retrieve_structured_data(state_after_entities.copy())
            self.step_outputs["graph_retrieval"] = {
                "status": "completed",
                "output": {
                    "structured_data": state_after_graph.get('structured_data', 'No structured data'),
                    "data_length": len(state_after_graph.get('structured_data', '')),
                    "entities_processed": state_after_graph.get('entities', [])
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": state_after_graph.get('curr_agent', 'graph_retrieval')
            }
            
            # Step 4: Document Retrieval
            start_time = time.time()
            state_after_docs = self.workflow.document_retrieval_agent.retrieve_relevant_documents(state_after_graph.copy())
            self.step_outputs["document_retrieval"] = {
                "status": "completed",
                "output": {
                    "document_count": len(state_after_docs.get('relevant_documents', [])),
                    "documents": [doc for doc in state_after_docs.get('relevant_documents', [])],
                    "total_doc_length": sum(len(doc) for doc in state_after_docs.get('relevant_documents', []))
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": state_after_docs.get('curr_agent', 'document_retrieval')
            }
            
            # Step 5: Answer Generation
            start_time = time.time()
            state_after_answer = self.workflow.answer_generation_agent.generate_answer(state_after_docs.copy())
            self.step_outputs["answer_generation"] = {
                "status": "completed",
                "output": {
                    "final_answer": state_after_answer.get('final_answer', ''),
                    "answer_length": len(state_after_answer.get('final_answer', '')),
                    "prompt_used": state_after_answer.get('final_prompt', '')
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": state_after_answer.get('curr_agent', 'answer_generation')
            }
            
            # Step 6: Memory Store
            start_time = time.time()
            final_state = self.workflow.memory_agent.store_conversation(state_after_answer.copy())
            self.step_outputs["memory_store"] = {
                "status": "completed",
                "output": {
                    "conversation_stored": True,
                    "user_id": user_id,
                    "entities_stored": final_state.get('entities', []),
                    "timestamp_stored": time.time()
                },
                "timestamp": f"{time.time() - start_time:.2f}s",
                "agent": final_state.get('curr_agent', 'memory_store')
            }
            
            self.current_state = final_state
            return final_state
            
        except Exception as e:
            # Mark failed step
            for step, data in self.step_outputs.items():
                if data["status"] == "pending":
                    self.step_outputs[step] = {
                        "status": "error",
                        "output": f"Error: {str(e)}",
                        "timestamp": "failed",
                        "agent": "error"
                    }
                    break
            raise e

def create_gradio_interface(workflow: GraphRAGWorkflow):
    """Create Gradio interface for workflow visualization"""
    
    visualizer = WorkflowVisualizer(workflow)
    
    def process_question_with_viz(question: str, user_id: str):
        """Process question and return visualization data"""
        if not question.strip():
            return "Vui lòng nhập câu hỏi", "", "", "", "", "", "", ""
        
        if not user_id.strip():
            user_id = "anonymous_user"
        
        try:
            # Process with visualization
            final_state = visualizer.process_with_visualization(question, user_id)
            
            # Extract outputs for display
            memory_output = json.dumps(visualizer.step_outputs["memory_load"]["output"], ensure_ascii=False, indent=2)
            entity_output = json.dumps(visualizer.step_outputs["entity_extraction"]["output"], ensure_ascii=False, indent=2)
            graph_output = visualizer.step_outputs["graph_retrieval"]["output"]["structured_data"]
            doc_output = json.dumps(visualizer.step_outputs["document_retrieval"]["output"], ensure_ascii=False, indent=2)
            answer_output = visualizer.step_outputs["answer_generation"]["output"]["final_answer"]
            memory_store_output = json.dumps(visualizer.step_outputs["memory_store"]["output"], ensure_ascii=False, indent=2)
            
            # Create summary
            summary = f"""
            **Workflow Execution Summary:**
            - Memory Load: {visualizer.step_outputs["memory_load"]["timestamp"]}
            - Entity Extraction: {visualizer.step_outputs["entity_extraction"]["timestamp"]} 
            - Graph Retrieval: {visualizer.step_outputs["graph_retrieval"]["timestamp"]}
            - Document Retrieval: {visualizer.step_outputs["document_retrieval"]["timestamp"]}
            - Answer Generation: {visualizer.step_outputs["answer_generation"]["timestamp"]}
            - Memory Store: {visualizer.step_outputs["memory_store"]["timestamp"]}

            **Total Entities Found:** {len(final_state.get('entities', []))}
            **Documents Retrieved:** {len(final_state.get('relevant_documents', []))}
            **Final Answer Length:** {len(final_state.get('final_answer', ''))} characters
            """
            
            return (
                answer_output, 
                summary,       
                memory_output, 
                entity_output, 
                graph_output,  
                doc_output,    
                answer_output, 
                memory_store_output
            )
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            return error_msg
    
    def get_workflow_diagram():
        """Return workflow diagram as text"""
        return """
    📥 MEMORY LOAD
         ↓
    🔍 ENTITY EXTRACTION  
         ↓
    🕸️ GRAPH RETRIEVAL
         ↓
    📚 DOCUMENT RETRIEVAL
         ↓
    💡 ANSWER GENERATION
         ↓
    💾 MEMORY STORE
         ↓
    ✅ FINAL ANSWER
        """
    
    # Create Gradio interface
    with gr.Blocks(title="GraphRAG", theme=gr.themes.Soft()) as demo:
        
        gr.Markdown("# GraphRAG")
        gr.Markdown("Visualize each component.")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("## Workflow Diagram")
                workflow_diagram = gr.Textbox(
                    value=get_workflow_diagram(),
                    lines=10,
                    label="Processing Flow",
                    interactive=False
                )
        
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("## Input")
                question_input = gr.Textbox(
                    label="Câu hỏi y tế (Medical Question)",
                    placeholder="Tôi bị ngu",
                    lines=3
                )
                user_id_input = gr.Textbox(
                    label="User ID", 
                    placeholder="patient_123",
                    value="demo_user"
                )
                process_btn = gr.Button("Process Question", variant="primary", size="lg")
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("## Final Answer")
                final_answer = gr.Textbox(
                    label="Câu trả lời",
                    lines=8,
                    interactive=False
                )
                
                gr.Markdown("## Execution Summary")
                execution_summary = gr.Textbox(
                    label="Tóm tắt thực hiện",
                    lines=6,
                    interactive=False
                )
        
        gr.Markdown("## Step-by-Step Workflow Outputs")
        
        with gr.Tabs():
            with gr.TabItem("1️⃣ Memory Load"):
                memory_output = gr.Textbox(
                    label="User Context Loaded",
                    lines=8,
                    interactive=False
                )
                
            with gr.TabItem("2️⃣ Entity Extraction"):
                entity_output = gr.Textbox(
                    label="Medical Entities Extracted", 
                    lines=8,
                    interactive=False
                )
                
            with gr.TabItem("3️⃣ Graph Retrieval"):
                graph_output = gr.Textbox(
                    label="Knowledge Graph Data",
                    lines=12,
                    interactive=False
                )
                
            with gr.TabItem("4️⃣ Document Retrieval"):
                doc_output = gr.Textbox(
                    label="Relevant Documents",
                    lines=10,
                    interactive=False
                )
                
            with gr.TabItem("5️⃣ Answer Generation"):
                answer_gen_output = gr.Textbox(
                    label="Generated Answer",
                    lines=10,
                    interactive=False
                )
                
            with gr.TabItem("6️⃣ Memory Store"):
                memory_store_output = gr.Textbox(
                    label="Memory Storage Result",
                    lines=8,
                    interactive=False
                )
        
        # Connect the processing function
        process_btn.click(
            fn=process_question_with_viz,
            inputs=[question_input, user_id_input],
            outputs=[
                final_answer,
                execution_summary, 
                memory_output,
                entity_output,
                graph_output,
                doc_output,
                answer_gen_output,
                memory_store_output
            ]
        )
        
        # Example questions
        gr.Markdown("## Example Questions")
        example_questions = [
            "Nếu tôi bị ung thư não thì phải làm thế nào?",
            "Tôi biết 1 + 1 = 3, và tôi không sai đúng không?",
            "Nếu hút thuốc nhiều thì phổi tôi sẽ bị làm sao ?"
        ]
        
        for i, example in enumerate(example_questions):
            gr.Button(f"Example {i+1}: {example[:50]}...").click(
                lambda ex=example: (ex, "demo_user"),
                outputs=[question_input, user_id_input]
            )
    
    return demo

def main():
    """Main function to run the Gradio interface"""
    try:
        # Initialize your components (replace with actual initialization)
        base_model_name = 'keepitreal/vietnamese-sbert'
        model_kwargs = {'device': "cpu"}
        encode_kwargs = {'normalize_embeddings': False}

        llm = ChatGoogleGenerativeAI(
            model = "gemini-2.0-flash",
            temperature = 0.7,
            google_api_key = os.getenv("GEMINI_API"),
            max_retries = 3)

        graph = Neo4jGraph(
            url= os.getenv("NEO4J_URI"),
            username= os.getenv("NEO4J_USERNAME"),
            password= os.getenv("NEO4J_PASSWORD")
        )

        model_embedding = HuggingFaceEmbeddings(model_name = base_model_name,
                                                model_kwargs = model_kwargs,
                                                encode_kwargs = encode_kwargs)

        # Initialize vector search based mode label: Document and text and embedding created in Neo4j
        vector_index = Neo4jVector.from_existing_graph(
            model_embedding,
            search_type="hybrid",
            node_label="Document",
            text_node_properties=['text'],
            embedding_node_property = "embedding")

        workflow = GraphRAGWorkflow(llm, graph, vector_index)
        demo = create_gradio_interface(workflow)
        demo.launch(share=True, debug=True)
        
    except Exception as e:
        print(f"Error initializing workflow: {e}")
        print("Please ensure all dependencies are properly set up")

if __name__ == "__main__":
    main()
