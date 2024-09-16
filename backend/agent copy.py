import asyncio
from pydantic import BaseModel, ValidationError, validator
from typing import List, Optional, Dict, Any, Literal, AsyncGenerator
import instructor
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
from search import search_card_by_name, get_rulings_for_question, analyze_card_mechanics
from vlm_rulebook_search import unstructured_search

# Load environment variables
load_dotenv()

# Set up OpenAI API client
client = instructor.patch(AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Pydantic Models

class Card(BaseModel):
    name: str
    humanReadableCardType: str
    desc: str
    race: Optional[str] = None
    atk: Optional[int] = None
    def_: Optional[int] = None
    attribute: Optional[str] = None
    level: Optional[int] = None
    card_images: Optional[Dict[str, Any]] = None

class Message(BaseModel):
    role: str
    content: str

class Action(BaseModel):
    name: Literal["search_rulings", "analyze_mechanics", "search_rulebook"]
    input: str

class Thought(BaseModel):
    content: str

class Observation(BaseModel):
    content: str

class Answer(BaseModel):
    explanation: str
    ruling: str

class AgentResponse(BaseModel):
    thought: Optional[Thought] = None
    action: Optional[Action] = None
    observation: Optional[Observation] = None
    answer: Optional[Answer] = None

class YuGiOhAgent:
    def __init__(self, system: Optional[str] = "", verbose: bool = False):
        self.system = system
        self.messages: List[Message] = []
        if self.system:
            self.messages.append(Message(role="system", content=system))
        self.verbose = verbose
        self.action_history: List[str] = []
        self.thinking_turns = 0
        self.max_thinking_turns = 3
    
    async def __call__(self, question: str, cards: List[Card]) -> AsyncGenerator[AgentResponse, None]:
        self.messages.append(Message(role="user", content=f"Question: {question}\nCards: {[card.name for card in cards]}"))
        turn_count = 0
        max_turns = 15
        action_count = 0
        max_actions = 10
        
        while turn_count < max_turns:
            turn_count += 1
            print(f"Turn {turn_count}")
            result = await self.execute()
            response = self.parse_response(result)
            yield response
            
            if response.action:
                if self.is_duplicate_action(response.action):
                    print(f"Skipping duplicate action: {response.action.name}")
                    continue
                
                action_count += 1
                print(f"Performing action {action_count}: {response.action.name}")
                observation = await self.perform_action(response.action, cards)
                response.observation = Observation(content=observation)
                self.messages.append(Message(role="system", content=f"Observation: {observation}"))
                self.action_history.append(f"{response.action.name}:{response.action.input}")
                yield response
            
            if self.has_sufficient_information():
                print("Sufficient information gathered. Starting thinking turns.")
                while self.thinking_turns < self.max_thinking_turns:
                    self.thinking_turns += 1
                    thinking_prompt = self.get_thinking_prompt(self.thinking_turns)
                    self.messages.append(Message(role="system", content=thinking_prompt))
                    print(f"Thinking turn {self.thinking_turns}")
                    
                    # Execute thinking turn
                    result = await self.execute()
                    response = self.parse_response(result)
                    yield response
                    
                    # Add the thought to the message history
                    if response.thought:
                        self.messages.append(Message(role="assistant", content=response.thought.content))
                
                print("Executing final answer")
                final_result = await self.execute_final_answer()
                final_response = self.parse_response(final_result)
                if final_response.answer:
                    print("Final answer provided")
                    yield final_response
                else:
                    print("Unable to reach a conclusive answer")
                    yield AgentResponse(
                        thought=Thought(content="Unable to reach a conclusive answer."),
                        answer=Answer(
                            explanation="After analyzing the available information, a definitive answer couldn't be reached.",
                            ruling="Inconclusive - Further investigation may be needed."
                        )
                    )
                break
            
            if action_count >= max_actions:
                print(f"Maximum actions ({max_actions}) reached")
                yield AgentResponse(
                    thought=Thought(content=f"Maximum actions ({max_actions}) reached without a conclusive answer."),
                    answer=Answer(
                        explanation="After analyzing the available information, a definitive answer couldn't be reached within the given action constraints.",
                        ruling="Inconclusive - Further investigation may be needed."
                    )
                )
                break
            
            if turn_count == max_turns:
                print(f"Maximum turns ({max_turns}) reached")
                yield AgentResponse(
                    thought=Thought(content=f"Maximum turns ({max_turns}) reached without a conclusive answer."),
                    answer=Answer(
                        explanation="After analyzing the available information, a definitive answer couldn't be reached within the given turn constraints.",
                        ruling="Inconclusive - Further investigation may be needed."
                    )
                )
                break

    def has_sufficient_information(self) -> bool:
        #required_actions = {"analyze_mechanics", "search_rulings"}
        required_actions = {'analyze_mechanics', 'search_rulings', 'search_rulebook'}
        performed_actions = set(action.split(":")[0] for action in self.action_history)
        #has_sufficient = required_actions.issubset(performed_actions) and self.rulebook_searched
        has_sufficient = (required_actions == performed_actions)
        #print(f"Checking sufficient information: {performed_actions}, Rulebook searched: {self.rulebook_searched}")

        # print("\n--- Debugging Information ---")
        # print(f"Required actions: {required_actions}")
        print(f"Performed actions: {performed_actions}")
        # # print(f"Action history: {self.action_history}")
        # print(f"Sets equal: {performed_actions == required_actions}")
        # print(f"Missing actions: {required_actions - performed_actions}")
        # print(f"Extra actions: {performed_actions - required_actions}")
        # print(f"has_sufficient: {has_sufficient}")
        
        if has_sufficient:
            print("Sufficient information gathered")
        return has_sufficient

    def get_thinking_prompt(self, turn: int) -> str:
        prompts = [
            "Based on the information gathered, what new knowledge have you gained that's relevant to the question? How does this information contribute to forming a ruling?",
            "Considering the mechanics of the cards and the relevant rulings, what are the key points that support or contradict a potential ruling? Are there any ambiguities or conflicts in the information?",
            "Given all the information gathered and your analysis, what is your current leaning towards a ruling? Decide if you have enough information to draw a conclusion, or if you don't know the answer."
        ]
        return prompts[turn - 1]

    def is_duplicate_action(self, action: Action) -> bool:
        return f"{action.name}:{action.input}" in self.action_history

   
    async def execute_final_answer(self):
        messages = [message.dict() for message in self.messages]
        
        # # Check if the last message contains a valid answer
        # last_message = messages[-1]['content']
        # if "Ruling:" in last_message and "Explanation:" in last_message:
        #     # Extract the ruling and explanation from the last thinking step
        #     ruling = last_message.split("Ruling:")[-1].strip()
        #     explanation = last_message.split("Explanation:")[-1].split("Ruling:")[0].strip()
        #     return f"Answer: {explanation}\nRuling: {ruling}"
        
        # If no valid answer in the last thinking step, proceed with the original logic
        messages.append({
            "role": "system",
            "content": "You have gathered and analyzed all necessary information. Please provide a final answer and ruling based on your analysis. Be decisive and explain your reasoning clearly. If there are any remaining uncertainties, acknowledge them but provide the most likely ruling based on the available information."
        })
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300,
            n=1,
            stop=None,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    
    async def execute(self):
        messages = [message.dict() for message in self.messages]
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300,
            n=1,
            stop=None,
            temperature=0.7,
        )
        print(f"Executing: {response.choices[0].message.content.strip()}")
        return response.choices[0].message.content.strip()
    
    def parse_response(self, content: str) -> AgentResponse:
        response = AgentResponse()
        lines = content.split("\n")
        current_section = None
        
        for line in lines:
            if line.startswith("Thought:"):
                response.thought = Thought(content=line[8:].strip())
            elif line.startswith("Action:"):
                action_parts = line[7:].strip().split(":", 1)
                if len(action_parts) == 2:
                    response.action = Action(name=action_parts[0].strip(), input=action_parts[1].strip())
            elif line.startswith("Answer:"):
                # answer_parts = line[7:].strip().split("\nRuling:", 1)
                answer_parts = content.split("Answer:", 1)[1].split("Ruling:", 1)
                if len(answer_parts) == 2:
                    response.answer = Answer(explanation=answer_parts[0].strip(), ruling=answer_parts[1].strip())
            elif line == "PAUSE":
                break
        
        return response

    async def perform_action(self, action: Action, cards: List[Card]) -> str:
        if action.name == "search_rulings":
            card_names = [card.name for card in cards]
            if action.input not in card_names:
                return f"Error: Can only search rulings for cards mentioned in the question. '{action.input}' is not in the provided list of cards."
            rulings = await get_rulings_for_question(action.input, card_names)
            return "\n".join([ruling.content for ruling in rulings])
        elif action.name == "analyze_mechanics":
            card = next((c for c in cards if c.name == action.input), None)
            if card:
                mechanics = analyze_card_mechanics(card)
                return str(mechanics)
            return f"Card '{action.input}' not found in the provided list."
        elif action.name == "search_rulebook":
            # self.rulebook_searched = True
            return await unstructured_search(action.input)
        else:
            return f"Unknown action: {action.name}"

        

    
        return f"{action.name}:{action.input}" in self.action_history
    
    def log(self, message: str):
        if self.verbose:
            print(message)

# System prompt definition
prompt = """
You are a Yu-Gi-Oh! judge AI. Your job is to answer questions about card interactions and provide rulings. You run in a loop of Thought, Action, PAUSE, Observation. At the end of the loop, you output an Answer with a Ruling.

1. Use Thought to describe your thoughts about the question you have been asked.
2. Use Action to run one of the actions available to you, then return PAUSE.
3. You will receive an Observation, which is the result of running the action.
4. Repeat steps 1-3 until you have enough information to provide an Answer, or until you've taken 10 turns.
5. End with an Answer that includes an explanation and a Ruling.

Your available actions are:
- search_rulings: Search for relevant rulings about the cards. Only use this for cards mentioned in the question.
- analyze_mechanics: Get a detailed breakdown of a card's mechanics.
- search_rulebook: Look up relevant rules in the Yu-Gi-Oh! rulebook.

Important guidelines:
- Do not repeat the same action with the same input.
- Only search for rulings of the specific cards mentioned in the question.
- If you're unsure after 10 turns, provide your best answer based on the information you have, or state that you're unsure.

Example:

Question: Can Ash Blossom negate Shaddoll Fusion if there are no Extra Deck monsters on the field?
Thought: I need to understand how both Ash Blossom and Shaddoll Fusion work, and if Shaddoll Fusion's effect can be negated by Ash Blossom under these conditions.
Action: analyze_mechanics: Ash Blossom & Joyous Spring
PAUSE
Observation: (You'll receive the mechanics of Ash Blossom here)
Thought: Now that I understand Ash Blossom's mechanics, I need to check Shaddoll Fusion's mechanics.
Action: analyze_mechanics: Shaddoll Fusion
PAUSE
Observation: (You'll receive the mechanics of Shaddoll Fusion here)
Thought: I have the mechanics for both cards. Now I should check if there are any specific rulings about this interaction.
Action: search_rulings: Ash Blossom & Joyous Spring
PAUSE
Observation: (You'll receive relevant rulings here)
Thought: I've gathered information about both cards and relevant rulings. I can now determine if Ash Blossom can negate Shaddoll Fusion in this scenario.
Answer: Ash Blossom & Joyous Spring can negate Shaddoll Fusion even if there are no Extra Deck monsters on the field. Shaddoll Fusion always includes an effect to send cards from the Deck to the GY (as Fusion Materials), which is one of the effects that Ash Blossom can negate. The condition of having an opponent's Extra Deck monster on the field only allows for additional uses of the card, but doesn't change its core effect that Ash Blossom responds to.
Ruling: Ash Blossom & Joyous Spring can negate Shaddoll Fusion regardless of whether there are Extra Deck monsters on the field or not.
""".strip()

async def main():
    agent = YuGiOhAgent(prompt, verbose=True)
    question = "Can Ash Blossom negate Shaddoll Fusion if there are no Extra Deck monsters on the field?"
    cards = [
        Card(name="Ash Blossom & Joyous Spring", humanReadableCardType="Tuner Effect Monster", desc="When a card or effect is activated that includes any of these effects (Quick Effect): You can discard this card; negate that effect. ● Add a card from the Deck to the hand. ● Special Summon from the Deck. ● Send a card from the Deck to the GY. You can only use this effect of 'Ash Blossom & Joyous Spring' once per turn."),
        Card(name="Shaddoll Fusion", humanReadableCardType="Normal Spell", desc="Fusion Summon 1 'Shaddoll' Fusion Monster from your Extra Deck, using monsters from your hand or field as Fusion Material. If your opponent controls a monster that was Special Summoned from the Extra Deck, you can also use monsters in your Deck as Fusion Material. You can only activate 1 'Shaddoll Fusion' per turn.")
    ]
    
    async for response in agent(question, cards):
        if response.thought:
            print("Thought:", response.thought.content)
        if response.action:
            print(f"Action: {response.action.name}: {response.action.input}")
            print("PAUSE")
        if response.observation:
            print("Observation:", response.observation.content)
        if response.answer:
            print("Answer:", response.answer.explanation)
            print("Ruling:", response.answer.ruling)
        print("---")

if __name__ == "__main__":
    asyncio.run(main())