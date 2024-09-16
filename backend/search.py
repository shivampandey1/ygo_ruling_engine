import sqlite3
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from rank_bm25 import BM25Okapi
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
import math
import instructor
from enum import Enum
import numpy as np
from sentence_transformers import CrossEncoder
import torch
from card_mechanics import analyze_card_mechanics, CardMechanic

# Load environment variables
load_dotenv()

# Set up OpenAI API client with instructor
client = instructor.patch(AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Load the cross-encoder model (do this outside the function for efficiency)
cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

class Card(BaseModel):
    name: str
    humanReadableCardType: str
    desc: str
    race: str
    atk: int
    def_: int
    attribute: str
    card_images: List[Dict[str, Any]]
    level: int

class Ruling(BaseModel):
    source: str
    content: str

class RelevanceLevel(str, Enum):
    STRONG = "strong"
    UNSURE = "unsure"
    WEAK = "weak"

class RankingResult(BaseModel):
    reasoning: str
    relevance: RelevanceLevel

    @field_validator('relevance', mode='before')
    @classmethod
    def parse_relevance(cls, v):
        if isinstance(v, str):
            try:
                return RelevanceLevel(v.lower())
            except ValueError:
                raise ValueError(f"Invalid relevance level: {v}")
        return v

# Cards Search 
def search_card_by_name(card_name: str, db_path: str = 'yugioh.db') -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
    SELECT name, humanReadableCardType, desc, race, atk, def, attribute, card_images, level
    FROM cards
    WHERE name LIKE ?
    LIMIT 10
    """
    
    cursor.execute(query, (f"%{card_name}%",))
    results = cursor.fetchall()
    
    columns = ['name', 'humanReadableCardType', 'desc', 'race', 'atk', 'def', 'attribute', 'card_images', 'level']
    cards = []
    
    for result in results:
        card_properties = dict(zip(columns, result))
        card_properties['card_images'] = json.loads(card_properties['card_images'])
        cards.append(card_properties)
    
    conn.close()
    return cards

def get_exact_rulings(card_names: List[str], db_path: str = 'yugioh.db', verbose: bool = False) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    rulings = []
    
    # Check qa_tl_fixed table
    for card_name in card_names:
        query = """
        SELECT qaId, locale, title, question, answer, date, sourceHash, translator, lastEditor
        FROM qa_tl_fixed
        WHERE question LIKE ?
        """
        cursor.execute(query, (f"%{card_name}%",))
        results = cursor.fetchall()
        for result in results:
            rulings.append({
                'source': 'qa_tl_fixed',
                'qaId': result[0],
                'locale': result[1],
                'title': result[2],
                'question': result[3],
                'answer': result[4],
                'date': result[5],
                'sourceHash': result[6],
                'translator': result[7],
                'lastEditor': result[8]
            })
    
    # Check faq_tl_entries_fixed table
    for card_name in card_names:
        query = """
        SELECT cardId, locale, effect, sourceHash, content, name
        FROM faq_tl_entries_fixed
        WHERE name = ?
        """
        cursor.execute(query, (card_name,))
        results = cursor.fetchall()
        for result in results:
            rulings.append({
                'source': 'faq_tl_entries_fixed',
                'cardId': result[0],
                'locale': result[1],
                'effect': result[2],
                'sourceHash': result[3],
                'content': result[4],
                'name': result[5]
            })
    
    conn.close()
    
    # Apply BM25 ranking to pare down to 10 most relevant rulings
    if rulings:
        ruling_texts = [r.get('question', '') + ' ' + r.get('answer', '') + ' ' + r.get('content', '') for r in rulings]
        bm25 = BM25Okapi([text.split() for text in ruling_texts])
        card_names_query = ' '.join(card_names)
        scores = bm25.get_scores(card_names_query.split())
        top_indices = np.argsort(scores)[-10:][::-1]
        rulings = [rulings[i] for i in top_indices]
    
    if verbose:
        print(f"Found {len(rulings)} relevant rulings for cards: {card_names}")
    
    return rulings

def get_relevant_rulings(card_names: List[str], db_path: str = 'yugioh.db', verbose: bool = False) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all card descriptions for BM25
    cursor.execute("SELECT name, desc FROM cards")
    all_cards = cursor.fetchall()
    
    card_descriptions = [desc for _, desc in all_cards]
    bm25 = BM25Okapi([desc.split() for desc in card_descriptions])
    
    relevant_rulings = []
    
    for card_name in card_names:
        # Get the description of the current card
        cursor.execute("SELECT desc FROM cards WHERE name = ?", (card_name,))
        card_desc = cursor.fetchone()
        if not card_desc:
            continue
        
        # Find similar cards using BM25 (increased strictness)
        scores = bm25.get_scores(card_desc[0].split())
        similar_cards = [all_cards[i][0] for i in scores.argsort()[-5:][::-1]]  # Reduced from 10 to 5
        
        # Get exact match rulings for similar cards
        similar_rulings = get_exact_rulings(similar_cards, db_path, verbose)
        relevant_rulings.extend(similar_rulings)
    
    conn.close()
    
    if verbose:
        print(f"Found {len(relevant_rulings)} relevant rulings for cards: {card_names}")
    
    return relevant_rulings

async def rerank_rulings(question: str, rulings: List[Dict[str, Any]], verbose: bool = False) -> List[Ruling]:
    total_rulings = len(rulings)
    print(f"Ranking {total_rulings} rulings...")

    # Prepare pairs for the cross-encoder
    pairs = [(question, ruling.get('question', '') + ' ' + ruling.get('answer', '') + ' ' + ruling.get('content', '')) for ruling in rulings]

    # Get scores from the cross-encoder
    scores = cross_encoder.predict(pairs)

    # Sort rulings by score
    ranked_rulings = sorted(zip(rulings, scores), key=lambda x: x[1], reverse=True)

    # Select top 5 rulings
    top_rulings = [Ruling(source=ruling['source'], content=ruling.get('question', '') + ' ' + ruling.get('answer', '') + ' ' + ruling.get('content', '')) 
                   for ruling, score in ranked_rulings[:5]]

    if verbose:
        for i, (ruling, score) in enumerate(ranked_rulings[:5], 1):
            print(f"Rank {i}:")
            print(f"Score: {score}")
            print(f"Content: {ruling.get('question', '')[:100]}...")
            print()

    print(f"Selected top {len(top_rulings)} most relevant rulings.")
    return top_rulings

async def get_rulings_for_question(question: str, card_names: List[str], db_path: str = 'yugioh.db', verbose: bool = False) -> Optional[List[Ruling]]:
    exact_rulings = get_exact_rulings(card_names, db_path, verbose)
    relevant_rulings = get_relevant_rulings(card_names, db_path, verbose)
    all_rulings = exact_rulings + relevant_rulings

    reranked_rulings = await rerank_rulings(question, all_rulings, verbose)
    return reranked_rulings

async def mechanics_search(card: Card) -> CardMechanic:
    mechanics = analyze_card_mechanics(card)
    return mechanics

# Example usage:
if __name__ == "__main__":
    import asyncio

    async def main():
        print("search.py")
        # Example search
        # print(search_card_by_name("Shaddoll Fusion"))
        # print(search_card_by_name("Ash Blossom & Joyous Spring"))
        
        # # Example rulings search and reranking
        # question = "Can Ash Blossom & Joyous Spring negate Shaddoll Fusion if my opponent controls no monsters summoned from the Extra Deck?"
        # card_names = ["Shaddoll Fusion", "Ash Blossom & Joyous Spring"]
        
        # reranked_rulings = await get_rulings_for_question(question, card_names, verbose=False)
        # print("\nStrongly Relevant rulings:")
        # for ruling in reranked_rulings:
        #     print(f"Source: {ruling.source}")
        #     print(f"Content: {ruling.content[:200]}...")
        #     print()

        # Example mechanics search
        # card_name = "Dark Magician"
        # card_data = search_card_by_name(card_name)
        # if card_data:
        #     card = Card(**card_data[0])  # Assuming search_card_by_name returns a list of dictionaries
        #     mechanics = await mechanics_search(card)
        #     if mechanics:
        #         print(f"\nMechanics for {card_name}:")
        #         print(mechanics.model_dump_json(indent=2))
        #     else:
        #         print(f"No mechanics found for {card_name}")
        # else:
        #     print(f"Card not found: {card_name}")

    asyncio.run(main())