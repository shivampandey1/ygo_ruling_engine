from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from search import search_card_by_name
import logging
from starlette.websockets import WebSocketDisconnect  # Add this import
import uvicorn
from agent import YuGiOhAgent, Card, prompt  # Import the agent and necessary classes

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag to enable/disable logging
ENABLE_LOGGING = True

def log(message):
    if ENABLE_LOGGING:
        logger.info(message)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    log("WebSocket connection established")
    agent = YuGiOhAgent(prompt, verbose=True)  # Create an instance of the agent
    
    try:
        while True:
            data = await websocket.receive_text()
            log(f"Received data: {data}")
            try:
                json_data = json.loads(data)
                type = json_data.get("type")
                log(f"type check: {type}")
                if json_data.get("type") == "card_search":
                    query = json_data.get("query", "")
                    log(f"Searching for card: {query}")
                    results = search_card_by_name(query)
                    await websocket.send_json({
                        "type": "search_results",
                        "results": results
                    })
                    log(f"Sent {len(results)} search results")
                elif json_data.get("type") == "inquiry":
                    question = json_data.get("question", "")
                    '''
                    cards = json_data.get("cards", [])
                    card_names = [card['name'] for card in cards]  # Extract card names
                    log(f"Received inquiry: {question} for cards: {', '.join(card_names)}")
                    # Here you would process the inquiry
                    # For now, we'll just send a confirmation message
                    await websocket.send_json({
                        "type": "inquiry_confirmation",
                        "message": f"Your question '{question}' involving cards {', '.join(card_names)} was successfully received."
                    })
                    log("Sent inquiry confirmation")
                    '''
                    cards = [Card(**card) for card in json_data.get("cards", [])]
                    log(f"Received inquiry: {question} for cards: {', '.join([card.name for card in cards])}")
                    
                    # Create a new instance of the agent for each inquiry to ensure state is reset
                    agent = YuGiOhAgent(prompt, verbose=True)
                    # Call the agent and stream the response
                    async for response in agent(question, cards):
                        await websocket.send_json({
                            "type": "agent_response",
                            "data": response.dict()
                        })
                    
                    log("Finished processing inquiry")
            except json.JSONDecodeError:
                log("Received invalid JSON data")
    except WebSocketDisconnect:
        log("WebSocket disconnected")
    except Exception as e:
        log(f"WebSocket error: {str(e)}")
    finally:
        log("WebSocket connection closed!")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    #uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")