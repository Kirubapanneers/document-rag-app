import os
import io
import uuid
import json
import logging
from datetime import datetime
from typing import Optional, List
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from pydantic import BaseModel, EmailStr, field_validator
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from pydantic import BaseModel
from minio import Minio
from minio.error import S3Error
from unstructured.partition.auto import partition
from elasticsearch import Elasticsearch
from bcrypt import hashpw, gensalt, checkpw
import redis

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
DEFAULT_BUCKET = os.getenv("MINIO_BUCKET", "kirubabucket")

# --- Database Setup (PostgreSQL) ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    password_hash = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)
    documents = relationship("Document", back_populates="user")
    queries = relationship("Query", back_populates="user")

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_name = Column(String(255))
    file_path = Column(String(512))  # Path in Minio
    file_type = Column(String(50))
    doc_metadata = Column(Text)      # Store metadata as JSON string
    content = Column(Text)           # Store extracted text content
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="documents")
    queries = relationship("Query", back_populates="document")

class Query(Base):
    __tablename__ = "queries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    document_id = Column(Integer, ForeignKey("documents.id"))
    query_text = Column(Text)
    response_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    document = relationship("Document", back_populates="queries")
    user = relationship("User", back_populates="queries")

Base.metadata.create_all(bind=engine)

# --- Robust Redis URL Parsing ---
redis_host = 'redis'
redis_port = 6379
redis_db = 0
if REDIS_URL:
    # Example: redis://redis:6379/0
    match = re.match(r"redis://([^:/]+):(\d+)(?:/(\d+))?", REDIS_URL)
    if match:
        redis_host = match.group(1)
        redis_port = int(match.group(2))
        if match.group(3):
            redis_db = int(match.group(3))

redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

# --- Minio Client (S3-compatible storage) ---
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)
try:
    if not minio_client.bucket_exists(DEFAULT_BUCKET):
        minio_client.make_bucket(DEFAULT_BUCKET)
        logger.info(f"Bucket '{DEFAULT_BUCKET}' created successfully in Minio.")
except S3Error as exc:
    logger.error(f"Error creating Minio bucket: {exc}")

# --- Elasticsearch Client ---
es = Elasticsearch([ELASTICSEARCH_URL])
try:
    if not es.ping():
        raise ValueError("Connection to Elasticsearch failed!")
    logger.info("Connected to Elasticsearch successfully.")
except Exception as e:
    logger.error(f"Could not connect to Elasticsearch: {e}")

# --- FastAPI App Instance ---
app = FastAPI(
    title="Document Management API",
    description="API for managing documents and performing semantic search",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Update if your frontend origin changes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# --- Pydantic Models ---




class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator('email')
    @classmethod
    def email_must_be_gmail(cls, v):
        if not v.endswith('@gmail.com'):
            raise ValueError('Only @gmail.com emails allowed')
        return v


class UserLogin(BaseModel):
    username: str
    password: str

class QueryRequest(BaseModel):
    document_id: int
    query_text: str

class QueryResponse(BaseModel):
    response_text: str
    document_id: int
    created_at: datetime

class DocumentResponse(BaseModel):
    id: int
    file_name: str
    file_type: str
    created_at: datetime

# --- Dependency Functions ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password: str) -> str:
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

SESSION_EXPIRATION_SECONDS = 3600

async def create_session(user_id: int) -> str:
    session_id = str(uuid.uuid4())
    redis_client.setex(f"session:{session_id}", SESSION_EXPIRATION_SECONDS, str(user_id))
    return session_id

async def get_user_from_session(session_id: str, db: Session) -> Optional[User]:
    user_id_str = redis_client.get(f"session:{session_id}")
    if user_id_str:
        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            redis_client.expire(f"session:{session_id}", SESSION_EXPIRATION_SECONDS)
        return user
    return None

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await get_user_from_session(session_id, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user

# --- Authentication Endpoints ---
@app.post("/register", status_code=201)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, email=user.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"username": user.username, "email": user.email}

@app.post("/login")
async def login_user(response: Response, user_login: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_login.username).first()
    if not user or not verify_password(user_login.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    session_id = await create_session(user.id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="Lax", max_age=SESSION_EXPIRATION_SECONDS)
    return {"message": "Login successful"}

@app.get("/me")
async def get_my_info(user: User = Depends(get_current_user)):
    return {"username": user.username, "email": user.email}

@app.post("/logout")
async def logout_user(response: Response, request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        redis_client.delete(f"session:{session_id}")
    response.delete_cookie(key="session_id")
    return {"message": "Logout successful"}

# --- Document Management Endpoints ---
@app.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        object_name = f"{user.id}/{uuid.uuid4()}-{file.filename}"
        file_content = await file.read()
        minio_client.put_object(DEFAULT_BUCKET, object_name, io.BytesIO(file_content), len(file_content), content_type=file.content_type)
        logger.info(f"File '{object_name}' uploaded to Minio.")

        elements = partition(file=io.BytesIO(file_content), content_type=file.content_type)
        full_content = "\n\n".join([str(el) for el in elements if hasattr(el, 'text')])

        new_doc = Document(
            user_id=user.id,
            file_name=file.filename,
            file_path=object_name,
            file_type=file.content_type,
            doc_metadata=json.dumps({"size": len(file_content), "parsed_elements_count": len(elements)}),
            content=full_content
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        logger.info(f"Document '{new_doc.id}' saved to DB.")

        es.index(index="documents", id=new_doc.id, document={
            "document_id": new_doc.id,
            "user_id": user.id,
            "file_name": new_doc.file_name,
            "content": full_content,
            "created_at": new_doc.created_at
        })
        logger.info(f"Document '{new_doc.id}' indexed in Elasticsearch.")

        return DocumentResponse(
            id=new_doc.id,
            file_name=new_doc.file_name,
            file_type=new_doc.file_type,
            created_at=new_doc.created_at
        )
    except S3Error as exc:
        logger.error(f"Minio S3 Error: {exc}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {exc}")
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

@app.get("/documents", response_model=List[DocumentResponse])
async def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.user_id == user.id).all()
    return [
        DocumentResponse(
            id=doc.id,
            file_name=doc.file_name,
            file_type=doc.file_type,
            created_at=doc.created_at
        ) for doc in docs
    ]

@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        minio_client.remove_object(DEFAULT_BUCKET, document.file_path)
        db.delete(document)
        db.commit()
        es.delete(index="documents", id=document.id, ignore=[404])
        logger.info(f"Document '{document.id}' deleted.")
        return {"message": "Document deleted successfully"}
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document deletion failed: {e}")

# --- Query Endpoint (RAG) ---

@app.post("/query", response_model=QueryResponse)
async def query_document(
    req: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == req.document_id, Document.user_id == user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        # Use Gemini LLM via LangChain for RAG
        llm = ChatGoogleGenerativeAI(google_api_key=GEMINI_API_KEY, model="models/gemini-2.0-flash-lite-preview")  # or the correct model name

        prompt = f"Document Content:\n{document.content}\n\nUser Query: {req.query_text}\n\nAnswer:"
        response = llm([HumanMessage(content=prompt)])
        answer = response.content if hasattr(response, "content") else str(response)

        # Save query and response in DB
        new_query = Query(
            user_id=user.id,
            document_id=document.id,
            query_text=req.query_text,
            response_text=answer
        )
        db.add(new_query)
        db.commit()
        db.refresh(new_query)

        return QueryResponse(
            response_text=answer,
            document_id=document.id,
            created_at=new_query.created_at
        )
    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
