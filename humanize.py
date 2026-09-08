import random
import re
from typing import List

class HumanizeAI:
    """
    Converts machine-like AI responses into more natural, human-like text.
    """
    
    def __init__(self):
        # Filler words and phrases to add natural flow
        self.filler_words = [
            "you know", "I mean", "like", "actually", "honestly",
            "kind of", "sort of", "basically", "essentially", "I think",
            "in my opinion", "to be honest"
        ]
        
        # Transitional phrases for better flow
        self.transitions = [
            "Here's the thing:",
            "So basically,",
            "The way I see it,",
            "What I mean is,",
            "Let me explain:",
            "Here's my take:",
            "In other words,"
        ]
        
        # Conversational starters
        self.starters = [
            "Well, ",
            "So, ",
            "Look, ",
            "Actually, ",
            "You know what, "
        ]
    
    def add_contractions(self, text: str) -> str:
        """
        Replace formal phrases with conversational contractions.
        """
        replacements = {
            r'\bdo not\b': "don't",
            r'\bcannot\b': "can't",
            r'\bwill not\b': "won't",
            r'\bcould not\b': "couldn't",
            r'\bshould not\b': "shouldn't",
            r'\bwould not\b': "wouldn't",
            r'\bit is\b': "it's",
            r'\bthere is\b': "there's",
            r'\bhave been\b': "been",
            r'\bI am\b': "I'm",
            r'\byou are\b': "you're",
            r'\bthat is\b': "that's",
        }
        
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def break_long_sentences(self, text: str, max_length: int = 60) -> str:
        """
        Break long sentences into shorter, more conversational ones.
        """
        sentences = text.split('. ')
        result = []
        
        for sentence in sentences:
            if len(sentence) > max_length:
                # Split on conjunctions
                parts = re.split(r'\s+(and|but|because|however|therefore)\s+', sentence)
                current = ""
                
                for part in parts:
                    if current and len(current) + len(part) > max_length:
                        result.append(current.strip())
                        current = part
                    else:
                        current += " " + part if current else part
                
                if current:
                    result.append(current.strip())
            else:
                result.append(sentence)
        
        return '. '.join(result) + '.'
    
    def add_personality(self, text: str) -> str:
        """
        Add subtle personality and filler words for natural flow.
        """
        # Add occasional fillers to longer sentences
        sentences = text.split('. ')
        result = []
        
        for i, sentence in enumerate(sentences):
            if len(sentence.split()) > 10 and random.random() < 0.3:
                # Insert filler word randomly
                words = sentence.split()
                insert_pos = random.randint(2, len(words) - 2)
                filler = random.choice(self.filler_words)
                words.insert(insert_pos, filler)
                sentence = ' '.join(words)
            
            result.append(sentence)
        
        return '. '.join(result) + '.'
    
    def humanize(self, text: str) -> str:
        """
        Main method: Apply all humanization techniques.
        """
        if not text:
            return text
        
        # Step 1: Add contractions
        text = self.add_contractions(text)
        
        # Step 2: Break long sentences
        text = self.break_long_sentences(text)
        
        # Step 3: Add personality
        text = self.add_personality(text)
        
        # Step 4: Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text


# Example usage
if __name__ == "__main__":
    humanizer = HumanizeAI()
    
    # Machine-like response
    machine_text = """The implementation of this algorithm requires careful consideration of multiple factors. 
    These include performance optimization, resource allocation, and error handling mechanisms. 
    Furthermore, it is essential to ensure that the system can scale efficiently under varying load conditions. 
    The architectural design must therefore prioritize robustness and maintainability."""
    
    # Humanized response
    human_text = humanizer.humanize(machine_text)
    
    print("ORIGINAL (Machine-like):")
    print(machine_text)
    print("\n" + "="*60 + "\n")
    print("HUMANIZED:")
    print(human_text)
