#!/usr/bin/env python3
"""
Test examples showing before/after humanization.
"""

from humanize import HumanizeAI
from advanced_humanize import AdvancedHumanizer

def print_comparison(title: str, original: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    print(f"\n🤖 ORIGINAL (Machine-like):")
    print(f"{original}")
    
    basic = HumanizeAI()
    humanized_basic = basic.humanize(original)
    print(f"\n✨ BASIC HUMANIZED:")
    print(f"{humanized_basic}")
    
    advanced = AdvancedHumanizer()
    humanized_advanced = advanced.humanize_complete(original, intensity="medium")
    print(f"\n💬 ADVANCED HUMANIZED (Medium):")
    print(f"{humanized_advanced}")
    
    humanized_heavy = advanced.humanize_complete(original, intensity="heavy")
    print(f"\n🎉 ADVANCED HUMANIZED (Heavy):")
    print(f"{humanized_heavy}")


if __name__ == "__main__":
    # Example 1: Technical explanation
    ex1 = """The implementation of this algorithm requires careful consideration of multiple factors. 
    These include performance optimization, resource allocation, and error handling mechanisms. 
    Furthermore, it is essential to ensure that the system can scale efficiently under varying load conditions. 
    The architectural design must therefore prioritize robustness and maintainability."""
    
    print_comparison("Example 1: Technical Explanation", ex1)
    
    # Example 2: Product description
    ex2 = """This software product provides comprehensive solutions for data management. 
    It is compatible with multiple operating systems and supports various data formats. 
    The installation process is straightforward and does not require extensive technical knowledge. 
    User support is available through multiple channels including email and phone."""
    
    print_comparison("Example 2: Product Description", ex2)
    
    # Example 3: Research summary
    ex3 = """The research indicates that machine learning algorithms can be trained to recognize patterns 
    in large datasets with high accuracy. The performance metrics demonstrate significant improvements 
    over traditional methods. However, further investigation is required to understand the implications 
    for real-world applications."""
    
    print_comparison("Example 3: Research Summary", ex3)
    
    print(f"\n{'='*70}")
    print("  ✅ All examples completed!")
    print(f"{'='*70}\n")
