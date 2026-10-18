"""Cerveau de secours : Ollama Cloud, utilisé seulement quand Claude n'est pas disponible.

Pas d'outils ici (prix, rappels, 3Commas, web) : juste la conversation.
"""

import logging

import anthropic
import httpx

from brain import SYSTEM

log = logging.getLogger("caro.backup")

OLLAMA_URL = "https://ollama.com/api/chat"
PREFIX = "(mode secours) "
BACKUP_NOTE = (
    "\n\nMode secours : Claude n'est pas disponible en ce moment. Tu n'as accès à aucun outil "
    "(pas de prix en direct, pas de rappels, pas de 3Commas, pas de web). Si on te demande ça, dis-le simplement."
)


class OllamaBackup:
    def __init__(self, api_key, model="gpt-oss:120b", client=None):
        self.api_key = api_key
        self.model = model
        self.client = client

    async def chat(self, history, user_text):
        messages = [{"role": "system", "content": SYSTEM + BACKUP_NOTE}] + history + [{"role": "user", "content": user_text}]
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=60)
        try:
            r = await client.post(
                OLLAMA_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "stream": False},
            )
        finally:
            if own:
                await client.aclose()
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "").strip()


def claude_unavailable(err):
    """Vrai si l'erreur veut dire que Claude est indisponible, et pas que la configuration est mauvaise."""
    if isinstance(err, anthropic.AuthenticationError):
        return False  # clé refusée : il faut la corriger, pas la cacher
    if isinstance(err, (anthropic.APIConnectionError, anthropic.RateLimitError)):
        return True
    if isinstance(err, anthropic.APIStatusError):
        if err.status_code >= 500:
            return True
        return "credit" in str(err.message).lower()  # crédit épuisé
    return False


async def reply_with_backup(brain, backup, chat_id, user_text):
    """Répond avec Claude ; si Claude est indisponible et qu'un secours existe, répond avec Ollama."""
    try:
        return await brain.reply(chat_id, user_text)
    except Exception as err:
        if backup is None or not claude_unavailable(err):
            raise
        log.warning("Claude indisponible (%s), passage à Ollama", type(err).__name__)
        history = brain.store.recent_history(chat_id)
        text = await backup.chat(history, user_text)
        text = PREFIX + (text or "Je suis en mode secours et j'ai pas de réponse.")
        brain.store.add_turn(chat_id, "user", user_text)
        brain.store.add_turn(chat_id, "assistant", text)
        return text
