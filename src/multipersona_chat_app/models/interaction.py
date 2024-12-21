from pydantic import BaseModel

class Interaction(BaseModel):
    purpose: str        # Short-term goal or current mindset
    affect: str         # Internal feelings/emotions
    action: str         # Visible behavior or action
    new_location: str = ""  # This character's personal location change (if any)
    dialogue: str       # Spoken words (may be empty if no dialogue)

    def format(self) -> str:
        """Format the Interaction object into a human-readable string (for debug/log)."""
        return (
            f"Purpose: {self.purpose}\n"
            f"Affect: {self.affect}\n"
            f"Action: {self.action}\n"
            f"New Location: {self.new_location if self.new_location else 'None'}\n"
            f"Dialogue: {self.dialogue}\n"
        )
