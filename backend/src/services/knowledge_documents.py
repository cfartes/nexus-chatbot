from html.parser import HTMLParser
from io import BytesIO
from os import environ
from subprocess import DEVNULL, PIPE, SubprocessError, TimeoutExpired, run
from sys import executable, stdin, stdout
from typing import Literal
from urllib.parse import urlsplit
from urllib.request import build_opener
from xml.etree.ElementTree import ParseError, fromstring
from zipfile import BadZipFile, ZipFile

from pypdf import Configuration, PdfReader, apply_configuration

from src.services.provider_http import NoRedirect

DocumentFormat = Literal["txt", "pdf", "docx"]
MAX_UPLOAD = 4 * 1024**2
MAX_DOCUMENT_TEXT = 40_000
_PDF_TEXT_LIMIT_EXIT = 42
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentImportError(ValueError):
    pass


def extract_document(kind: DocumentFormat, raw: bytes) -> str:
    try:
        if kind == "txt":
            return raw.decode("utf-8-sig")
        if kind == "docx":
            with ZipFile(BytesIO(raw)) as archive, archive.open("word/document.xml") as document:
                xml = document.read(1_000_001).decode("utf-8-sig")
            if len(xml) > 1_000_000 or "<!DOCTYPE" in xml:
                raise ValueError("Invalid DOCX")
            root = fromstring(xml)
            return "\n".join("".join(node.text or "" for node in paragraph.iter(f"{_WORD}t"))
                             for paragraph in root.iter(f"{_WORD}p"))
        result = run([executable, "-m", __name__], input=raw, stdout=PIPE, stderr=DEVNULL, timeout=10,
                     env={key: environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in environ})
        if result.returncode == _PDF_TEXT_LIMIT_EXIT:
            raise DocumentImportError("O PDF tem mais de 40.000 caracteres de texto. Divida o arquivo em partes menores e tente novamente.")
        result.check_returncode()
        return result.stdout.decode()
    except DocumentImportError:
        raise
    except TimeoutExpired:
        raise DocumentImportError("A leitura do PDF demorou demais. Divida o arquivo em partes menores e tente novamente.") from None
    except (BadZipFile, KeyError, ParseError, OSError, RuntimeError, SubprocessError, ValueError):
        raise DocumentImportError("Não foi possível ler o arquivo. Confira se ele está íntegro e sem senha.") from None


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip is None and tag in {"head", "script", "style", "noscript", "svg"}:
            self._skip = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self._skip:
            self._skip = None

    def handle_data(self, data: str) -> None:
        if self._skip is None and data.strip():
            self.parts.append(data.strip())


def extract_url(url: str, allowed_origin: str | None) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.fragment or f"{parsed.scheme}://{parsed.netloc}" != allowed_origin):
        raise ValueError("URL fora da origem HTTPS autorizada")
    with build_opener(NoRedirect()).open(url, timeout=10) as response:
        body: bytes = response.read(1_000_001)
        if len(body) > 1_000_000 or response.headers.get_content_type() not in {"text/html", "text/plain"}:
            raise ValueError("Formato ou tamanho de página inválido")
        content = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        if response.headers.get_content_type() == "text/plain":
            return content
    parser = _PageText()
    parser.feed(content)
    parser.close()
    return "\n".join(parser.parts)


if __name__ == "__main__":
    apply_configuration(Configuration(
        maximum_declared_stream_length=5_000_000, zlib_maximum_output_length=5_000_000,
        stream_decoding_work_maximum_length=12_000_000, xform_maximum_invocations_per_extraction=100,
        page_tree_maximum_page_entries=100, jbig2dec_binary=None,
    ))
    reader = PdfReader(BytesIO(stdin.buffer.read(MAX_UPLOAD + 1)), strict=True, xref_stream_maximum_entries=10_000)
    output: list[str] = []
    size = 0
    for page in reader.pages:
        content = page.extract_text()
        size += len(content) + 1
        if size > MAX_DOCUMENT_TEXT + 1:
            raise SystemExit(_PDF_TEXT_LIMIT_EXIT)
        output.append(content)
    stdout.buffer.write("\n".join(output).encode())
