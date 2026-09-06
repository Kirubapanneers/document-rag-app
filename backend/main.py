import os
import io
import uuid
import json
import logging
import re

from datetime import datetime
from typing import Optional, List

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Depends,
    HTTPException,
    Request,
    Response,
    status
)
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, EmailStr, field_validator

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Text
)
from sqlalchemy.orm import (
    sessionmaker,
    relationship,
    Session,
    declarative_base
)

from minio import Minio
from minio.error import S3Error

from unstructured.partition.auto import partition

from elasticsearch import Elasticsearch

from bcrypt import hashpw, gensalt, checkpw

import redis

# LangChain + Gemini
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings
)
from langchain_core.messages import HumanMessage

# Recursive chunking
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")

DEFAULT_BUCKET = os.getenv(
    "MINIO_BUCKET",
    "kirubabucket"
)


# ============================================================
# DATABASE SETUP
# ============================================================

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# ============================================================
# DATABASE MODELS
# ============================================================

class User(Base):

    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    username = Column(
        String(50),
        unique=True,
        index=True
    )

    email = Column(
        String(100),
        unique=True,
        index=True
    )

    password_hash = Column(
        String(128)
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    documents = relationship(
        "Document",
        back_populates="user"
    )

    queries = relationship(
        "Query",
        back_populates="user"
    )


class Document(Base):

    __tablename__ = "documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    file_name = Column(
        String(255)
    )

    file_path = Column(
        String(512)
    )

    file_type = Column(
        String(50)
    )

    doc_metadata = Column(
        Text
    )

    content = Column(
        Text
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    user = relationship(
        "User",
        back_populates="documents"
    )

    queries = relationship(
        "Query",
        back_populates="document"
    )


class Query(Base):

    __tablename__ = "queries"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id")
    )

    query_text = Column(
        Text
    )

    response_text = Column(
        Text
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    document = relationship(
        "Document",
        back_populates="queries"
    )

    user = relationship(
        "User",
        back_populates="queries"
    )


Base.metadata.create_all(
    bind=engine
)


# ============================================================
# REDIS SETUP
# ============================================================

redis_host = "redis"
redis_port = 6379
redis_db = 0

if REDIS_URL:

    match = re.match(
        r"redis://([^:/]+):(\d+)(?:/(\d+))?",
        REDIS_URL
    )

    if match:

        redis_host = match.group(1)

        redis_port = int(
            match.group(2)
        )

        if match.group(3):

            redis_db = int(
                match.group(3)
            )


redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    db=redis_db
)


# ============================================================
# MINIO CLIENT
# ============================================================

minio_client = Minio(

    MINIO_ENDPOINT,

    access_key=MINIO_ACCESS_KEY,

    secret_key=MINIO_SECRET_KEY,

    secure=False
)


try:

    if not minio_client.bucket_exists(
        DEFAULT_BUCKET
    ):

        minio_client.make_bucket(
            DEFAULT_BUCKET
        )

        logger.info(
            f"Bucket '{DEFAULT_BUCKET}' created successfully."
        )

except S3Error as exc:

    logger.error(
        f"Error creating Minio bucket: {exc}"
    )


# ============================================================
# ELASTICSEARCH CLIENT
# ============================================================

es = Elasticsearch(
    [ELASTICSEARCH_URL]
)


INDEX_NAME = "document_chunks"


try:

    if not es.ping():

        raise ValueError(
            "Connection to Elasticsearch failed!"
        )

    logger.info(
        "Connected to Elasticsearch successfully."
    )

except Exception as e:

    logger.error(
        f"Could not connect to Elasticsearch: {e}"
    )


# ============================================================
# GEMINI EMBEDDING MODEL
# ============================================================

embeddings = GoogleGenerativeAIEmbeddings(

    model="models/gemini-embedding-001",

    google_api_key=GEMINI_API_KEY
)


# ============================================================
# GEMINI LLM
# ============================================================

llm = ChatGoogleGenerativeAI(

    google_api_key=GEMINI_API_KEY,

    model="models/gemini-2.0-flash-lite-preview"
)


# ============================================================
# RECURSIVE CHUNKING
# ============================================================

text_splitter = RecursiveCharacterTextSplitter(

    chunk_size=800,

    chunk_overlap=150,

    separators=[
        "\n\n",
        "\n",
        ". ",
        " ",
        ""
    ]
)


# ============================================================
# CREATE ELASTICSEARCH INDEX
# ============================================================

def create_elasticsearch_index():

    try:

        if es.indices.exists(
            index=INDEX_NAME
        ):

            logger.info(
                f"Elasticsearch index '{INDEX_NAME}' already exists."
            )

            return

        index_mapping = {

            "mappings": {

                "properties": {

                    "document_id": {
                        "type": "integer"
                    },

                    "user_id": {
                        "type": "integer"
                    },

                    "file_name": {
                        "type": "keyword"
                    },

                    "chunk_id": {
                        "type": "integer"
                    },

                    "content": {
                        "type": "text"
                    },

                    "embedding": {
                        "type": "dense_vector",

                        "dims": 3072,

                        "index": True,

                        "similarity": "cosine"
                    },

                    "created_at": {
                        "type": "date"
                    }
                }
            }
        }

        es.indices.create(

            index=INDEX_NAME,

            body=index_mapping
        )

        logger.info(
            f"Elasticsearch index '{INDEX_NAME}' created."
        )

    except Exception as e:

        logger.error(
            f"Error creating Elasticsearch index: {e}",
            exc_info=True
        )


create_elasticsearch_index()


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(

    title="Document Management API",

    description=(
        "API for document management and "
        "RAG-based semantic search"
    ),

    version="2.0.0"
)


app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

    expose_headers=[
        "Content-Disposition"
    ]
)


# ============================================================
# PYDANTIC MODELS
# ============================================================

class UserCreate(BaseModel):

    username: str

    email: EmailStr

    password: str

    @field_validator("email")
    @classmethod
    def email_must_be_gmail(cls, v):

        if not v.endswith("@gmail.com"):

            raise ValueError(
                "Only @gmail.com emails allowed"
            )

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


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()


# ============================================================
# PASSWORD FUNCTIONS
# ============================================================

def get_password_hash(
    password: str
) -> str:

    return hashpw(
        password.encode("utf-8"),
        gensalt()
    ).decode("utf-8")


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:

    return checkpw(

        plain_password.encode("utf-8"),

        hashed_password.encode("utf-8")
    )


# ============================================================
# SESSION MANAGEMENT
# ============================================================

SESSION_EXPIRATION_SECONDS = 3600


async def create_session(
    user_id: int
) -> str:

    session_id = str(
        uuid.uuid4()
    )

    redis_client.setex(

        f"session:{session_id}",

        SESSION_EXPIRATION_SECONDS,

        str(user_id)
    )

    return session_id


async def get_user_from_session(
    session_id: str,
    db: Session
) -> Optional[User]:

    user_id_str = redis_client.get(
        f"session:{session_id}"
    )

    if user_id_str:

        user_id = int(
            user_id_str
        )

        user = db.query(User).filter(
            User.id == user_id
        ).first()

        if user:

            redis_client.expire(

                f"session:{session_id}",

                SESSION_EXPIRATION_SECONDS
            )

        return user

    return None


async def get_current_user(

    request: Request,

    db: Session = Depends(get_db)

) -> User:

    session_id = request.cookies.get(
        "session_id"
    )

    if not session_id:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Not authenticated"
        )

    user = await get_user_from_session(
        session_id,
        db
    )

    if not user:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Invalid session"
        )

    return user


# ============================================================
# AUTHENTICATION
# ============================================================

@app.post(
    "/register",
    status_code=201
)
def register_user(

    user: UserCreate,

    db: Session = Depends(get_db)

):

    db_user = db.query(User).filter(
        User.username == user.username
    ).first()

    if db_user:

        raise HTTPException(

            status_code=400,

            detail="Username already registered"
        )

    hashed_password = get_password_hash(
        user.password
    )

    new_user = User(

        username=user.username,

        email=user.email,

        password_hash=hashed_password
    )

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

    return {

        "username": user.username,

        "email": user.email
    }


@app.post("/login")
async def login_user(

    response: Response,

    user_login: UserLogin,

    db: Session = Depends(get_db)

):

    user = db.query(User).filter(

        User.username == user_login.username

    ).first()

    if (
        not user
        or not verify_password(
            user_login.password,
            user.password_hash
        )
    ):

        raise HTTPException(

            status_code=400,

            detail="Incorrect username or password"
        )

    session_id = await create_session(
        user.id
    )

    response.set_cookie(

        key="session_id",

        value=session_id,

        httponly=True,

        samesite="Lax",

        max_age=SESSION_EXPIRATION_SECONDS
    )

    return {
        "message": "Login successful"
    }


@app.get("/me")
async def get_my_info(

    user: User = Depends(get_current_user)

):

    return {

        "username": user.username,

        "email": user.email
    }


@app.post("/logout")
async def logout_user(

    response: Response,

    request: Request

):

    session_id = request.cookies.get(
        "session_id"
    )

    if session_id:

        redis_client.delete(
            f"session:{session_id}"
        )

    response.delete_cookie(
        key="session_id"
    )

    return {
        "message": "Logout successful"
    }


# ============================================================
# EMBEDDING HELPER
# ============================================================

def generate_embedding(
    text: str
) -> List[float]:

    try:

        vector = embeddings.embed_query(
            text
        )

        return vector

    except Exception as e:

        logger.error(
            f"Embedding generation failed: {e}",
            exc_info=True
        )

        raise


# ============================================================
# INDEX DOCUMENT CHUNKS
# ============================================================

def index_document_chunks(

    document_id: int,

    user_id: int,

    file_name: str,

    chunks: List[str],

    created_at: datetime

):

    for chunk_id, chunk in enumerate(chunks):

        embedding = generate_embedding(
            chunk
        )

        es.index(

            index=INDEX_NAME,

            document={

                "document_id": document_id,

                "user_id": user_id,

                "file_name": file_name,

                "chunk_id": chunk_id,

                "content": chunk,

                "embedding": embedding,

                "created_at": created_at
            }
        )

    es.indices.refresh(
        index=INDEX_NAME
    )

    logger.info(

        f"Indexed {len(chunks)} chunks "
        f"for document {document_id}"
    )


# ============================================================
# VECTOR SEARCH
# ============================================================

def semantic_search(

    query: str,

    document_id: int,

    user_id: int,

    top_k: int = 5

):

    query_embedding = generate_embedding(
        query
    )

    response = es.search(

        index=INDEX_NAME,

        knn={

            "field": "embedding",

            "query_vector": query_embedding,

            "k": top_k,

            "num_candidates": 50,

            "filter": [

                {
                    "term": {
                        "document_id": document_id
                    }
                },

                {
                    "term": {
                        "user_id": user_id
                    }
                }
            ]
        },

        size=top_k
    )

    return response["hits"]["hits"]


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@app.post(
    "/upload",
    response_model=DocumentResponse
)
async def upload_document(

    file: UploadFile = File(...),

    user: User = Depends(
        get_current_user
    ),

    db: Session = Depends(get_db)

):

    try:

        # ----------------------------------------------------
        # 1. READ FILE
        # ----------------------------------------------------

        file_content = await file.read()

        if not file_content:

            raise HTTPException(

                status_code=400,

                detail="Uploaded file is empty"
            )


        # ----------------------------------------------------
        # 2. STORE ORIGINAL FILE IN MINIO
        # ----------------------------------------------------

        object_name = (

            f"{user.id}/"
            f"{uuid.uuid4()}-"
            f"{file.filename}"
        )

        minio_client.put_object(

            DEFAULT_BUCKET,

            object_name,

            io.BytesIO(file_content),

            len(file_content),

            content_type=file.content_type
        )

        logger.info(

            f"File '{object_name}' uploaded to Minio."
        )


        # ----------------------------------------------------
        # 3. EXTRACT TEXT
        # ----------------------------------------------------

        elements = partition(

            file=io.BytesIO(file_content),

            content_type=file.content_type
        )

        extracted_parts = []

        for element in elements:

            text = getattr(
                element,
                "text",
                None
            )

            if text:

                extracted_parts.append(
                    text
                )

        full_content = "\n\n".join(
            extracted_parts
        )


        if not full_content.strip():

            raise HTTPException(

                status_code=400,

                detail=(
                    "Could not extract text "
                    "from the uploaded document."
                )
            )


        # ----------------------------------------------------
        # 4. SAVE DOCUMENT METADATA TO POSTGRESQL
        # ----------------------------------------------------

        new_doc = Document(

            user_id=user.id,

            file_name=file.filename,

            file_path=object_name,

            file_type=file.content_type,

            doc_metadata=json.dumps({

                "size": len(file_content),

                "parsed_elements_count": len(elements)
            }),

            content=full_content
        )

        db.add(new_doc)

        db.commit()

        db.refresh(new_doc)


        logger.info(

            f"Document '{new_doc.id}' saved to PostgreSQL."
        )


        # ----------------------------------------------------
        # 5. RECURSIVE CHUNKING
        # ----------------------------------------------------

        chunks = text_splitter.split_text(
            full_content
        )

        logger.info(

            f"Document {new_doc.id} "
            f"split into {len(chunks)} chunks."
        )


        # ----------------------------------------------------
        # 6. CREATE GEMINI EMBEDDINGS
        # 7. STORE CHUNKS + VECTORS IN ELASTICSEARCH
        # ----------------------------------------------------

        index_document_chunks(

            document_id=new_doc.id,

            user_id=user.id,

            file_name=new_doc.file_name,

            chunks=chunks,

            created_at=new_doc.created_at
        )


        # ----------------------------------------------------
        # 8. RESPONSE
        # ----------------------------------------------------

        return DocumentResponse(

            id=new_doc.id,

            file_name=new_doc.file_name,

            file_type=new_doc.file_type,

            created_at=new_doc.created_at
        )


    except S3Error as exc:

        logger.error(
            f"Minio S3 Error: {exc}"
        )

        raise HTTPException(

            status_code=500,

            detail=f"File upload failed: {exc}"
        )


    except HTTPException:

        raise


    except Exception as e:

        logger.error(

            f"Upload error: {e}",

            exc_info=True
        )

        raise HTTPException(

            status_code=500,

            detail=(
                f"Document processing failed: {e}"
            )
        )


# ============================================================
# LIST DOCUMENTS
# ============================================================

@app.get(
    "/documents",
    response_model=List[DocumentResponse]
)
async def list_documents(

    user: User = Depends(
        get_current_user
    ),

    db: Session = Depends(get_db)

):

    docs = db.query(Document).filter(

        Document.user_id == user.id

    ).all()

    return [

        DocumentResponse(

            id=doc.id,

            file_name=doc.file_name,

            file_type=doc.file_type,

            created_at=doc.created_at

        )

        for doc in docs
    ]


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete(
    "/documents/{document_id}"
)
async def delete_document(

    document_id: int,

    user: User = Depends(
        get_current_user
    ),

    db: Session = Depends(get_db)

):

    document = db.query(Document).filter(

        Document.id == document_id,

        Document.user_id == user.id

    ).first()


    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"
        )


    try:

        # ----------------------------------------------------
        # 1. DELETE ORIGINAL FILE FROM MINIO
        # ----------------------------------------------------

        minio_client.remove_object(

            DEFAULT_BUCKET,

            document.file_path
        )


        # ----------------------------------------------------
        # 2. DELETE ALL CHUNKS FROM ELASTICSEARCH
        # ----------------------------------------------------

        es.delete_by_query(

            index=INDEX_NAME,

            query={

                "bool": {

                    "filter": [

                        {
                            "term": {
                                "document_id": document.id
                            }
                        },

                        {
                            "term": {
                                "user_id": user.id
                            }
                        }
                    ]
                }
            }
        )


        # ----------------------------------------------------
        # 3. DELETE DOCUMENT FROM POSTGRESQL
        # ----------------------------------------------------

        db.delete(document)

        db.commit()


        logger.info(

            f"Document '{document.id}' deleted."
        )


        return {

            "message":
                "Document deleted successfully"
        }


    except Exception as e:

        logger.error(

            f"Delete error: {e}",

            exc_info=True
        )

        raise HTTPException(

            status_code=500,

            detail=(
                f"Document deletion failed: {e}"
            )
        )


# ============================================================
# QUERY / RAG ENDPOINT
# ============================================================

@app.post(
    "/query",
    response_model=QueryResponse
)
async def query_document(

    req: QueryRequest,

    user: User = Depends(
        get_current_user
    ),

    db: Session = Depends(get_db)

):

    # --------------------------------------------------------
    # 1. VERIFY DOCUMENT BELONGS TO USER
    # --------------------------------------------------------

    document = db.query(Document).filter(

        Document.id == req.document_id,

        Document.user_id == user.id

    ).first()


    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"
        )


    try:

        # ----------------------------------------------------
        # 2. SEMANTIC VECTOR SEARCH
        # ----------------------------------------------------

        results = semantic_search(

            query=req.query_text,

            document_id=req.document_id,

            user_id=user.id,

            top_k=5
        )


        if not results:

            raise HTTPException(

                status_code=404,

                detail=(
                    "No relevant information "
                    "found in the document."
                )
            )


        # ----------------------------------------------------
        # 3. BUILD CONTEXT FROM TOP 5 CHUNKS
        # ----------------------------------------------------

        retrieved_chunks = []

        for hit in results:

            source = hit["_source"]

            retrieved_chunks.append(

                f"[Chunk {source['chunk_id']}]\n"
                f"{source['content']}"
            )


        context = "\n\n".join(
            retrieved_chunks
        )


        # ----------------------------------------------------
        # 4. RAG PROMPT
        # ----------------------------------------------------

        prompt = f"""
You are a document question-answering assistant.

Answer the user's question using ONLY the
provided document context.

Do not use outside knowledge.

Do not make up information.

If the answer cannot be found in the
provided context, say:

"I couldn't find this information in the document."

Document Context:
-----------------
{context}
-----------------

User Question:
{req.query_text}

Answer:
"""


        # ----------------------------------------------------
        # 5. GEMINI GENERATION
        # ----------------------------------------------------

        response = llm.invoke(

            [
                HumanMessage(
                    content=prompt
                )
            ]
        )


        answer = response.content


        # ----------------------------------------------------
        # 6. SAVE QUERY + ANSWER
        # ----------------------------------------------------

        new_query = Query(

            user_id=user.id,

            document_id=document.id,

            query_text=req.query_text,

            response_text=answer
        )

        db.add(new_query)

        db.commit()

        db.refresh(new_query)


        # ----------------------------------------------------
        # 7. RETURN RESPONSE
        # ----------------------------------------------------

        return QueryResponse(

            response_text=answer,

            document_id=document.id,

            created_at=new_query.created_at
        )


    except HTTPException:

        raise


    except Exception as e:

        logger.error(

            f"Query error: {e}",

            exc_info=True
        )

        raise HTTPException(

            status_code=500,

            detail=f"Query failed: {e}"
        )