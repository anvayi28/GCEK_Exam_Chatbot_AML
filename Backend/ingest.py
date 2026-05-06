import os
import pytesseract
import pymupdf
import chromadb
from PIL import Image
import io
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Tesseract path ────────────────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Embedding model ───────────────────────────────────────────────────────────
print("Loading embedding model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
print("Embedding model loaded.\n")

# ── ChromaDB: get or create (never wipes existing data) ──────────────────────
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection("gcek_exam_rules")
print(f"ChromaDB ready. Currently has {collection.count()} chunks stored.\n")

# ── Text splitter ─────────────────────────────────────────────────────────────
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    length_function=len,
)


def extract_text_from_page(page) -> str:
    """
    Convert a PDF page to image and extract text using Tesseract OCR.
    No API calls, no limits, works completely offline.
    """
    # Render page at 3x resolution for better OCR accuracy
    mat = pymupdf.Matrix(3, 3)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")

    # Convert to PIL Image for pytesseract
    image = Image.open(io.BytesIO(img_bytes))

    # Run Tesseract OCR
    text = pytesseract.image_to_string(image, lang='eng')
    return text.strip()


def page_already_processed(pdf_name: str, page_num: int) -> bool:
    """Check if this page was already stored in ChromaDB."""
    chunk_id = f"{pdf_name}_p{page_num + 1}_c0"
    try:
        result = collection.get(ids=[chunk_id])
        return len(result["ids"]) > 0
    except Exception:
        return False


def embed_and_store(chunks: list):
    """Generate embeddings and store chunks in ChromaDB immediately."""
    if not chunks:
        return

    texts     = [c["text"]     for c in chunks]
    ids       = [c["chunk_id"] for c in chunks]
    metadatas = [{"source": c["source"], "page": c["page"]} for c in chunks]

    embeddings = embedding_model.encode(texts).tolist()
    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
    print(f"    Saved to ChromaDB. Total chunks: {collection.count()}")


def process_pdf(pdf_path: str):
    """
    Process a single PDF:
    - Skip already-done pages (resume mode)
    - Extract text via Tesseract OCR (local, no API needed)
    - Chunk and store immediately after each page
    """
    pdf_name = os.path.basename(pdf_path)
    print(f"Processing: {pdf_name}")
    doc = pymupdf.open(pdf_path)
    skipped = 0

    for page_num in range(len(doc)):

        # Resume: skip pages already in ChromaDB
        if page_already_processed(pdf_name, page_num):
            skipped += 1
            continue

        print(f"  Page {page_num + 1}/{len(doc)} — running OCR...")
        page = doc[page_num]
        page_text = extract_text_from_page(page)

        if not page_text or len(page_text.strip()) < 20:
            print(f"  Page {page_num + 1}: No text found, skipping.")
            continue

        # Split into chunks
        chunks = text_splitter.split_text(page_text)
        chunk_dicts = []
        for i, chunk in enumerate(chunks):
            chunk_dicts.append({
                "text": chunk,
                "source": pdf_name,
                "page": page_num + 1,
                "chunk_id": f"{pdf_name}_p{page_num + 1}_c{i}"
            })

        print(f"  Page {page_num + 1}: Extracted {len(chunks)} chunk(s).")

        # Store immediately — never lose progress
        embed_and_store(chunk_dicts)

    doc.close()

    if skipped > 0:
        print(f"  Skipped {skipped} already-processed page(s).")
    print()


def main():
    pdf_folder = "./pdfs"
    pdf_files = [
        os.path.join(pdf_folder, f)
        for f in os.listdir(pdf_folder)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print("No PDFs found in ./pdfs folder.")
        return

    print(f"Found {len(pdf_files)} PDF(s): {[os.path.basename(f) for f in pdf_files]}\n")
    print("Using Tesseract OCR — no API keys needed, no rate limits!\n")

    for pdf_path in pdf_files:
        process_pdf(pdf_path)

    total = collection.count()
    print(f"Ingestion complete! Total chunks in ChromaDB: {total}")
    if total > 0:
        print("You can now run: python rag_pipeline.py")


if __name__ == "__main__":
    main()