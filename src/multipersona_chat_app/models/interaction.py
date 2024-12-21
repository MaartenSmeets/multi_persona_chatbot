from pydantic import BaseModel

class Interaction(BaseModel):
    purpose: str        # Short-term goal or current mindset
    affect: str         # Internal feelings/emotions
    action: str         # Visible behavior or action
    dialogue: str       # Spoken words (may be empty if no dialogue)
    new_location: str = ""  # This character's personal location change (if any)
    new_clothing: str = ""  # Description of clothing change (e.g., removing jacket or putting on swimwear)

    def format(self) -> str:
        """Format the Interaction object into a human-readable string (for debug/log)."""
        return (
            f"Purpose: {self.purpose}\n"
            f"Affect: {self.affect}\n"
            f"Action: {self.action}\n"
            f"Dialogue: {self.dialogue}\n"
            f"New Location: {self.new_location if self.new_location else 'None'}\n"
            f"New Clothing: {self.new_clothing if self.new_clothing else 'None'}\n"
        )
