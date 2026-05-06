from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import json
import uvicorn

from database import get_db, init_db, User, ChatSession, Message, Feedback
from auth import hash_password, verify_password, create_token, get_current_user
from rag_pipeline import ask

# ── Init database ─────────────────────────────────────────────────────────────
init_db()

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="GCEK Exam Chatbot API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    token: str
    name: str
    email: str

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[int] = None

class FeedbackRequest(BaseModel):
    message_id: int
    rating: str


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered. Please log in."
        )
    user = User(
        name=req.name,
        email=req.email,
        hashed_password=hash_password(req.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token({"sub": user.email})
    return TokenResponse(token=token, name=user.name, email=user.email)


@app.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    token = create_token({"sub": user.email})
    return TokenResponse(token=token, name=user.name, email=user.email)


@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id":    current_user.id,
        "name":  current_user.name,
        "email": current_user.email
    }


# ── Chat route ────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Create or get session
    if req.session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == req.session_id,
            ChatSession.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
    else:
        session = ChatSession(
            user_id=current_user.id,
            title=req.question[:50]
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    # Save user message first
    user_msg = Message(
        session_id=session.id,
        role="user",
        content=req.question
    )
    db.add(user_msg)
    db.commit()

    # ── Build conversation history from DB ────────────────────────────────────
    # Get all previous messages in this session (excluding the one just saved)
    prev_messages = db.query(Message).filter(
        Message.session_id == session.id,
        Message.id != user_msg.id      # exclude current message
    ).order_by(Message.created_at).all()

    # Format history for RAG pipeline
    history = []
    for m in prev_messages[-6:]:      # last 6 messages = 3 exchanges
        history.append({
            "role":    "user" if m.role == "user" else "assistant",
            "content": m.content
        })

    # ── Run RAG pipeline with history ─────────────────────────────────────────
    try:
        result = ask(req.question, history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Save assistant response
    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=result["answer"],
        sources=json.dumps(result["sources"])
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "answer":     result["answer"],
        "sources":    result["sources"],
        "session_id": session.id,
        "message_id": assistant_msg.id
    }


# ── Chat history routes ───────────────────────────────────────────────────────

@app.get("/sessions")
def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id
    ).order_by(ChatSession.created_at.desc()).all()

    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}
        for s in sessions
    ]


@app.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.created_at).all()

    return [
        {
            "id":      m.id,
            "role":    m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else []
        }
        for m in messages
    ]


@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "Session deleted."}


# ── Feedback ──────────────────────────────────────────────────────────────────

@app.post("/feedback")
def submit_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if req.rating not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'.")
    feedback = Feedback(message_id=req.message_id, rating=req.rating)
    db.add(feedback)
    db.commit()
    return {"message": "Feedback submitted!"}


@app.get("/")
def root():
    return {"status": "GCEK Exam Chatbot API v2.0 is running!"}


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)