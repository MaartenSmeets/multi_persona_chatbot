from pydantic import BaseModel

class Interaction(BaseModel):
    purpose: str  # Short-term goal for the character
    affect: str   # Internal feelings and emotions
    action: str   # Observable behavior
    dialogue: str # Spoken words
    new_location: str = ""  # If empty, no location change. If non-empty, indicates a location change.

    def format(self) -> str:
        """Format the Interaction object into a displayable string."""
        return (f"Purpose: {self.purpose}\n"
                f"Affect: {self.affect}\n"
                f"Action: {self.action}\n"
                f"Dialogue: {self.dialogue}\n"
                f"New Location: {self.new_location if self.new_location else 'None'}")
