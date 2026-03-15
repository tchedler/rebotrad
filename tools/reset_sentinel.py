"""
tools/reset_sentinel.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Utilitaire pour réinitialiser le Circuit Breaker (CB)
et les KillSwitches (KS) dans le DataStore après un
arrêt d'urgence (CB3 HALT) ou des tests.

Usage :
    python tools/reset_sentinel.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
import argparse
import logging
from pprint import pprint

# Ajouter la racine du projet au PYTHONPATH pour importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datastore.data_store import DataStore

def main():
    parser = argparse.ArgumentParser(
        description="Réinitialiser l'état de sécurité du bot Sentinel Pro KB5"
    )
    parser.add_argument(
        "--confirm", 
        action="store_true", 
        help="Confirmer l'exécution sans interaction"
    )
    args = parser.parse_args()

    print("==================================================")
    print(" SENTINEL PRO KB5 - RESET DE SÉCURITÉ ")
    print("==================================================")
    print("Cet outil réinitialisera complètement :")
    print("  - Le niveau du Circuit Breaker (CB) à 0 (NOMINAL)")
    print("  - L'état de tous les KillSwitches (KS)")
    print("\nAttention : N'utilisez cet outil que si vous avez résolu")
    print("les problèmes sous-jacents, surtout après un CB3 HALT ou une")
    print("déconnexion prolongée.")
    
    if not args.confirm:
        reply = input("\nVoulez-vous procéder au reset ? (y/n) : ")
        if reply.lower() != 'y':
            print("Action annulée.")
            sys.exit(0)

    print("\n[+] Instanciation du DataStore...")
    ds = DataStore()

    print("[+] Réinitialisation du Circuit Breaker...")
    ds.reset_cb()
    
    print("[+] Réinitialisation des KillSwitches...")
    ds.reset_ks()

    print("\n[+] Verification de l'état :")
    
    print("\nÉtat Circuit Breaker :")
    pprint(ds.get_cb_state())
    
    print("\nKillswitches Actifs :")
    ks_list = ds.get_active_ks_list()
    if ks_list:
        print(f"  Encore actifs : {ks_list}")
    else:
        print("  Aucun KS actif.")

    print("\n==================================================")
    print(" [OK] RESET TERMINE AVEC SUCCES")
    print(" Vous pouvez maintenant relancer Sentinel Pro.")
    print("==================================================")

if __name__ == "__main__":
    # Configurer le logging basique pour voir d'éventuels messages du DataStore
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()
