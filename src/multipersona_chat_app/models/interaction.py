from pydantic import BaseModel, Field
from typing import Optional


class AppearanceSegments(BaseModel):
    """
    Holds the five detailed subfields describing the appearance.
    Each field is optional; empty means no changes.
    """
    hair: Optional[str] = ""
    clothing: Optional[str] = ""
    accessories_and_held_items: Optional[str] = ""
    posture_and_body_language: Optional[str] = ""
    other_relevant_details: Optional[str] = ""


class Interaction(BaseModel):
    purpose: str        # Short-term goal or current mindset
    why_purpose: str    # Reason for the chosen purpose
    affect: str         # Internal feelings/emotions
    why_affect: str     # Reasoning behind those emotions
    action: str         # Visible behavior or action
    why_action: str     # Reason for taking that action now
    dialogue: str       # Spoken words (may be empty if no dialogue)
    why_dialogue: str   # Why these words (or silence) were chosen
    new_location: str   # This character's personal location change (if any)
    why_new_location: str
    new_appearance: AppearanceSegments
    why_new_appearance: str

    def format(self) -> str:
        """Format the Interaction object into a human-readable string for debugging/logging."""
        return (
            f"Purpose: {self.purpose if self.purpose else 'None'}\n"
            f"Why Purpose: {self.why_purpose if self.why_purpose else 'None'}\n"
            f"Affect: {self.affect if self.affect else 'None'}\n"
            f"Why Affect: {self.why_affect if self.why_affect else 'None'}\n"
            f"Action: {self.action if self.action else 'None'}\n"
            f"Why Action: {self.why_action if self.why_action else 'None'}\n"
            f"Dialogue: {self.dialogue if self.dialogue else 'None'}\n"
            f"Why Dialogue: {self.why_dialogue if self.why_dialogue else 'None'}\n"
            f"New Location: {self.new_location if self.new_location else 'None'}\n"
            f"Why New Location: {self.why_new_location if self.why_new_location else 'None'}\n"
            f"New Appearance: {self.new_appearance.model_dump() if self.new_appearance else 'None'}\n"
            f"Why New Appearance: {self.why_new_appearance if self.why_new_appearance else 'None'}\n"
        )
