'''
blogs used for this:
https://yugiohblog.konami.com/articles/?p=2906
https://yugiohblog.konami.com/articles/?p=2915
https://yugiohblog.konami.com/articles/?p=2947
https://yugiohblog.konami.com/articles/?p=2962
https://yugiohblog.konami.com/articles/?p=3111
https://yugiohblog.konami.com/articles/?p=3140
https://yugiohblog.konami.com/articles/?p=4514
'''

'''
Summary of important Yu-Gi-Oh! card mechanics:

1. Problem-Solving Card Text (PSCT) uses colons (:) and semicolons (;) to separate card effects into activation conditions, costs, and resolutions.
2. Special Summons are divided into two groups: effects that Summon (start a Chain) and built-in Summons (don't start a Chain).
3. Negating Summons only works on built-in Summons, not effect Summons.
4. Key conjunctions in card text:
   - "Then": Sequential actions, A required for B
   - "Also": Simultaneous actions, neither required for the other
   - "And if you do": Simultaneous actions, A required for B
   - "And": Simultaneous actions, both required
5. Timing and causation are important for determining effect activation eligibility and resolution.
6. Cards can have Continuous Effects, Trigger Effects, Ignition Effects, and Quick Effects.
7. Targeting is specified in card text, and conditions may need to be met at resolution.
8. Some effects can miss timing if they are optional "When... you can" effects.
9. Card types (Monster, Spell, Trap) and sub-types (Normal, Effect, Fusion, Synchro, Xyz, Ritual, Continuous, Quick-Play, etc.) affect how they can be used.
10. Chains resolve in reverse order, with each effect resolving separately.
'''

from typing import List, Dict, Any
from pydantic import BaseModel

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

class CardMechanic(BaseModel):
    effect_type: str
    activation_condition: str
    cost: str
    resolution: str
    timing: str
    targeting: bool
    once_per_chain: bool
    once_per_turn: bool
    hard_once_per_turn: bool
    once_per_duel: bool

def analyze_card_mechanics(card: Card) -> CardMechanic:
    # Analyze the card text and extract mechanics
    card_text = card.desc
    
    effect_type = determine_effect_type(card_text)
    activation_condition = extract_activation_condition(card_text)
    cost = extract_cost(card_text)
    resolution = extract_resolution(card_text)
    timing = determine_timing(card_text)
    targeting = 'target' in card_text.lower()
    once_per_chain = 'once per chain' in card_text.lower()
    once_per_turn = 'once per turn' in card_text.lower()
    hard_once_per_turn = 'you can only use this effect of' in card_text.lower()
    once_per_duel = 'once per duel' in card_text.lower()

    return CardMechanic(
        effect_type=effect_type,
        activation_condition=activation_condition,
        cost=cost,
        resolution=resolution,
        timing=timing,
        targeting=targeting,
        once_per_chain=once_per_chain,
        once_per_turn=once_per_turn,
        hard_once_per_turn=hard_once_per_turn,
        once_per_duel=once_per_duel
    )

def determine_effect_type(card_text: str) -> str:
    if ':' in card_text:
        return 'Trigger' if 'when' in card_text.lower() or 'if' in card_text.lower() else 'Ignition'
    elif ';' in card_text:
        return 'Quick' if 'during' in card_text.lower() or 'quick effect' in card_text.lower() else 'Ignition'
    else:
        return 'Continuous'

def extract_activation_condition(card_text: str) -> str:
    if ':' in card_text:
        return card_text.split(':')[0].strip()
    return ''

def extract_cost(card_text: str) -> str:
    if ';' in card_text:
        return card_text.split(';')[0].split(':')[-1].strip()
    return ''

def extract_resolution(card_text: str) -> str:
    if ';' in card_text:
        return card_text.split(';')[-1].strip()
    elif ':' in card_text:
        return card_text.split(':')[-1].strip()
    return card_text

def determine_timing(card_text: str) -> str:
    if 'quick effect' in card_text.lower():
        return 'Quick Effect'
    elif 'during either player\'s' in card_text.lower():
        return 'Either Player\'s Turn'
    elif 'during your opponent\'s' in card_text.lower():
        return 'Opponent\'s Turn'
    else:
        return 'Your Turn'
