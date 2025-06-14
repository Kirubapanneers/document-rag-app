# Document RAG App

A secure, scalable, full-stack application for uploading, storing, and querying documents (PDF, PPT, CSV, DOCX, etc.) using advanced NLP and RAG (Retrieve and Generate) agents. Built as per the [Full-Stack Developer Assignment](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/53029497/287db915-d90b-4355-81a1-9216a5f5714c/Full-Stack-Developer-Assignment.pdf).

---

## Table of Contents

- [Objective](#objective)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [Database Schema & Low-Level Design](#database-schema--low-level-design)
- [Setup & Deployment](#setup--deployment)
- [API Documentation](#api-documentation)
- [Assignment Requirements Checklist](#assignment-requirements-checklist)
- [Demo](#demo)
- [Security & Best Practices](#security--best-practices)
- [Credits](#credits)
- [License](#license)

---

## Objective

Develop a secure, scalable, full-stack application that allows users to upload, store, and interact with any type of documents (PDF, PPT, CSV, DOCX, etc.) through advanced natural language processing (NLP) and implement a RAG Agent to do querying for any question the user has.  
The application supports document management, user authentication, and efficient RAG agents, and utilizes unstructured.io for efficient parsing of document content[1].

---

## Features

- **User Authentication**: Secure session-based login and registration.
- **Document Upload & Management**: Upload, list, and delete multi-format documents.
- **Advanced Document Parsing**: Integration with [unstructured.io](https://unstructured.io/) for extracting text and metadata.
- **RAG Querying**: Contextual Q&A over uploaded documents using Gemini (Google) LLM and LangChain.
- **Full-Text Search**: Elasticsearch for semantic and keyword search.
- **Scalable & Secure**: Containerized with Docker, ready for Kubernetes.
- **Cloud Storage**: Uses MinIO (S3-compatible) for document storage[2].

---

## Tech Stack

- **Frontend**: React.js (Vite)
- **Backend**: FastAPI (Python)
- **NLP Processing**: LangChain, Gemini (Google Generative AI)
- **Database**: PostgreSQL
- **Cache/Session**: Redis
- **File Storage**: MinIO (S3-compatible)[2]
- **Document Parsing**: unstructured.io
- **Search Engine**: Elasticsearch
- **Deployment**: Docker, Docker Compose, (Optional) Kubernetes
- **Monitoring/Logging (Optional)**: Prometheus, Grafana, ELK Stack

---

## Architecture Overview

**Main Components:**
- **Client**: React app ([http://localhost:5173](http://localhost:5173))
- **API**: FastAPI backend ([http://localhost:8000](http://localhost:8000))
- **DB**: PostgreSQL for users, documents, queries
- **Cache**: Redis for session management
- **Storage**: MinIO for document files[2]
- **Search**: Elasticsearch for full-text and semantic queries
- **Parsing**: unstructured.io for extracting content from files
- **NLP**: Gemini LLM via LangChain for RAG-based Q&A


[User] <---> [React Client] <--REST/Session--> [FastAPI Backend] <---> [PostgreSQL, Redis, MinIO, Elasticsearch, unstructured.io, Gemini]


---

## Database Schema & Low-Level Design

**Tables:**
- `users`: id, username, email, password_hash, created_at
- `documents`: id, user_id (FK), file_name, file_path, file_type, doc_metadata, content, created_at
- `queries`: id, user_id (FK), document_id (FK), query_text, response_text, created_at

**Relationships:**
- Each document belongs to a user.
- Each query is linked to a user and a document.

**Class Structure:**
- `User`: Handles registration, login, and session management.
- `Document`: Handles upload, parsing, storage, and deletion.
- `Query`: Handles user queries, RAG agent invocation, and stores Q&A history.

**Functions & Interactions:**
- Document upload triggers parsing (unstructured.io), storage (MinIO), and indexing (Elasticsearch).
- Query endpoint retrieves and generates answers using LangChain and Gemini based on indexed content.

---

## Setup & Deployment

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/)
- (Optional) [Kubernetes](https://kubernetes.io/) for advanced deployment

### 1. Clone the Repository

git clone https://github.com/yourusername/document-rag-app.git
cd document-rag-app


### 2. Set Environment Variables

Create a `.env` file in the project root (or edit `docker-compose.yml`):

GEMINI_API_KEY=your_gemini_api_key



### 3. Build and Run All Services

docker compose up --build


- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **MinIO Console**: [http://localhost:9001](http://localhost:9001) 
- **Elasticsearch**: [http://localhost:9200](http://localhost:9200)

### 4. Test the Application

- Register and log in.
- Upload documents (PDF, PPT, CSV, DOCX, etc.).
- Ask questions about uploaded documents.
- List and delete documents as needed.

---

## API Documentation

Interactive API docs available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Example: Register

POST /register
Content-Type: application/json

{
"username": "testuser",
"email": "test@email.com",
"password": "testpass"
}


### Example: Login

POST /login
Content-Type: application/json

{
"username": "testuser",
"password": "testpass"
}



### Example: Upload Document

`POST /upload` (multipart/form-data, requires authentication)

---

## Assignment Requirements Checklist

- [x] Secure user authentication and session management
- [x] Multi-format document upload and parsing (unstructured.io)
- [x] RAG agent integration (LangChain + Gemini)
- [x] Full-text search (Elasticsearch)
- [x] Dockerized deployment (Compose)
- [x] LLD diagrams and documentation
- [x] Demo video or live link

---

## Demo

- [Demo Video Link](https://your-demo-link.com)
- (Optional) [Live Demo](https://your-live-demo-url.com)

---

## Security & Best Practices

- Passwords hashed with bcrypt
- Session-based authentication via Redis
- All secrets managed via environment variables
- Containers isolated and orchestrated with Docker Compose

---

## Credits

- Assignment by [Your Institution/Instructor]
- Built by [Your Name]
- Powered by open-source: FastAPI, React, LangChain, Gemini, unstructured.io, PostgreSQL, Redis, MinIO, Elasticsearch

---

## License

MIT
 
