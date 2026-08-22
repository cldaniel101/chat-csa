"""Testes do Guardrail de Validação de Citações no Servidor.

Verifica se o post-processor de app.py bloqueia corretamente respostas
inseguras ou que desrespeitam regras de citação, e se permite respostas válidas.
"""

from chat_csa.server.app import validate_agent_response, _is_sensitive, _extract_read_urls
from langchain_core.messages import AIMessage


def test_is_sensitive():
    assert _is_sensitive("Quando sai o edital?") is True
    assert _is_sensitive("Como funciona a matrícula") is True
    assert _is_sensitive("Qual o prazo?") is True
    assert _is_sensitive("Tem lista de espera?") is True
    assert _is_sensitive("Quem é o reitor?") is False
    assert _is_sensitive("Qual a cor do céu?") is False


def test_extract_read_urls():
    # Cria estrutura de mensagens simulando chamadas de tool
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "web_csa_fetch", "args": {"url": "https://csa.uefs.br/index.php/sisu261/edital"}, "id": "t1"},
                {"name": "web_csa_fetch", "args": {"url": "https://csa.uefs.br/index.php/sisu261/matricula "}, "id": "t2"},
                {"name": "search", "args": {"query": "teste"}, "id": "t3"} # tool ignorada
            ]
        )
    ]
    urls = _extract_read_urls(messages)
    assert len(urls) == 2
    assert "https://csa.uefs.br/index.php/sisu261/edital" in urls
    assert "https://csa.uefs.br/index.php/sisu261/matricula" in urls


def test_guardrail_passa_resposta_segura():
    question = "Quais os documentos para matrícula?"
    resp = "Você precisa de RG. \n\nFontes:\n[1] Edital — https://csa.uefs.br/edital (acesso 2026-08-22)"
    read = {"https://csa.uefs.br/edital"}
    
    assert validate_agent_response(question, resp, read) is None


def test_guardrail_bloqueia_tema_sensivel_sem_fonte():
    question = "Qual o prazo do edital?"
    resp = "O prazo é de 5 dias úteis. Boa sorte!"
    read = {"https://csa.uefs.br/edital"}
    
    err = validate_agent_response(question, resp, read)
    assert err is not None
    assert "bloqueada porque o agente não incluiu a seção de Fontes" in err


def test_guardrail_bloqueia_url_nao_lida():
    question = "Quais os documentos para matrícula?"
    # Citou uma URL que não foi lida
    resp = "Você precisa de RG. \n\nFontes:\n[1] Edital — https://csa.uefs.br/falso (acesso 2026-08-22)"
    read = {"https://csa.uefs.br/verdadeiro"}
    
    err = validate_agent_response(question, resp, read)
    assert err is not None
    assert "não lida ou inexistente" in err
    assert "https://csa.uefs.br/falso" in err


def test_guardrail_ignora_ancoras_na_validacao():
    question = "Quais os documentos para matrícula?"
    # Citou URL com âncora
    resp = "Você precisa de RG. \n\nFontes:\n[1] Edital — https://csa.uefs.br/edital#secao-1 (acesso 2026-08-22)"
    # Mas só leu a base
    read = {"https://csa.uefs.br/edital"}
    
    assert validate_agent_response(question, resp, read) is None
