from asyncio import gather, to_thread
from re import search
from urllib.parse import urlsplit

from pydantic import HttpUrl

from src.schemas.knowledge import KnowledgeMatch
from src.services.knowledge_documents import extract_url

_CACHE_DOCS = {
    "chrome": "https://support.google.com/accounts/answer/32050?hl=pt-BR",
    "firefox": "https://support.mozilla.org/pt-BR/kb/como-limpar-cache-firefox",
}


async def technical_excerpts(question: str, allowed: list[HttpUrl]) -> list[KnowledgeMatch]:
    if search(r"\b(senha|credencia\w*|token|chave|invas\w*|hack\w*|permiss\w*|excluir|apagar|comando|script)\b", question):
        return []
    urls = [str(url) for url in allowed[:3]]
    if search(r"\b(cache|cookies?)\b", question):
        urls = [_CACHE_DOCS[browser] for browser in _CACHE_DOCS if search(rf"\b{browser}\b", question)] + urls
    matches = await gather(*(_read_page(url) for url in list(dict.fromkeys(urls))[:3]))
    return [match for match in matches if match is not None]


async def _read_page(url: str) -> KnowledgeMatch | None:
    try:
        parsed = urlsplit(url)
        if len(url) > 500 or parsed.scheme != "https" or parsed.port not in {None, 443}:
            return None
        content = (await to_thread(extract_url, url, f"https://{parsed.netloc}", timeout=5, max_bytes=2_000_000)).strip()[:16000]
    except (OSError, ValueError, LookupError):
        return None
    if not content or "A required part of this site couldn" in content:
        return None
    return KnowledgeMatch(source=url, content=content)
