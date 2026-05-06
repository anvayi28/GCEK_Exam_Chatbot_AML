# GCEK_Exam_Chatbot_AML
Chatbot build using Groq api and python libraries 
Tesseract ocr, to extract text from images
Then we split it into 500 chunks of characters using langchain's recursive character text splitter
For reading pdf we used PyMuPDF


We convert each chunk into vector Embedding using all-miniLM model , from sentence transformer library 
Then we store 715 chunks  in chromadb lightweight local db 
When students asks question, it will be searched in chromadb- 5 most similar chunks using cosine similarity 
Chunks combined are sent to groq(the API we used), then it generates an answer 


Using fast API, makes process fast and automatically generates API documentation 
CORS is used as an middle ware so frontend can communicate with Backend 


We wanted to use Google Gemini API for both answers and ocr
But it has only 20 req per day
So for ocr we switched to Tesseract and for answering groq
