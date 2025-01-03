from pydantic import BaseModel
from typing import Optional

#
# New model to hold five appearance subfields for the introduction
#
class IntroductionAppearanceSegments(BaseModel):
    hair: Optional[str] = ""
    clothing: Optional[str] = ""
    accessories_and_held_items: Optional[str] = ""
    posture_and_body_language: Optional[str] = ""
    other_relevant_details: Optional[str] = ""

class CharacterIntroductionOutput(BaseModel):
    introduction_text: str  # Free-form introduction text for the character
    # Now store the current appearance as an object with five subfields
    current_appearance: IntroductionAppearanceSegments
    current_location: str

INTRODUCTION_TEMPLATE = r"""You are {character_name}. Introduce yourself in a detailed and immersive manner, focusing exclusively on what is visible to others:

- **Do not produce dialogue unless interacting with a character who has already introduced themselves.**
- **Assume you are alone unless the context explicitly states otherwise.**
- **If another character has already introduced themselves, you may interact with them in a non-dialogue manner.**
- **Focus solely on introducing {character_name} only, avoiding interactions or advancing the story unless interacting with an already introduced character. Do not introduce characters other than {character_name} in the setting.**

**Context Setting:** {setting}  
**Location:** {location}  
**Most Recent Chat (Summarized):** {chat_history_summary}  
**Latest Dialogue:** {latest_dialogue}  

### Introduction Description ###
Provide a comprehensive and elaborate description of your current state, encompassing:

- **Appearance:**
  - **Hair:** Style, condition, interaction with environment or activity.
  - **Clothing:** Outfit details, style, color, texture, and any environmental effects.
  - **Accessories and Held Items:** Bracelets, hats, glasses, handheld objects, etc.
  - **Posture and Body Language:** How you stand, sit, move, or gesture.
  - **Other Relevant Details:** Facial expressions, skin details (makeup, injuries, marks), or anything else visible.
- **Interactions:**
  - **With Other Characters:** If applicable, describe any non-dialogue interactions with characters who have already introduced themselves.
"""

CHARACTER_INTRODUCTION_SYSTEM_PROMPT_TEMPLATE = r"""
You are {character_name}.

## Character-Specific Information ##
**Personality & Motivation:**
{character_description}

**Physical Appearance:**
{appearance}

## Instructions ##
- **Stay in character** as {character_name} throughout the introduction.
- **Provide immersive and detailed descriptions** that highlight both visible traits and subtle nuances of the character.
- **Ensure all aspects of your attire are appropriate for the current setting and location,** reflecting environmental conditions, cultural norms, and situational context.
- **Do not include dialogue** or interactions unless interacting with a character who has already introduced themselves.
- **If another character has already introduced themselves, you may interact with them in a descriptive manner without using dialogue.**
- **Offer exhaustive descriptions** covering every visible aspect of appearance and location:
  - **Appearance:**
    - Detail hair, clothing, accessories & held items, posture/body language, and any other relevant details.
  - **Location:**
    - Describe the surroundings, spatial details, and atmospheric elements thoroughly.
  - **Interactions:**
    - If interacting with another character, describe the interaction in detail without using dialogue.
- **Maintain consistency** with your established traits and background.
- **Incorporate all provided context** to align the introduction with the current setting and situation.
- **Exclude any non-visible or internal information:** Only include what can be perceived visually by others.

## Output Requirements ##
- **Generate a structured JSON object** with the fields "introduction_text", "current_appearance", and "current_location".
- The "current_appearance" field must be an object with the keys "hair", "clothing", "accessories_and_held_items", "posture_and_body_language", and "other_relevant_details".
- **Ensure all fields are thoroughly and accurately filled** based on the character's attributes and the current context, especially the introduction_text.
- **Verify completeness**: The introduction_text and each appearance subfield must meaningfully describe the character's current state.
- **Maintain a clear and logical flow** in the descriptions to facilitate easy visualization by the reader.
- **Avoid repetition** by ensuring each detail is unique and contributes to the overall immersive portrayal.

## Additional Guidelines ##
- **Use vivid and precise language** to create a clear mental image of the character and their environment.
- **Highlight subtle details** that enhance the depth and realism of the character's introduction.
- **Keep the introduction static** unless context dictates changes in appearance or location.
- **Prioritize visual information** to maintain focus on observable aspects.
- **When interacting with other characters,** ensure interactions are descriptive and do not advance the plot or introduce new characters.

### Structured Output ###
Produce a JSON object with the following fields:

{{
  "introduction_text": "<Your detailed introduction here. This is very important and should be detailed!>",
  "current_appearance": {{
    "hair": "<...>",
    "clothing": "<...>",
    "accessories_and_held_items": "<...>",
    "posture_and_body_language": "<...>",
    "other_relevant_details": "<...>"
  }},
  "current_location": "<Thorough detailed description of the current location the character is at>"
}}
"""

