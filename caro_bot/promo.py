"""ECHO : la publication quotidienne sur le projet crypto, toujours approuvée par le propriétaire avant d'être publiée."""

from datetime import time

ECHO_SYSTEM = """Tu es ECHO, l'agent contenu de l'équipe Black Box. Tu écris UNE publication pour une chaîne Telegram communautaire sur un projet crypto de Charlevoix.

Règles, toutes obligatoires :
- Français québécois naturel, ton chaleureux et local. 300 à 700 caractères. Pas de Markdown, au plus 3 émojis.
- Parle du projet, de la communauté, de Charlevoix, des étapes réelles du projet données dans la fiche. Varie le sujet d'un jour à l'autre et ne répète pas les publications précédentes.
- Aucune promesse de prix, de rendement, de profit ou de « x10 ». Pas de « achète maintenant », pas de fausse urgence, pas de faux chiffres, pas de partenariat inventé. Utilise seulement les faits de la fiche.
- Termine par la ligne : « Pas un conseil financier. Les cryptos peuvent perdre toute leur valeur. »
- Si la fiche contient une divulgation (ex. l'équipe détient des jetons), inclus-la telle quelle.
Réponds seulement avec le texte de la publication."""


def parse_hhmm(value, tz):
    h, m = (value or "09:00").strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Heure invalide : utilise HH:MM, ex. 09:00")
    return time(h, m, tzinfo=tz)


async def draft_post(client, model, brief, recent, today):
    previous = "\n---\n".join(recent) if recent else "(aucune)"
    prompt = (
        f"Date : {today}\n\nFiche du projet (seule source de faits) :\n{brief}\n\n"
        f"Publications précédentes, à ne pas répéter :\n{previous}\n\nÉcris la publication du jour."
    )
    resp = await client.messages.create(
        model=model,
        max_tokens=4000,
        system=ECHO_SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude a refusé d'écrire cette publication.")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Publication vide.")
    return text
