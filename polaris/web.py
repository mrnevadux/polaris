"""Lecture et recherche de pages publiques sur le Web.

Ce module ne se connecte pas à des comptes et ne soumet pas de formulaires.
Il ne prétend donc pas remplacer un navigateur interactif complet.
"""
import ipaddress
import socket
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

TIMEOUT = 15
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
USER_AGENT = "PolarisAssistant/1.0 (public web research)"
TOOL_NAMES = {"web_search", "read_webpage"}
DECLARATIONS = [
    {
        "name": "web_search",
        "description": "Recherche sur le Web public et renvoie des titres, extraits et URL. Pour répondre à une question web, utilise ensuite read_webpage sur les pages pertinentes. N'ouvre pas de compte et n'effectue aucun achat.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Recherche en langage naturel"}}, "required": ["query"]},
    },
    {
        "name": "read_webpage",
        "description": "Récupère et extrait le texte lisible d'une page Web publique en HTTP/HTTPS, sans se connecter ni soumettre de formulaire.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL publique de la page"}}, "required": ["url"]},
    },
]


def _validate_public_url(raw_url: str) -> str:
    parts = urlsplit(raw_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Seules les URL publiques HTTP/HTTPS sont autorisées.")
    if parts.username or parts.password:
        raise ValueError("Les URL avec identifiants intégrés ne sont pas autorisées.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Seuls les ports Web standard 80 et 443 sont autorisés.")
    host = parts.hostname.encode("idna").decode("ascii")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError(f"Impossible de résoudre le site : {exc}") from exc
    if not addresses:
        raise ValueError("Le nom de domaine n'a pas d'adresse publique.")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("L'accès aux adresses locales ou privées est bloqué.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def _get(url: str) -> tuple[str, str, bytes]:
    current = _validate_public_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}
    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            current = _validate_public_url(current)
            with session.get(current, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirection invalide.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                    raise ValueError("Cette ressource n'est pas une page HTML ou texte lisible.")
                chunks, size = [], 0
                for chunk in response.iter_content(32_768):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("La page dépasse la limite de lecture de 2 Mo.")
                    chunks.append(chunk)
                return current, content_type, b"".join(chunks)
    raise ValueError("Trop de redirections.")


def search(query: str) -> str:
    query = query.strip()
    if not query:
        return "Écris ce que tu veux rechercher sur le Web."
    # DuckDuckGo HTML fournit des résultats publics sans ouvrir le navigateur.
    endpoint = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    _, _, body = _get(endpoint)
    soup = BeautifulSoup(body, "html.parser")
    results = []
    for item in soup.select(".result"):
        anchor = item.select_one("a.result__a")
        snippet = item.select_one(".result__snippet")
        if not anchor:
            continue
        title = anchor.get_text(" ", strip=True)
        link = anchor.get("href", "")
        if link.startswith("//"):
            link = "https:" + link
        # DDG utilise parfois un lien de redirection avec l'URL dans uddg.
        parsed = urlsplit(link)
        if "duckduckgo.com" in (parsed.hostname or ""):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                link = target
        try:
            link = _validate_public_url(link)
        except (ValueError, OSError):
            continue
        excerpt = snippet.get_text(" ", strip=True) if snippet else ""
        results.append(f"{len(results) + 1}. {title}\n{excerpt}\nURL: {link}")
        if len(results) >= 6:
            break
    return "\n\n".join(results) if results else "Aucun résultat exploitable trouvé. Essaie une autre formulation."


def read_webpage(url: str) -> str:
    final_url, content_type, body = _get(url)
    encoding = requests.utils.get_encoding_from_headers({"content-type": content_type}) or "utf-8"
    text = body.decode(encoding, errors="replace")
    if "html" in content_type or "xhtml" in content_type:
        soup = BeautifulSoup(text, "html.parser")
        for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            node.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else "Page Web"
        content = " ".join(soup.stripped_strings)
    else:
        title, content = final_url, text
    content = " ".join(content.split())
    if not content:
        return f"La page {final_url} ne contient pas de texte lisible."
    return f"Titre : {title}\nURL : {final_url}\n\n{content[:12000]}"


def execute(name: str, args: dict) -> str:
    if name == "web_search":
        return search(str(args.get("query", "")))
    if name == "read_webpage":
        return read_webpage(str(args.get("url", "")))
    return "Outil Web inconnu."
