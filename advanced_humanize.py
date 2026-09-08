import re
from typing import Dict, List, Tuple
import random

class AdvancedHumanizer:
    """
    Advanced techniques to make AI responses sound more natural and human.
    """
    
    def __init__(self):
        self.emotion_markers = [
            "😊", "🤔", "👍", "💡", "✨"
        ]
        
        self.hedging_phrases = [
            "I think", "I believe", "It seems", "It appears",
            "In my view", "From what I understand"
        ]
        
        self.emphasis_words = {
            "good": ["really good", "quite good", "pretty great"],
            "important": ["really important", "super important", "quite crucial"],
            "interesting": ["quite interesting", "pretty fascinating", "really cool"],
            "difficult": ["pretty tricky", "quite challenging", "really tough"]
        }
    
    def add_hedging(self, text: str, intensity: float = 0.3) -> str:
        """
        Add hedging phrases to soften absolute statements.
        Makes responses sound less robotic and more thoughtful.
        """
        sentences = text.split('. ')
        result = []
        
        for sentence in sentences:
            if random.random() < intensity and not any(phrase in sentence for phrase in self.hedging_phrases):
                if sentence[0].isupper():
                    hedging = random.choice(self.hedging_phrases)
                    sentence = f"{hedging}, {sentence[0].lower()}{sentence[1:]}"
            
            result.append(sentence)
        
        return '. '.join(result) + '.'
    
    def vary_sentence_structure(self, text: str) -> str:
        """
        Vary sentence length and structure for natural rhythm.
        """
        sentences = text.split('. ')
        
        if len(sentences) > 3:
            # Randomly reorder some sentences for variety (while maintaining meaning)
            # Avoid reordering dependent clauses
            if random.random() < 0.4:
                for _ in range(min(2, len(sentences) - 1)):
                    i = random.randint(0, len(sentences) - 2)
                    if sentences[i] and sentences[i+1]:
                        sentences[i], sentences[i+1] = sentences[i+1], sentences[i]
        
        return '. '.join(sentences) + '.'
    
    def remove_redundancy(self, text: str) -> str:
        """
        Remove repetitive words and phrases.
        """
        # Remove repeated words
        words = text.split()
        result = [words[0]] if words else []
        
        for word in words[1:]:
            if word.lower() != result[-1].lower():
                result.append(word)
        
        return ' '.join(result)
    
    def add_emphasis_variation(self, text: str) -> str:
        """
        Replace bland descriptors with more natural emphasis.
        """
        for bland, alternatives in self.emphasis_words.items():
            if re.search(rf'\b{bland}\b', text, re.IGNORECASE):
                replacement = random.choice(alternatives)
                text = re.sub(rf'\b{bland}\b', replacement, text, flags=re.IGNORECASE, count=1)
        
        return text
    
    def add_rhetorical_questions(self, text: str, probability: float = 0.15) -> str:
        """
        Add occasional rhetorical questions for engagement.
        """
        sentences = text.split('. ')
        result = []
        
        for i, sentence in enumerate(sentences):
            result.append(sentence)
            
            # Add rhetorical question after certain sentences
            if (i < len(sentences) - 1 and random.random() < probability and 
                len(sentence.split()) > 8):
                questions = [
                    "Do you see?",
                    "Make sense?",
                    "Right?",
                    "You know?",
                    "See what I mean?"
                ]
                result.append(random.choice(questions))
        
        return '. '.join(result) + '.'
    
    def humanize_complete(self, text: str, intensity: str = "medium") -> str:
        """
        Complete humanization pipeline.
        intensity: "light", "medium", or "heavy"
        """
        intensity_map = {"light": 0.2, "medium": 0.4, "heavy": 0.6}
        intensity_val = intensity_map.get(intensity, 0.4)
        
        text = self.remove_redundancy(text)
        text = self.add_emphasis_variation(text)
        text = self.add_hedging(text, intensity=intensity_val)
        text = self.vary_sentence_structure(text)
        text = self.add_rhetorical_questions(text, probability=intensity_val * 0.3)
        
        return text


# Example
if __name__ == "__main__":
    humanizer = AdvancedHumanizer()
    
    text = """Machine learning is an important field that has applications in many industries. 
    The technology is powerful and can solve complex problems. Good results require good data. 
    This approach is different from traditional programming approaches."""
    
    print("ORIGINAL:")
    print(text)
    print("\n" + "="*60 + "\n")
    print("HUMANIZED (Medium Intensity):")
    print(humanizer.humanize_complete(text, intensity="medium"))
    print("\n" + "="*60 + "\n")
    print("HUMANIZED (Heavy Intensity):")
    print(humanizer.humanize_complete(text, intensity="heavy"))
