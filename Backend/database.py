from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# ── Database setup ────────────────────────────────────────────────────────────
DATABASE_URL = "sqlite:///./gcek_chatbot.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # needed for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    """Stores registered students."""
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # One user has many chat sessions
    sessions = relationship("ChatSession", back_populates="user")


class ChatSession(Base):
    """A single conversation (collection of messages)."""
    __tablename__ = "chat_sessions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    title      = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)

    user     = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session")


class Message(Base):
    """A single message inside a chat session."""
    __tablename__ = "messages"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role       = Column(String, nullable=False)   # "user" or "assistant"
    content    = Column(Text, nullable=False)
    sources    = Column(Text, nullable=True)       # JSON string of sources
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class Feedback(Base):
    """Thumbs up/down on assistant messages."""
    __tablename__ = "feedback"

    id         = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    rating     = Column(String, nullable=False)   # "up" or "down"
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Create all tables ─────────────────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(bind=engine)


# ── Dependency for FastAPI routes ─────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully!")