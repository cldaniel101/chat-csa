"""Testes de qualidade de resposta do servidor (guia > bloqueio).

Verifica que o servidor higieniza o formato sem bloquear respostas:
o agente é guiado pelo prompt (guia de citações), nunca punido depois.
"""

from langchain_core.messages import AIMessage, ToolMessage

from chat_csa.server.app import (
    _RESPONSE_GUIDE_BLOCK,
    _format_agent_response,
    _has_source_lookup,
    _is_conversational,
)


def test_is_conversational():
    assert _is_conversational("Opa") is True
    assert _is_conversational("Olá!") is True
    assert _is_conversational("Obrigado") is True
    assert _is_conversational("Como funciona a lista de espera?") is False


def test_format_agent_response_remove_rotulo_resposta():
    response = "Resposta:\nA matrícula é feita pelo SIDOC. [1]\n\nFontes:\n[1] Edital — https://csa.uefs.br/edital"

    formatted = _format_agent_response(response, source_was_consulted=True)

    assert formatted.startswith("A matrícula")
    assert "Resposta:" not in formatted
    assert "Fontes:" in formatted


def test_format_agent_response_mantem_fontes_sem_consulta():
    # Sem fonte consultada o formatter não apaga mais a seção Fontes:
    # guia > bloqueio — a resposta do agente passa como veio.
    response = "**Resposta:** Opa! Como posso ajudar? [1]\n\nFontes:\n[1] Portal CSA — https://csa.uefs.br/"

    formatted = _format_agent_response(response, source_was_consulted=False)

    assert formatted.startswith("Opa!")
    assert "Resposta:" not in formatted
    assert "Fontes:" in formatted


def test_format_agent_response_remove_nota_de_divergencia_orfã():
    response = "A resposta.\n\nEm caso de divergência, prevalece o edital oficial."

    formatted = _format_agent_response(response, source_was_consulted=False)

    assert formatted == "A resposta."


def test_response_guide_block_ensina_template_de_citacao():
    assert "Fontes:" in _RESPONSE_GUIDE_BLOCK
    assert "cache FAQ-" in _RESPONSE_GUIDE_BLOCK
    assert "web_csa_fetch" in _RESPONSE_GUIDE_BLOCK
    assert "Não invente URLs" in _RESPONSE_GUIDE_BLOCK


def test_has_source_lookup_exige_fonte_aberta():
    search_only = [
        AIMessage(
            content="",
            tool_calls=[{"name": "web_csa_search", "args": {"query": "SiSU"}, "id": "t1"}],
        )
    ]
    fetched = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "web_csa_fetch", "args": {"url": "https://csa.uefs.br/"}, "id": "t2"}
            ],
        )
    ]

    assert _has_source_lookup(search_only) is False
    assert _has_source_lookup(fetched) is True


def test_has_source_lookup_ignora_fetch_com_erro():
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_csa_fetch",
                    "args": {"url": "https://csa.uefs.br/index.php/sisu/inicial"},
                    "id": "t1",
                }
            ],
        ),
        ToolMessage(
            content=(
                '{"url":"https://csa.uefs.br/index.php/sisu261/inicial",'
                '"resolved_from_url":"https://csa.uefs.br/index.php/sisu/inicial",'
                '"error":"Página não encontrada no portal CSA/UEFS"}'
            ),
            tool_call_id="t1",
        ),
    ]

    assert _has_source_lookup(messages) is False