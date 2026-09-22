from .models import DecisionRequired

def decision_required(question,evidence,possible_interpretations,why_it_matters):
 return DecisionRequired(question,evidence,possible_interpretations,why_it_matters)
