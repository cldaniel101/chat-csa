# Log de Atualizações do Conhecimento

Registro cronológico de todas as alterações na base de conhecimento OKF do Chat CSA.
Cada entrada documenta a data, o tipo de operação e os conceitos afetados.

---

## 2026-08-26

* **Initialization**: Criação da estrutura inicial do bundle OKF.
  - Criados índices para todas as categorias: `editais/`, `cronogramas/`, `procedimentos/`, `modalidades/`, `perguntas-frequentes/`.
  - Ingestão inicial de ~25 conceitos cobrindo edital, cronograma, procedimentos de matrícula, lista de espera, chamada regular, modalidades de concorrência (cotas), resultados e FAQs.
  - Conteúdo gerado com base no funcionamento padrão do SISU e da UEFS; URLs oficiais lógicas apontadas. **Pendente revisão humana da equipe de curadoria.**
  - `.gitignore` ajustado para permitir versionamento completo da pasta `knowledge/`.
