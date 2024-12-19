from pydantic import BaseModel

class Interaction(BaseModel):
    purpose: str  # Short-term goal for the character
    affect: str   # Internal feelings and emotions
    action: str   # Observable behavior
    dialogue: str # Spoken words

    def format(self) -> str:
        """Format the Interaction object into a displayable string."""
        return (f"Purpose: {self.purpose}\n"
                f"Affect: {self.affect}\n"
                f"Action: {self.action}\n"
                f"Dialogue: {self.dialogue}")