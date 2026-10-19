# Relatório de Viabilidade Técnica: Estratégias para Contorno do Bloqueio de Rede do Portal CSA/UEFS

**Data:** 19 de outubro de 2026  
**Contexto:** Investigação e prototipagem da Issue #13 (referente aos bloqueios reportados nas Issues #4 e #5).  
**Alvo:** Portal oficial da Coordenação de Seleção e Admissão da UEFS (`https://csa.uefs.br`, IP `200.128.81.67`).

---

## 1. Sumário Executivo

A raspagem automatizada periódica do portal `csa.uefs.br` falha consistentemente quando executada a partir de ambientes de computação em nuvem (GitHub Actions hospedado na Azure e Serverless Functions na AWS/Vercel), resultando em `ConnectTimeout` na porta TCP 443 após 15 segundos.

Por meio de diagnósticos empíricos executados com a ferramenta `scripts/probe_csa_egress.py`, confirmamos a coexistência de **duas camadas distintas de filtragem**:
1. **Camada de Borda / Firewall de Rede (L4):** Bloqueio estrito de pacotes TCP SYN originados de blocos de IP de datacenters internacionais de nuvem (Microsoft Azure, AWS, GCP, etc.).
2. **Camada de Aplicação / WAF (L7):** O servidor Apache/PHP rejeita ferramentas utilitárias (`curl/*`) com HTTP 403 Forbidden, mas aceita requisições HTTP originadas de redes brasileiras (inclusive com User-Agent padrão de bibliotecas como `httpx` ou identificador do projeto).

A solução de maior estabilidade a curto/médio prazo consiste na **Execução Agendada via Self-Hosted Runner ou Máquina no Campus**, complementada pelo **Alinhamento Institucional com a CSA/UEFS**.

---

## 2. Diagnóstico Empírico das Camadas de Bloqueio

Os testes controlados executados revelaram o seguinte comportamento comparativo:

| Ambiente de Origem | Resolução DNS | Handshake TCP (443) | Assinatura HTTP / User-Agent | Resultado HTTP | Causa Raiz / Observação |
|---|---|---|---|---|---|
| **Rede Residencial / Brasil** | 200.128.81.67 (16 ms) | OK (7,2 ms) | `curl/8.5.0` | **403 Forbidden** | WAF bloqueia a string do User-Agent do curl. |
| **Rede Residencial / Brasil** | 200.128.81.67 (16 ms) | OK (7,2 ms) | `python-httpx` | **200 OK** (171 ms) | Resposta íntegra do servidor Apache/2.4.16. |
| **Rede Residencial / Brasil** | 200.128.81.67 (16 ms) | OK (7,2 ms) | `chat-csa-bot/1.0` | **200 OK** (155 ms) | Aceito normalmente. |
| **Rede Residencial / Brasil** | 200.128.81.67 (16 ms) | OK (7,2 ms) | `Chrome/124 (Browser)` | **200 OK** (134 ms) | Aceito normalmente. |
| **GitHub Actions (Azure us-north)** | 200.128.81.67 (normal) | **Falha (SYN Drop)** | Qualquer | **ConnectTimeout** | Firewall de borda descarta pacotes de IP de nuvem. |
| **Vercel Functions (AWS iad1)** | 200.128.81.67 (normal) | **Falha (SYN Drop)** | Qualquer | **ConnectTimeout** | Bloqueio de IP de datacenter internacional. |

### Conclusão Técnica
Não se trata de fingerprinting TLS (JA3/JA4) nem de bloqueio exclusivo de User-Agent. Alterar apenas os cabeçalhos HTTP no CI em nuvem **não resolve o problema**, pois a conexão TCP nunca é estabelecida a partir de redes de nuvem internacionais.

---

## 3. Avaliação Detalhada das Alternativas

### Alternativa 1: Headers HTTP e Fingerprinting de Navegador
* **Descrição:** Modificar o script do crawler para injetar cabeçalhos de navegadores reais (`Sec-Fetch-*`, `User-Agent` moderno) ou utilizar navegadores headless como Playwright no CI em nuvem.
* **Viabilidade Técnica:** **Inválida para Cloud CI isolado.** Como a conexão TCP 443 é descartada antes de qualquer troca de dados TLS/HTTP, nenhum ajuste de camada 7 consegue atingir o servidor quando originado do IP do GitHub Actions/Vercel.
* **Custo:** Zero.
* **Complexidade:** Baixa.
* **Estabilidade:** Nula em nuvem.

### Alternativa 2: Proxy Residencial / Egress Local (Tailscale Exit Node)
* **Descrição:** Configurar o workflow do GitHub Actions para rotear seu tráfego de saída através de um proxy com IP brasileiro ou via nó de saída Tailscale instalado em uma máquina local da equipe ou na rede do campus.
* **Viabilidade Técnica:** **Alta.** A requisição sai do CI, trafega pelo túnel criptografado e egressa na internet com IP brasileiro residencial/institucional.
* **Custo:** Gratuito com Tailscale (até 3 usuários/100 dispositivos) ou custo de contratação de proxy HTTP residencial caso terceirizado.
* **Complexidade:** Média (exige manter uma máquina host sempre ligada com conectividade à internet estável e chave de autenticação do Tailscale configurada nos Secrets do GitHub).
* **Estabilidade:** Média (depende da disponibilidade contínua da máquina hospedeira do túnel).

### Alternativa 3: Execução Agendada Local (Self-Hosted Runner ou Cron de Equipe)
* **Descrição:** Configurar um GitHub Actions Self-Hosted Runner em um servidor no campus ou máquina dedicada de membro da equipe (ou cron job local em Linux) que roda `python scripts/scrape_portal.py` a cada 12 horas e submete os novos documentos convertidos diretamente à API (`POST /kb/upload`).
* **Viabilidade Técnica:** **Altíssima.** Não exige manipulação de proxy nem tunelamento de rede no CI. O script roda localmente, consulta o portal (que responde em < 200 ms), processa os arquivos e envia os artefatos via API autenticada com token de escrita.
* **Custo:** Zero (utiliza infraestrutura existente).
* **Complexidade:** Baixa.
* **Estabilidade:** Alta, com isolamento total de falhas externas.

### Alternativa 4: Alinhamento Institucional (Canal Oficial com a CSA/UEFS)
* **Descrição:** Formalizar junto à Gerência de Informática da UEFS e à Coordenação de Seleção e Admissão uma solicitação de liberação de rota para o bloco de IPs ou um feed/API JSON direto para o projeto de extensão.
* **Viabilidade Técnica:** **Ideal a longo prazo.** Elimina qualquer necessidade de raspagem de HTML, reduz o consumo de banda dos servidores da universidade e garante dados estruturados oficiais.
* **Custo:** Zero.
* **Complexidade:** Política/Institucional (tempo de tramitação de processo interno).
* **Estabilidade:** Máxima após homologado.

---

## 4. Matriz Comparativa de Decisão

| Critério | Alt 1: Headers / Fingerprint | Alt 2: Proxy / Tailscale | Alt 3: Self-Hosted Runner / Local | Alt 4: Canal Institucional |
|---|---|---|---|---|
| **Eficácia contra o bloqueio** | ❌ Não resolve (TCP drop) | ✅ Resolve | ✅ Resolve | ✅ Resolve |
| **Complexidade de Implantação** | Mínima | Média | Baixa | Variável (burocrática) |
| **Custo Financeiro** | R$ 0 | R$ 0 – R$ 100/mês | R$ 0 | R$ 0 |
| **Dependência de Infraestrutura** | Nenhuma | Máquina pessoal / VPN | Máquina da equipe / campus | TI central da universidade |
| **Resiliência a Manutenção** | Baixa | Média | Alta | Máxima |
| **Prazo de Viabilização** | Imediato (mas ineficaz) | 1 a 2 dias | Imediato | 2 a 8 semanas |

---

## 5. Recomendações e Plano de Ação

1. **A curto prazo (Imediato):**
   - Adotar a **Alternativa 3 (Execução Local / Self-Hosted Runner)** para desbloquear as sincronizações periódicas. Um cron job diário ou disparador manual com o script `scripts/scrape_portal.py` realiza a raspagem a partir de rede local e publica os documentos na base via `POST /kb/upload`.
2. **Ajuste no Cliente HTTP do Scraper:**
   - Atualizar `scripts/scrape_portal.py` e `src/chat_csa/csa_portal.py` para garantir que o User-Agent utilize cabeçalho formatado de navegador ou identificador explícito do projeto (evitando o bloqueio de L7 WAF que atinge clientes como curl).
3. **A médio/longo prazo (Institucional):**
   - Prosseguir com a tramitação da **Issue #5** junto aos canais oficiais da CSA/UEFS, solicitando fornecimento de feed estruturado de publicações ou whitelist de rede para o projeto.
