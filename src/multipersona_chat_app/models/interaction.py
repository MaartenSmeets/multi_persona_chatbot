from pydantic import BaseModel

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
    new_clothing: str   # New or removed clothing if any
    why_new_clothing: str

    def format(self) -> str:
        """Format the Interaction object into a human-readable string for debugging/logging."""
        return (
            f"Purpose: {self.purpose}\n"
            f"Why Purpose: {self.why_purpose}\n"
            f"Affect: {self.affect}\n"
            f"Why Affect: {self.why_affect}\n"
            f"Action: {self.action}\n"
            f"Why Action: {self.why_action}\n"
            f"Dialogue: {self.dialogue}\n"
            f"Why Dialogue: {self.why_dialogue}\n"
            f"New Location: {self.new_location if self.new_location else 'None'}\n"
            f"Why New Location: {self.why_new_location if self.why_new_location else 'None'}\n"
            f"New Clothing: {self.new_clothing if self.new_clothing else 'None'}\n"
            f"Why New Clothing: {self.why_new_clothing if self.why_new_clothing else 'None'}\n"
        )