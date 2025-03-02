import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from langchain.chains import RetrievalQA
from langchain_google_vertexai import VertexAI
from langchain_google_community import VertexAISearchRetriever
import vertexai
from google.cloud import logging as cloud_logging
import logging

# Load environment variables
load_dotenv(override=True)

# Validate required environment variables
required_env_vars = ['PROJECT_ID', 'DATA_STORE_ID']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

app = Flask(__name__)

# Get environment variables with defaults
PROJECT_ID = os.getenv('PROJECT_ID')
LOCATION = os.getenv('LOCATION', 'us-east1')
DATA_STORE_ID = os.getenv('DATA_STORE_ID')
DATA_STORE_LOCATION = os.getenv('DATA_STORE_LOCATION', 'global')
MODEL = os.getenv('MODEL', 'gemini-1.0-pro')

# Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Initialize Cloud Logging
cloud_logging_client = cloud_logging.Client()
cloud_logging_client.setup_logging()
logger = logging.getLogger(__name__)

# Add this global variable to track initialization
qa_chain = None

def initialize_qa_chain():
    """Initialize the QA chain with Vertex AI and Search components"""
    llm = VertexAI(model_name=MODEL)

    retriever = VertexAISearchRetriever(
        project_id=PROJECT_ID,
        location_id=DATA_STORE_LOCATION,
        data_store_id=DATA_STORE_ID,
        get_extractive_answers=True,
        max_documents=10,
        max_extractive_segment_count=1,
        max_extractive_answer_count=5,
    )

    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

@app.before_request
def setup():
    """Initialize the QA chain before the first request if not already initialized"""
    global qa_chain
    if qa_chain is None:
        logger.info("Initializing QA chain")
        qa_chain = initialize_qa_chain()

@app.route('/query', methods=['POST'])
def query():
    """
    Endpoint to handle Q&A queries
    Expects JSON with format: {"question": "your question here"}
    """
    if not request.is_json:
        logger.warning("Request received without JSON content")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    question = data.get('question')

    if not question:
        logger.warning("Request received without question")
        return jsonify({"error": "No question provided"}), 400

    try:
        logger.info(f"Processing question: {question}")
        results = qa_chain.invoke(question)

        # Format source documents
        sources = []
        for doc in results["source_documents"]:
            sources.append(doc.page_content)

        logger.info("Successfully processed question")
        return jsonify({
            "answer": results["result"],
            "sources": sources
        })

    except Exception as e:
        logger.error(f"Error processing question: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)