import os
import chromadb
from groq import Groq
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file. Please add it.")

# ── Groq client ───────────────────────────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL  = "llama-3.3-70b-versatile"

# ── Embedding model ───────────────────────────────────────────────────────────
print("Loading embedding model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
print("Embedding model ready.\n")

# ── ChromaDB ──────────────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection    = chroma_client.get_or_create_collection("gcek_exam_rules")
print(f"Connected to ChromaDB. {collection.count()} chunks available.\n")

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful assistant for GCEK (Government College of Engineering Kannur) students.
You have access to the official GCEK exam rules and regulations documents.

You have two modes:

1. EXAM RULES MODE: When a student asks about GCEK exam rules, attendance, hall tickets, malpractice,
   grading, ESE, or any college regulation — answer strictly from the provided document context.
   If not found in context, say "I couldn't find this in the GCEK exam rules documents."

2. GENERAL MODE: When a student asks general questions like greetings, general knowledge, or anything
   not related to exam rules — answer freely and helpfully.

IMPORTANT: You have memory of the conversation. Use previous messages to understand follow-up questions.
For example if someone asked about ESE and then asks "how many marks does it carry", you know "it" = ESE.

Always be friendly, clear and use simple language. You are talking to engineering students at GCEK.
"""


def retrieve_relevant_chunks(question: str, history: list, top_k: int = 5) -> list:
    """
    Embed the question (enriched with recent history for better context)
    and find the most relevant chunks from ChromaDB.
    """
    # Enrich query with last user message for better context on follow-ups
    enriched_query = question
    if history:
        last_user_msgs = [m["content"] for m in history if m["role"] == "user"]
        if last_user_msgs:
            # Combine last question + current for better semantic search
            enriched_query = last_user_msgs[-1] + " " + question

    question_embedding = embedding_model.encode([enriched_query]).tolist()[0]

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    for i in range(len(results["documents"][0])):
        chunks.append({
            "text":     results["documents"][0][i],
            "source":   results["metadatas"][0][i]["source"],
            "page":     results["metadatas"][0][i]["page"],
            "distance": results["distances"][0][i]
        })

    return chunks


def build_context(chunks: list) -> str:
    """Format retrieved chunks into a clean context string."""
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[Source: {chunk['source']}, Page {chunk['page']}]\n{chunk['text']}"
        )
    return "\n\n---\n\n".join(context_parts)


def ask(question: str, history: list = []) -> dict:
    """
    Main RAG function with conversation memory.

    Args:
        question: The current question from the student
        history:  List of previous messages in format
                  [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        dict with "answer" and "sources"
    """
    # Step 1: Retrieve relevant chunks (uses history for better context)
    chunks = retrieve_relevant_chunks(question, history, top_k=5)

    # Step 2: Build context from chunks
    context = build_context(chunks) if chunks else "No relevant context found."

    # Step 3: Build the current user message with context
    user_message = f"""Here is relevant context from the GCEK exam rules documents:

{context}

Student's question: {question}"""

    # Step 4: Build full message list with history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history (last 6 messages = 3 back-and-forth exchanges)
    for msg in history[-6:]:
        messages.append({
            "role":    msg["role"],
            "content": msg["content"]
        })

    # Add current question (with context attached)
    messages.append({"role": "user", "content": user_message})

    # Step 5: Call Groq with full conversation
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content.strip()

    # Step 6: Collect unique sources
    sources = []
    seen = set()
    for chunk in chunks:
        key = f"{chunk['source']}_p{chunk['page']}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "file": chunk["source"],
                "page": chunk["page"]
            })

    return {
        "answer":  answer,
        "sources": sources
    }


# ── Test mode ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("GCEK Exam Chatbot — Conversation Memory Test")
    print("=" * 50)
    print("Type your question. Type 'quit' to exit.\n")

    conversation_history = []

    while True:
        question = input("You: ").strip()
        if question.lower() in ["quit", "exit", "q"]:
            break
        if not question:
            continue

        result = ask(question, conversation_history)
        print(f"\nBot: {result['answer']}")
        if result["sources"]:
            print("Sources:", [f"{s['file']} p{s['page']}" for s in result["sources"]])
        print()

        # Update history
        conversation_history.append({"role": "user",      "content": question})
        conversation_history.append({"role": "assistant", "content": result["answer"]})