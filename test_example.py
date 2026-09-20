"""Small runnable examples for the academic humanizer and analysers."""

from humanize import HumanizeAI
from advanced_humanize import AdvancedHumanizer
from academic_analyser import AcademicAnalyzer
from literature_review import LiteratureReviewAnalyzer


TEXT = """It is important to note that caste plays a crucial role in shaping
agrarian relations. Jodhka (2004) examines caste and land relations.
However, Gupta (2000) identifies regional variation. This remains
underexplored."""


if __name__ == "__main__":
    editor = AdvancedHumanizer()
    analyser = AcademicAnalyzer()
    lr_analyser = LiteratureReviewAnalyzer()

    print("--- ORIGINAL ---")
    print(TEXT)
    print("\n--- CONSERVATIVE ---")
    print(editor.humanize_literature_review(TEXT, "conservative"))
    print("\n--- STANDARD ---")
    print(editor.humanize_literature_review(TEXT, "standard"))
    print("\n--- POLISH ---")
    print(editor.humanize_literature_review(TEXT, "polish"))
    print("\n--- ACADEMIC DIAGNOSTICS ---")
    print(analyser.summary(TEXT))
    print("\n--- LITERATURE-REVIEW DIAGNOSTICS ---")
    print(lr_analyser.summary(TEXT))
