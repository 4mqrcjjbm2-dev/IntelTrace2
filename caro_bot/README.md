# CARO sur Telegram

CARO est ton assistant personnel dans Telegram. Il est propulsé par Claude et ne répond qu'à toi.

| Tu écris | CARO fait |
|---|---|
| N'importe quelle question | Il répond en québécois et se souvient de la conversation |
| « ça vaut combien l'ETH? » ou `/prix btc sol` | Il lit le prix en $ CA et $ US sur CoinGecko. Lecture seulement, il ne passe jamais d'ordre |
| « c'est quoi les nouvelles sur Bitcoin aujourd'hui? » | Il cherche sur le web et nomme ses sources |
| « rappelle-moi demain à 9 h d'appeler Marc » | Il t'écrit dans Telegram à l'heure dite |
| `/rappels`, `/annule 3` | Il liste ou supprime tes rappels |
| `/oublie` | Il efface sa mémoire de la conversation |
| « comment vont mes bots? » ou `/3c` | Il lit tes trades 3Commas ouverts (`/3c bots` pour tes bots). Lecture seulement |

## 1. Crée ton bot dans Telegram (5 minutes)

1. Dans Telegram, ouvre une conversation avec **@BotFather** (le compte officiel, avec le crochet bleu).
2. Envoie `/newbot`, puis donne un nom (ex. `CARO`) et un nom d'utilisateur qui finit par `bot` (ex. `caro_blackbox_bot`).
3. BotFather te donne un **token** qui ressemble à `123456789:AAH...`. C'est le mot de passe de ton bot : garde-le secret.

## 2. Prépare le fichier `.env`

Dans le dossier `caro_bot`, copie `.env.example` en `.env`, puis remplis :

- `TELEGRAM_BOT_TOKEN` : le token de BotFather ;
- `ANTHROPIC_API_KEY` : ta clé de [platform.claude.com](https://platform.claude.com) ;
- `TELEGRAM_OWNER_ID` : laisse ce champ vide pour l'instant (étape 4).

Le `.env` est déjà exclu de Git. Ne le mets jamais sur GitHub et ne l'envoie à personne.

## 3. Lance CARO

### Option A : sur ton ordinateur (gratuit)

Il faut Python 3.10 ou plus.

```bash
cd caro_bot
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

CARO répond tant que ton ordinateur est allumé et que la commande tourne.

### Option B : sur Railway (en ligne 24 h sur 24)

1. Crée un compte sur [railway.com](https://railway.com). Le forfait de base coûte environ 5 $ US par mois ; vérifie leur page de prix.
2. **New Project → Deploy from GitHub repo**, puis choisis `IntelTrace2` et la bonne branche.
3. Dans **Settings** du service :
   - **Root Directory** : `caro_bot`. Railway installe alors les dépendances de `caro_bot/requirements.txt` et lance `python bot.py`, comme indiqué dans `railway.json`.
4. Dans **Variables**, ajoute les mêmes valeurs que dans le `.env`.
5. Ajoute un **Volume** monté sur `/data`, puis la variable `CARO_DB=/data/caro.db`. Sans volume, la mémoire et les rappels sont effacés à chaque redéploiement.

Ne lance jamais CARO à deux endroits en même temps avec le même token. Telegram refuse et une des copies plante avec une erreur « Conflict ».

## 4. Verrouille CARO sur ton compte

1. Ouvre ton bot dans Telegram et envoie `/start`.
2. CARO te répond avec ton identifiant, un nombre comme `123456789`.
3. Mets ce nombre dans `TELEGRAM_OWNER_ID` (dans le `.env`, ou dans les variables Railway), puis redémarre le bot.
4. Envoie `/start` de nouveau : CARO est en ligne et ignore tous les autres comptes.

## Brancher 3Commas (optionnel, lecture seule)

1. Dans 3Commas : **Mon profil → Accès API → Nouvelle clé API**, puis choisis une clé générée par le système.
2. Coche **seulement la permission de lecture** (« Bots read » et « Accounts read », ou « Read only »). Ne coche jamais les permissions de modification (« write ») ou de trading.
3. Si 3Commas le propose, limite la clé à l'adresse IP de ton serveur.
4. Copie la clé et le secret dans `THREECOMMAS_API_KEY` et `THREECOMMAS_API_SECRET`, puis redémarre CARO.
5. Teste avec `/3c` dans Telegram.

CARO peut seulement lire. Il ne peut ni lancer, ni arrêter, ni modifier un bot ou un trade. Sur ta plateforme d'échange, la clé donnée à 3Commas ne doit jamais avoir le droit de retirer des fonds.

## Réglages

| Variable | Défaut | À quoi ça sert |
|---|---|---|
| `CARO_MODEL` | `claude-opus-5-5` | Le modèle Claude. `claude-sonnet-5-5` coûte environ deux fois moins cher |
| `CARO_EFFORT` | `low` | Profondeur de réflexion : `low`, `medium` ou `high`. Plus haut = plus lent et plus cher |
| `CARO_TZ` | `America/Toronto` | Ton fuseau horaire pour les rappels |
| `CARO_DB` | `caro_bot/caro.db` | Où sont gardés la mémoire et les rappels |

## Combien ça coûte

- **Claude Opus 5.5 :** 4 $ US par million de jetons lus et 20 $ US par million de jetons écrits. Un message ordinaire à CARO revient à environ 1 à 3 cents US. Une recherche web coûte un peu plus. Tu vois ta consommation réelle sur platform.claude.com.
- **CoinGecko :** gratuit, sans clé.
- **Telegram :** gratuit.
- **Railway :** environ 5 $ US par mois si tu choisis l'option B.

## Sécurité

- **Ton compte seulement :** CARO ignore tout autre compte Telegram dès que `TELEGRAM_OWNER_ID` est rempli.
- **Le web, c'est de l'information :** ce qu'il lit sur le web est traité comme des données, pas comme des ordres.
- **Crypto en lecture seule :** il lit les prix seulement. Il n'a accès à aucun portefeuille et ne peut rien acheter ni vendre.
- **Refus de sécurité :** si Claude refuse une demande pour une raison de sécurité, l'API la rejoue automatiquement sur un autre modèle (`fallbacks: "default"`). Ce réglage est dans `brain.py`.
- **Si ton token ou ta clé fuit :** révoque le token avec `/revoke` dans @BotFather et supprime la clé sur platform.claude.com.

## Tests

```bash
pip install pytest
python -m pytest tests
```

Les tests n'utilisent ni Telegram, ni l'API Claude, ni Internet.
