# CARO · Indicateurs Black Box (TradingView)

Un seul indicateur qui regroupe ce que tu ajouterais normalement un par un. Il roule directement dans TradingView : aucun jeton Claude, aucun coût.

| Sur le graphique | Ce que ça montre |
|---|---|
| Ligne bleue, ligne mauve, ligne orange épaisse | EMA 20, 50 et 200 : la tendance à court, moyen et long terme |
| Bande grise | Bandes de Bollinger (20, 2) : la volatilité |
| Fond vert ou rouge | Tendance haussière (prix au-dessus de l'EMA 200 et EMA 20 > EMA 50) ou baissière |
| Triangle HAUSSE / BAISSE | L'EMA 20 croise l'EMA 50, confirmé par le RSI (au-dessus ou au-dessous de 50) et le MACD |
| Petit point orange / bleu | Le RSI entre en zone surachetée (70) ou survendue (30) |
| Tableau en haut à droite | Tendance, RSI, MACD et écart du prix avec l'EMA 200 |

## L'installer

1. Sur [tradingview.com](https://www.tradingview.com), ouvre un graphique.
2. En bas de l'écran, ouvre l'onglet **Pine Editor**.
3. Efface le code qui s'y trouve, puis colle tout le contenu de `caro_indicateurs.pine`.
4. Clique **Enregistrer**, puis **Ajouter au graphique**.
5. Pour changer les longueurs, les zones RSI ou cacher un élément, clique la roue dentée à côté du nom « CARO ».

Si TradingView affiche une erreur en rouge dans le Pine Editor, copie le message et envoie-le à Claude pour qu'il corrige le script.

## Créer une alerte

1. Clique l'icône de réveil (**Alerte**) en haut du graphique.
2. Dans **Condition**, choisis **CARO**, puis un des signaux : croisement haussier, croisement baissier, RSI suracheté ou survendu.
3. Choisis comment être averti : une notification dans l'app TradingView, un courriel ou un webhook.

Selon ton forfait TradingView, le nombre d'alertes actives est limité.

Le message de l'alerte peut plus tard être remplacé par le message JSON d'un Signal Bot 3Commas, pour que l'alerte ouvre un trade. Fais-le seulement après avoir testé la stratégie.

## À savoir

Ces signaux décrivent ce que le prix **a fait**, pas ce qu'il va faire. Les croisements de moyennes arrivent en retard et donnent beaucoup de faux signaux quand le marché tourne en rond. Utilise-les pour t'aider à lire un graphique, pas comme un ordre d'achat ou de vente, et teste toute stratégie sur l'historique avant d'y mettre de l'argent.
