from midrasai import Midras
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf
from unstructured.staging.base import elements_to_json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from typing import List, Dict, Any

# Load environment variables
load_dotenv()

# Set up OpenAI API client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# # Initialize Midras
# midras = Midras(midras_key=os.getenv("MIDRAS_API_KEY"))

# # Index name
# index_name = "yugioh_rulebook_index"

async def initialize_index():
    # Create index if it doesn't exist
    midras.create_index(index_name)

    # Embed PDF if not already done
    response = midras.embed_pdf("rulebook.pdf", include_images=True)

    for id, embedding in enumerate(response.embeddings):
        midras.add_point(
            index=index_name,
            id=id,
            embedding=embedding,
            data={
                "page_number": id + 1,
            }
        )

async def colpali_search(user_query: str) -> str:
    # Query the document
    results = midras.query_text(index_name, text=user_query)

    # Prepare context from top 3 results
    context = "Relevant information from the Yu-Gi-Oh! rulebook:\n\n"
    for result in results[:3]:
        context += f"Page {result.data['page_number']}:\n{result.text}\n\n"

    # Prepare prompt for GPT-4o
    prompt = f"""Based on the following information from the Yu-Gi-Oh! rulebook, please provide context:

Context:
{context}

User Question: {user_query}

Please provide all relevant information from the provided sections of the rulebook given this question."""

    # Query GPT-4o
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a Yu-Gi-Oh! rules expert. Provide relevant information to the query from the given images. Do not answer the question, only provide context."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        n=1,
        stop=None,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()

# this is a placeholder for the actual search function until i get around to fixing it
async def unstructured_search(user_query: str) -> str:
    return "no relevant context found"

# getting this to work is a huge pain in my ass and i don't want to do it
# async def unstructured_search(user_query: str) -> str:
#     # Partition the PDF
#     elements = partition_pdf("rulebook.pdf")
    
#     # Convert elements to JSON
#     json_elements = elements_to_json(elements)
    
#     # Extract text content from elements
#     texts = [element['text'] for element in json_elements if 'text' in element]
    
#     # Create TF-IDF vectorizer
#     vectorizer = TfidfVectorizer()
#     tfidf_matrix = vectorizer.fit_transform(texts)
    
#     # Vectorize the query
#     query_vector = vectorizer.transform([user_query])
    
#     # Calculate cosine similarity
#     cosine_similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
    
#     # Get top 3 most similar passages
#     top_indices = cosine_similarities.argsort()[-3:][::-1]
    
#     # Prepare context from top 3 results
#     context = "Relevant information from the Yu-Gi-Oh! rulebook:\n\n"
#     for index in top_indices:
#         context += f"Passage {index + 1}:\n{texts[index]}\n\n"

#     # Prepare prompt for GPT-4o
#     prompt = f"""Based on the following information from the Yu-Gi-Oh! rulebook, please provide context:

# Context:
# {context}

# User Question: {user_query}

# Please provide all relevant information from the provided sections of the rulebook given this question."""

#     # Query GPT-4o
#     response = await client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[
#             {"role": "system", "content": "You are a Yu-Gi-Oh! rules expert. Provide relevant information to the query from the given passages. Do not answer the question, only provide context."},
#             {"role": "user", "content": prompt}
#         ],
#         max_tokens=300,
#         n=1,
#         stop=None,
#         temperature=0.7,
#     )

#     return response.choices[0].message.content.strip()

# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        #await initialize_index()
        
        user_query = "How does Synchro Summoning work?"
        
        #colpali_result = await colpali_search(user_query)
        #print(f"User Query: {user_query}")
        #print(f"Colpali Context: {colpali_result}")
        
        unstructured_result = await unstructured_search(user_query)
        print(f"\nUnstructured Context: {unstructured_result}")

    asyncio.run(main())