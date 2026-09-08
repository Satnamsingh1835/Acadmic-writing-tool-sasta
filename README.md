# Humanize AI Responses

Make AI-generated text sound more natural and human-like instead of robotic and mechanical.

## Features

### Basic Humanization (`humanize.py`)
- **Add Contractions**: Converts formal phrases to conversational ones ("do not" → "don't")
- **Break Long Sentences**: Splits verbose sentences into shorter, punchier ones
- **Add Personality**: Inserts natural filler words for conversational flow

### Advanced Humanization (`advanced_humanize.py`)
- **Hedging Phrases**: Softens absolute statements ("I think", "It seems")
- **Sentence Structure Variation**: Varies sentence length for natural rhythm
- **Remove Redundancy**: Eliminates repeated words and phrases
- **Emphasis Variation**: Replaces bland descriptors with more expressive alternatives
- **Rhetorical Questions**: Adds engaging questions for reader engagement

## Installation

```bash
git clone https://github.com/Satnamsingh1835/humanize-ai-responses.git
cd humanize-ai-responses
```

No external dependencies required! Uses only Python standard library.

## Quick Start

### Basic Usage

```python
from humanize import HumanizeAI

humanizer = HumanizeAI()

machine_text = """The implementation of this algorithm requires careful consideration. 
Furthermore, it is essential to ensure proper error handling."""

humanized = humanizer.humanize(machine_text)
print(humanized)
```

### Advanced Usage

```python
from advanced_humanize import AdvancedHumanizer

humanizer = AdvancedHumanizer()

text = "Machine learning is important and has good applications."

# Light humanization
light = humanizer.humanize_complete(text, intensity="light")

# Medium humanization (default)
medium = humanizer.humanize_complete(text, intensity="medium")

# Heavy humanization
heavy = humanizer.humanize_complete(text, intensity="heavy")
```

## Example Transformations

### Before (Machine-like)
```
The implementation of this algorithm requires careful consideration of multiple factors. 
These include performance optimization, resource allocation, and error handling mechanisms. 
Furthermore, it is essential to ensure that the system can scale efficiently under varying load conditions.
```

### After (Human-like)
```
Well, implementing this algorithm, you know, requires thinking about several things. 
That's performance optimization, resource allocation, and how you handle errors. 
You basically want to make sure the system scales well when the load changes. 
Right?
```

## Key Techniques

1. **Contractions**: Use "don't" instead of "do not"
2. **Short Sentences**: Break complex ideas into bite-sized chunks
3. **Filler Words**: Strategically add "like", "basically", "I think"
4. **Varied Structure**: Mix short and long sentences
5. **Hedging**: Soften claims with "I think", "It seems"
6. **Rhetorical Questions**: Engage readers with "Right?", "Make sense?"
7. **Emphasis**: Use varied intensity descriptors

## Intensity Levels

- **Light**: Subtle changes, preserves formality
- **Medium**: Balanced humanization for most use cases
- **Heavy**: Maximum natural flow, very conversational

## Use Cases

✅ ChatGPT response humanization  
✅ Blog post generation  
✅ Social media content  
✅ Email writing assistance  
✅ Customer support responses  
✅ Tutorial and documentation writing  

## Contributing

Feel free to submit PRs with:
- New humanization techniques
- Better filler words and phrases
- Improved sentence variation logic
- Bug fixes

## License

MIT License - feel free to use in your projects!

## Author

Created by Satnamsingh1835
