# Black Box : la mise en ligne, étape par étape

À la fin, tu as :
- **ton application Black Box** à une adresse web à toi, installée sur l'écran d'accueil de ton iPhone, protégée par un mot de passe ;
- **CARO sur Telegram**, le même agent que dans l'app, avec la même mémoire ;
- **une base de données** (SQLite, sur un volume Railway) qui garde la mémoire de CARO, tes rappels, tes trades, les publications et l'état de l'interrupteur ;
- **un vrai interrupteur d'urgence** pour tes bots, dans l'app et dans Telegram.

Compte environ **30 minutes**. Les étapes 1 à 8 suffisent pour que tout roule. L'étape 9 est pour plus tard.

> Les clés et les tokens se mettent **seulement** dans Railway (onglet Variables). Jamais dans un message, une capture d'écran ou un fichier sur GitHub.

---

## ☐ 1. Le bot Telegram (3 min)
1. Dans Telegram, ouvre **@BotFather** (le compte officiel, avec le crochet bleu).
2. Envoie `/newbot`, donne un nom (ex. `CARO`) puis un nom d'utilisateur qui finit par `bot`.
3. Copie le **token** qu'il te donne (il ressemble à `123456789:AAH...`).

## ☐ 2. La clé Claude (5 min)
1. Va sur **platform.claude.com** et connecte-toi.
2. Ajoute un peu de crédit (Billing). Quelques dollars suffisent pour commencer.
3. Dans **API Keys**, crée une clé et copie-la.

## ☐ 3. Le projet Railway (5 min)
1. Va sur **railway.com** et crée un compte avec ton GitHub.
2. **New Project → Deploy from GitHub repo**, puis choisis **IntelTrace2**.
3. Dans le service créé, ouvre **Settings** :
   - **Source → Branch** : `claude/adoring-noether-vu1rei` (ou `main` une fois fusionnée) ;
   - **Root Directory** : `caro_bot`.

Railway installe tout seul et lance `python main.py` (c'est déjà écrit dans `caro_bot/railway.json`).

## ☐ 4. La base de données (1 min)
1. Dans le service, ouvre le menu (clic droit ou ⋮), puis **Attach Volume**.
2. **Mount path** : `/data`.

## ☐ 5. Les variables (3 min)
Dans **Variables**, ajoute :

| Variable | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | le token de l'étape 1 |
| `ANTHROPIC_API_KEY` | la clé de l'étape 2 |
| `APP_PASSWORD` | un mot de passe **long** pour ouvrir l'application (16 caractères ou plus) |
| `CARO_DB` | `/data/caro.db` |

Railway redémarre le service tout seul.

## ☐ 6. L'adresse de ton app (1 min)
1. **Settings → Networking → Generate Domain**.
2. Railway te donne une adresse du genre `blackbox-production-xxxx.up.railway.app`. C'est ton application.

## ☐ 7. Verrouiller CARO sur ton compte Telegram (2 min)
1. Ouvre ton bot dans Telegram et envoie `/start`.
2. Il te répond avec ton **identifiant** (un nombre).
3. Dans Railway, ajoute la variable `TELEGRAM_OWNER_ID` = ce nombre.
4. Après le redémarrage, renvoie `/start` : CARO te présente ses commandes.

## ☐ 8. L'app sur ton iPhone (2 min)
1. Ouvre ton adresse Railway dans **Safari**.
2. Entre ton `APP_PASSWORD`. La session reste ouverte 30 jours.
3. Touche **Partager → Sur l'écran d'accueil**. Black Box s'ouvre maintenant en plein écran, avec son icône.

**C'est en ligne.** Pour vérifier :
- **Wallet → Connexions** affiche « Serveur Railway : En ligne » ;
- **Graphiques** montre les vrais prix (« Gemini » en vert) ;
- le bouton **CARO** répond pour vrai.

---

## ☐ 9. Plus tard, quand tu veux

| Pour… | Ajoute dans Variables | Détails |
|---|---|---|
| Voir tes bots 3Commas dans le garage et avec `/3c` | `THREECOMMAS_API_KEY`, `THREECOMMAS_API_SECRET` | Clé **en lecture seulement** |
| Que l'interrupteur arrête VRAIMENT tes bots | `THREECOMMAS_KILL_API_KEY`, `THREECOMMAS_KILL_API_SECRET` et/ou `FREQTRADE_URL`, `FREQTRADE_USER`, `FREQTRADE_PASSWORD` | 2e clé 3Commas : « Bots read » + « Bots write » seulement |
| La publication quotidienne d'ECHO | `PROMO_CHANNEL`, `PROMO_TIME`, `PROMO_BRIEF` | CARO doit être admin de la chaîne. Tu approuves chaque message |
| Un cerveau de secours si Claude tombe | `OLLAMA_API_KEY` | Clé de ollama.com |

Tous les détails : `caro_bot/README.md`.

---

## Si ça ne marche pas
- **Le déploiement échoue :** dans Railway, regarde **Deployments → View logs**. La ligne « Il manque … » dit quelle variable ajouter.
- **L'app redemande le mot de passe :** vérifie `APP_PASSWORD`. Après 10 essais ratés, attends 10 minutes.
- **CARO répond « Vérifie la clé Anthropic » :** la clé de l'étape 2 est mauvaise ou n'a plus de crédit.
- **Telegram dit « Conflict » :** le bot tourne à deux endroits avec le même token. Arrête l'autre copie.
- **Tu perds la mémoire à chaque mise à jour :** le volume `/data` et `CARO_DB=/data/caro.db` manquent (étape 4).
