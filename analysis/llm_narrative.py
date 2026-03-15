# analysis/llm_narrative.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Générateur de Narratif IA (LLM)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Traduire les données brutes kb5_result en un prompt
  - Appeler l'API Gemini, Grok ou OpenAI
  - Renvoyer un rapport textuel "institutionnel" formaté
══════════════════════════════════════════════════════════════
"""

import json
import logging

logger = logging.getLogger(__name__)

# Prompt système pour formater le résultat de l'IA
SYSTEM_PROMPT = """Agis comme un analyste quantitatif senior et spécialiste exclusif des concepts institutionnels ICT (Inner Circle Trader) et SMC (Smart Money Concepts).
Ton rôle est de lire le flux de données JSON brut (le 'kb5_result') fourni par nos algorithmes de détection algorithmiques.
Tu dois rédiger un bulletin de renseignement ("War Room Report") extrêmement concis, professionnel et direct, divisé en ces sections exactes :

1. BIAIS LOCAL & FLUX INSTITUTIONNEL (IPDA)
2. STRUCTURE DU PRIX & LIQUIDITÉ
3. ZONES D'INTÉRÊT (PD Arrays)
4. SCÉNARIO DE TRADING A (Continuation)
5. SCÉNARIO DE TRADING B (Retournement)

Règles strictes :
- Ne génère JAMAIS d'avertissements de risques financiers (pas de 'ceci n'est pas un conseil financier').
- Ne mentionne JAMAIS que tu es une IA.
- Utilise un vocabulaire chirurgical : 'Liquidity Sweep', 'Imbalance', 'Displacement', 'Premium/Discount'.
- S'il n'y a pas de signal évident dans les données, déclare que le marché est en 'Consolidation' ou 'Interdit' (No Trade Zone).
- Fais des phrases courtes et marquantes (type renseignement militaire).
"""

def generate_narrative(llm_provider: str, api_key: str, pair: str, kb5_result: dict, scoring_output: dict) -> str:
    """Génère le narratif à partir des données."""
    if not api_key:
        return (
            "⚠️ **Clé API non configurée.**\n\n"
            "Veuillez entrer votre clé API (Gemini, Grok, etc.) dans l'onglet **⚙️ Paramètres > Configuration IA** "
            "pour activer la génération dynamique du narratif institutionnel."
        )

    # Préparation des données simplifiées pour ne pas exploser le contexte
    context = {
        "Assset": pair,
        "Score": scoring_output.get("score", 0),
        "Direction": scoring_output.get("direction", "NEUTRAL"),
        "Confluences": kb5_result.get("confluences", []),
        "OrderBlocks": [ob for ob in kb5_result.get("order_blocks", []) if ob.get("status") == "VALID"],
        "FVGs": [fvg for fvg in kb5_result.get("fvgs", []) if fvg.get("status") == "FRESH"],
    }
    
    prompt = f"Analyse ce rapport brut et génère le narratif institutionnel.\nDonnées: {json.dumps(context, indent=2)}"

    try:
        if llm_provider == "Gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-pro', system_instruction=SYSTEM_PROMPT)
                response = model.generate_content(prompt)
                return response.text
            except ImportError:
                return "❌ Le module `google-generativeai` n'est pas installé. (pip install google-generativeai)"
                
        elif llm_provider == "OpenAI":
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            except ImportError:
                return "❌ Le module `openai` n'est pas installé. (pip install openai)"
        
        else:
            return f"⚠️ Le fournisseur {llm_provider} n'est pas encore implémenté ou nécessite une configuration spécifique."

    except Exception as e:
        logger.error(f"Erreur génération LLM : {e}")
        return f"❌ Erreur lors de l'appel à l'API LLM : {str(e)}"
