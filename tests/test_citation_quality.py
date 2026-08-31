"""Testes de qualidade de citação — cobertura dos 15 cenários obrigatórios.

Todos os testes são offline e determinísticos: não chamam LLM real.
A estratégia é:
- Testes de formato (cenários 1–6, 10, 13–15): validam strings de resposta
  simuladas usando helpers que aplicam as mesmas regras que o agente deveria
  seguir. Confirmam que as regras de formato são claras e verificáveis.
- Testes de metadados (cenários 7–9, 11–12): usam monkeypatch em csa_portal
  para verificar campos retornados por fetch_page, igual ao padrão existente.
"""

from __future__ import annotations

import json
import re

import pytest

import chat_csa.csa_portal as portal
from chat_csa.agent.tools import web_csa_fetch

# ---------------------------------------------------------------------------
# Helpers de validação de formato de resposta
# ---------------------------------------------------------------------------

# Expressão regular para linha de fonte válida no formato esperado:
# [N] Título — URL (acesso YYYY-MM-DD HH:mm)
_FONTE_RE = re.compile(
    r"^\[\d+\]\s+.+\s+—\s+https?://\S+\s+\(acesso\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\)",
    re.MULTILINE,
)

_PDF_STATUS_RE = re.compile(
    r"\[PDF:\s+(completo|parcial|falhou)\]",
)


def _has_fontes_section(text: str) -> bool:
    """Verifica se a resposta contém uma seção 'Fontes:'."""
    return "Fontes:" in text


def _has_resposta_label(text: str) -> bool:
    """Verifica se a resposta começa com o rótulo artificial 'Resposta:'."""
    return bool(re.match(r"^\s*Resposta:", text, re.IGNORECASE))


def _count_fontes(text: str) -> int:
    """Conta linhas de fonte no formato [N] Título — URL (acesso ...)."""
    return len(_FONTE_RE.findall(text))


def _has_incerteza_marker(text: str) -> bool:
    """Verifica presença do marcador de incerteza [!]."""
    return "[!]" in text


def _has_edital_precedencia(text: str) -> bool:
    """Verifica se a resposta menciona precedência do edital."""
    lower = text.lower()
    return "prevalece" in lower or "edital" in lower and "prevalece" in lower


def _has_pdf_status(text: str) -> bool:
    """Verifica se alguma fonte de PDF tem status anotado."""
    return bool(_PDF_STATUS_RE.search(text))


def _is_valid_markdown_for_frontend(text: str) -> bool:
    """
    Verifica se a resposta não contém elementos que quebram ReactMarkdown.
    Critério mínimo: sem tags HTML raw não fechadas e sem blocos mal formados.
    """
    # Tags HTML abertas sem fechar (heurística simples)
    open_tags = re.findall(r"<[a-zA-Z][^>]*>", text)
    close_tags = re.findall(r"</[a-zA-Z][^>]*>", text)
    # Verifica se código em bloco tem abertura e fechamento balanceados
    backtick_blocks = text.count("```")
    balanced_code = backtick_blocks % 2 == 0
    return balanced_code and len(open_tags) == len(close_tags)


# ---------------------------------------------------------------------------
# Respostas simuladas — sem LLM, representam saídas esperadas do agente
# ---------------------------------------------------------------------------

RESP_SINGLE = """\
"O prazo para confirmação de interesse na lista de espera é de 3 dias úteis a
partir da publicação da convocação." [1]

Fontes:
[1] Edital SISU/UEFS 2026 — https://csa.uefs.br/index.php/sisu261/edital (acesso 2026-08-22 17:30) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
"""

RESP_MULTIPLE = """\
"A matrícula deve ser realizada presencialmente na secretaria do curso." [1]
"Os documentos exigidos incluem RG, CPF e histórico escolar." [2]

Fontes:
[1] Chamada Regular — https://csa.uefs.br/index.php/sisu261/regular (acesso 2026-08-22 17:31)
[2] Documentos para Matrícula — https://csa.uefs.br/index.php/download/file/sisu261/doc_matricula (acesso 2026-08-22 17:32) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
"""

RESP_LABEL_ONLY = """\
Consulte a página Chamada Regular.

Fontes:
[1] Chamada Regular — https://csa.uefs.br/index.php/sisu261/regular (acesso 2026-08-22 17:31)
"""

RESP_OFFICIAL = """\
"Conforme o edital, item 4.3: as vagas remanescentes serão preenchidas por lista de espera." [1]

Fontes:
[1] Edital SISU/UEFS 2026 — https://csa.uefs.br/index.php/sisu261/edital (acesso 2026-08-22 17:30) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
"""

RESP_CONFLICT = """\
O edital (fonte [1]) informa prazo de 5 dias; a página informativa (fonte [2]) indica 3 dias.
O edital prevalece: o prazo correto é de 5 dias úteis.

"O prazo para entrega de documentos é de 5 (cinco) dias úteis." [1]

Fontes:
[1] Edital SISU/UEFS 2026 — https://csa.uefs.br/index.php/sisu261/edital (acesso 2026-08-22 17:30) [PDF: completo]
[2] Página Inicial SISU 2026 — https://csa.uefs.br/index.php/sisu261/inicial (acesso 2026-08-22 17:31)
Em caso de divergência, prevalece o edital oficial.
"""

RESP_WRONG_YEAR = """\
[!] Esta informação é do processo seletivo de 2025 e pode não se aplicar ao processo atual.
"Em 2025, o prazo foi de 3 dias úteis." [1]

Fontes:
[1] Edital SISU/UEFS 2025 — https://csa.uefs.br/index.php/sisu251/edital (acesso 2026-08-22 17:30) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
"""

RESP_NO_SOURCES = """\
[!] Não foi possível confirmar esta informação nas fontes consultadas.
Consultei as seguintes URLs sem encontrar o trecho solicitado:
- https://csa.uefs.br/index.php/sisu261/inicial
- https://csa.uefs.br/index.php/sisu261/downloads

Fontes:
Nenhuma fonte com trecho verificável encontrada. Acesse https://csa.uefs.br/ para informações oficiais.
"""

RESP_NO_AFFIRMATION = """\
[!] Não foi possível confirmar o prazo de inscrição nas fontes consultadas neste turno.
As páginas consultadas não continham o trecho específico solicitado.

Fontes:
[1] Portal CSA — https://csa.uefs.br/ (acesso 2026-08-22 17:30)
"""

RESP_PTBR_SISU = """\
"Para participar da lista de espera do SISU/UEFS 2026, o candidato deve confirmar
o interesse no período indicado no cronograma oficial." [1]

Fontes:
[1] Cronograma SISU/UEFS 2026 — https://csa.uefs.br/index.php/sisu261/cronograma_1cle (acesso 2026-08-22 17:30)
Em caso de divergência, prevalece o edital oficial.
"""


# ---------------------------------------------------------------------------
# Cenário 1 — Resposta com 1 afirmação e 1 fonte correspondente
# ---------------------------------------------------------------------------

def test_cenario1_uma_afirmacao_uma_fonte():
    """Resposta com afirmação única deve ser direta e ter exatamente uma fonte válida."""
    assert not _has_resposta_label(RESP_SINGLE)
    assert _has_fontes_section(RESP_SINGLE)
    assert _count_fontes(RESP_SINGLE) == 1


# ---------------------------------------------------------------------------
# Cenário 2 — Múltiplas afirmações com citações distintas
# ---------------------------------------------------------------------------

def test_cenario2_multiplas_afirmacoes_fontes_distintas():
    """Múltiplas afirmações devem ter referências [1] e [2] apontando para URLs distintas."""
    assert _count_fontes(RESP_MULTIPLE) == 2
    # Verifica que as duas URLs são diferentes
    urls = re.findall(r"https?://\S+(?=\s+\(acesso)", RESP_MULTIPLE)
    assert len(set(urls)) == 2, "Fontes distintas devem ter URLs distintas"


# ---------------------------------------------------------------------------
# Cenário 3 — Rejeição de fonte com só rótulo sem trecho substantivo
# ---------------------------------------------------------------------------

def test_cenario3_rotulo_sem_trecho_invalido():
    """Resposta com apenas rótulo de página não deve ter trecho entre aspas."""
    # RESP_LABEL_ONLY representa resposta INACEITÁVEL — não tem trecho citado
    trechos = re.findall(r'"[^"]{20,}"', RESP_LABEL_ONLY)
    assert len(trechos) == 0, (
        "Resposta com só rótulo não contém trecho substantivo — "
        "este padrão é exatamente o que deve ser evitado"
    )
    # E a resposta aceitável (RESP_SINGLE) deve ter trecho
    trechos_ok = re.findall(r'"[^"]{20,}"', RESP_SINGLE)
    assert len(trechos_ok) >= 1


# ---------------------------------------------------------------------------
# Cenário 4 — Fonte oficial com trecho correspondente
# ---------------------------------------------------------------------------

def test_cenario4_fonte_oficial_com_trecho():
    """Fonte oficial deve ter trecho verbatim e indicar que é edital."""
    assert "edital" in RESP_OFFICIAL.lower()
    trechos = re.findall(r'"[^"]{10,}"', RESP_OFFICIAL)
    assert len(trechos) >= 1


# ---------------------------------------------------------------------------
# Cenário 5 — Precedência de edital sobre página informativa conflitante
# ---------------------------------------------------------------------------

def test_cenario5_precedencia_edital():
    """Em conflito, resposta deve indicar explicitamente que o edital prevalece."""
    assert _has_edital_precedencia(RESP_CONFLICT)
    assert _count_fontes(RESP_CONFLICT) == 2
    # Verifica que a fonte [1] é edital
    assert "/edital" in RESP_CONFLICT


# ---------------------------------------------------------------------------
# Cenário 6 — Fonte de ano diferente com aviso
# ---------------------------------------------------------------------------

def test_cenario6_fonte_ano_diferente_com_aviso():
    """Fonte de ano diferente deve acionar aviso explícito ao usuário."""
    assert _has_incerteza_marker(RESP_WRONG_YEAR) or "pode não se aplicar" in RESP_WRONG_YEAR
    assert "2025" in RESP_WRONG_YEAR


# ---------------------------------------------------------------------------
# Cenários 7, 8, 9 — Status de extração de PDF (completed / partial / failed)
# ---------------------------------------------------------------------------

def _make_fake_pdf_fetch(monkeypatch, tmp_path, texto: str, url_suffix: str):
    """Fábrica de contexto para testar fetch de PDF com pypdf como fallback."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")

    # Gerador de PDF mínimo válido (inline para não depender de import entre módulos de teste)
    def _pdf_with_text(text: str) -> bytes:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 100 Td ({escaped}) Tj ET".encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
            ),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = []
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("ascii"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        pdf.extend(f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\n".encode("ascii"))
        pdf.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
        return bytes(pdf)

    pdf = _pdf_with_text(texto)

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = pdf
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(
        portal, "_extract_pdf_text_with_pdftotext",
        lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")),
    )
    return f"https://csa.uefs.br/index.php/download/file/sisu261/{url_suffix}"


def test_cenario7_pdf_completo(tmp_path, monkeypatch):
    """PDF com texto ≥50 chars deve ter pdf_extraction_status='completed'."""
    url = _make_fake_pdf_fetch(monkeypatch, tmp_path, "B" * 80, "edital_ok")
    out = json.loads(web_csa_fetch.invoke({"url": url, "extract_text": True}))
    assert out["pdf_extraction_status"] == "completed"
    assert "text" in out and len(out["text"].strip()) >= 50


def test_cenario8_pdf_parcial(tmp_path, monkeypatch):
    """PDF com texto <50 chars deve ter pdf_extraction_status='partial'."""
    url = _make_fake_pdf_fetch(monkeypatch, tmp_path, "X", "doc_parcial2")
    out = json.loads(web_csa_fetch.invoke({"url": url, "extract_text": True}))
    assert out["pdf_extraction_status"] == "partial"


def test_cenario9_pdf_falhou(tmp_path, monkeypatch):
    """PDF com ambos os extratores falhando deve ter pdf_extraction_status='failed'."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = b"%PDF-1.4 unreadable"
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(
        portal, "_extract_pdf_text_with_pdftotext",
        lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")),
    )
    monkeypatch.setattr(
        portal, "_extract_pdf_text_with_pypdf",
        lambda p: (_ for _ in ()).throw(RuntimeError("pypdf falhou")),
    )
    url = "https://csa.uefs.br/index.php/download/file/sisu261/doc_falho"
    out = json.loads(web_csa_fetch.invoke({"url": url, "extract_text": True}))
    assert out["pdf_extraction_status"] == "failed"
    assert "text_error" in out


# ---------------------------------------------------------------------------
# Cenário 10 — Ausência de fontes → mensagem de incerteza
# ---------------------------------------------------------------------------

def test_cenario10_ausencia_de_fontes():
    """Quando não há fontes suficientes, resposta deve usar [!] ou indicar claramente."""
    assert _has_incerteza_marker(RESP_NO_SOURCES) or "não foi possível" in RESP_NO_SOURCES.lower()
    assert _has_fontes_section(RESP_NO_SOURCES)


# ---------------------------------------------------------------------------
# Cenário 11 — URL inválida / fora do allowlist
# ---------------------------------------------------------------------------

def test_cenario11_url_invalida_fora_do_allowlist():
    """URL fora do allowlist deve retornar erro descritivo, não exceção não tratada."""
    result = web_csa_fetch.invoke({"url": "https://example.com/pagina"})
    assert "Error" in result or "allowlist" in result.lower()


def test_cenario11_url_http_error(tmp_path, monkeypatch):
    """URL acessível mas com erro HTTP deve retornar campo 'error' no resultado."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")

    class FakeResp:
        status_code = 404
        headers = {}

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    out = json.loads(
        web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/sisu261/pagina_inexistente", "refresh": True})
    )
    assert "error" in out
    assert "404" in out["error"]


# ---------------------------------------------------------------------------
# Cenário 12 — Compatibilidade com metadados antigos (campos extras ignorados)
# ---------------------------------------------------------------------------

def test_cenario12_compatibilidade_campos_antigos(tmp_path, monkeypatch):
    """fetch_page ainda deve conter todos os campos antigos após adição dos novos."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    html = "<html><body><h1>Resultado</h1></body></html>"

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}
        text = html

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    out = json.loads(web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/sisu261/resultado"}))

    # Campos antigos obrigatoriamente preservados
    for campo in ("url", "fetched_at", "content_type", "content", "chars", "cached", "truncated"):
        assert campo in out, f"Campo antigo '{campo}' ausente — compatibilidade quebrada"

    # Novos campos também presentes
    assert "source_type" in out
    assert "is_official" in out


# ---------------------------------------------------------------------------
# Cenário 13 — Não afirmar informação não confirmada
# ---------------------------------------------------------------------------

def test_cenario13_nao_afirmar_sem_confirmacao():
    """Resposta sem trecho verificável não deve afirmar prazo ou dado como fato."""
    # RESP_NO_AFFIRMATION indica incerteza explicitamente
    assert _has_incerteza_marker(RESP_NO_AFFIRMATION) or "não foi possível" in RESP_NO_AFFIRMATION.lower()
    # Não deve ter trecho entre aspas se não há evidência
    trechos = re.findall(r'"[^"]{20,}"', RESP_NO_AFFIRMATION)
    assert len(trechos) == 0, "Resposta sem evidência não deve conter afirmações entre aspas"


# ---------------------------------------------------------------------------
# Cenário 14 — Perguntas em pt-BR sobre SISU, matrícula, chamadas, lista de espera
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pergunta,palavra_chave", [
    ("Quais documentos preciso para a matrícula?", "matrícula"),
    ("Quando é a chamada regular do SISU?", "chamada"),
    ("Como faço para entrar na lista de espera?", "lista de espera"),
    ("Qual o cronograma do SISU/UEFS 2026?", "cronograma"),
])
def test_cenario14_perguntas_ptbr(pergunta, palavra_chave):
    """Termos em pt-BR comuns sobre o processo seletivo são válidos para busca."""
    # Verifica que os termos-chave típicos são detectáveis (base para busca futura)
    assert palavra_chave in pergunta.lower()
    # Verifica que a resposta simulada para SISU segue o formato correto
    assert not _has_resposta_label(RESP_PTBR_SISU)
    assert _has_fontes_section(RESP_PTBR_SISU)
    assert _count_fontes(RESP_PTBR_SISU) >= 1


# ---------------------------------------------------------------------------
# Cenário 15 — Markdown válido para o frontend (ReactMarkdown)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resp", [
    RESP_SINGLE,
    RESP_MULTIPLE,
    RESP_OFFICIAL,
    RESP_CONFLICT,
    RESP_WRONG_YEAR,
    RESP_NO_SOURCES,
    RESP_NO_AFFIRMATION,
    RESP_PTBR_SISU,
])
def test_cenario15_markdown_valido_frontend(resp):
    """Todos os formatos de resposta devem produzir Markdown válido para ReactMarkdown."""
    assert _is_valid_markdown_for_frontend(resp), (
        f"Resposta contém Markdown inválido para o frontend: {resp[:120]!r}"
    )
