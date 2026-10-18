# Black Box : tous les projets réunis

| Dossier | Ce que c'est |
|---|---|
| `blackbox/app/` | **L'application Black Box** : la salle des bots (20 agents + garage + signaux), les graphiques avec les indicateurs du script CARO, les diagnostics (rentabilité par mois, risque, simulation), le wallet, l'équipe en portraits, les paramètres, et CARO, l'agent vocal qui pilote l'app |
| `blackbox/academie/` | **Académie CARO** : comprendre un agent IA et la route pour bâtir CARO |
| `caro_bot/web/` | L'application servie par ton serveur Railway (reconstruite par `sh caro_bot/web/build.sh` à partir de `blackbox/app/source.html`) |
| `caro_bot/` | **CARO sur Telegram** : le vrai assistant (Claude, mémoire, prix crypto, web, rappels, 3Commas, secours Ollama) |
| `tradingview/` | **Script d'indicateurs TradingView** (Pine Script v6) |

## Ouvrir l'application

- **En vrai, avec ta base de données et tes bots :** suis `DEMARRAGE.md` (Railway).

- En ligne : https://claude.ai/artifact/ALcZCUuRDjgj14BKbZCwZH
- Sur ton ordinateur : ouvre `blackbox/app/index.html` dans un navigateur.
- Sur iPhone : ouvre le lien dans Safari, touche Partager, puis « Sur l'écran d'accueil ».

Ouverte sur claude.ai, l'application lit les vrais prix de ton connecteur Gemini (lecture seule) et CARO utilise Claude pour comprendre ce que tu lui dis. Ouverte depuis ce fichier, elle tourne en démo et CARO passe en mode simple (mots-clés).

L'application affiche pour l'instant des **données de démonstration** pour les trades, les bots et le risque. Elle ne touche à aucun argent. Elle deviendra « en direct » quand le bot CARO tournera sur un serveur.

Les adresses de paiement se remplissent dans l'objet `PAY` de `blackbox/app/index.html`, avec des adresses **publiques** seulement.
