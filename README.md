<div align="center">

# 💎 Plutos — Controle Financeiro Pessoal

**Aplicação desktop nativa para gestão financeira pessoal com arquitetura Local-First, interface moderna em Qt 6 e recursos opcionais de IA (Google Gemini).**

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://wiki.qt.io/Qt_for_Python)
[![Database](https://img.shields.io/badge/Database-SQLite3%20Local-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/diogold01/plutosfinances)
[![Tests](https://img.shields.io/badge/Tests-97%20passed%20(100%25)-brightgreen?style=for-the-badge)](tests/)
[![Release](https://img.shields.io/badge/Release-v1.3.6-blue?style=for-the-badge)](https://github.com/diogold01/plutosfinances/releases)

<br/>

<p align="center">
  <img src="referencias/ref-plutos/dashboard.png" alt="Plutos Dashboard (Tema Claro)" width="48%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />
  <img src="referencias/ref-plutos/dashboard_dark.png" alt="Plutos Dashboard (Tema Escuro)" width="48%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);" />
</p>
<p align="center"><i>Interface nativa PySide6 com alternância instantânea entre Tema Claro e Tema Escuro</i></p>

</div>

---

## ⚡ Visão Rápida (30 Segundos)

- **O que é:** Gerenciador financeiro desktop completo para Windows, desenvolvido em Python e PySide6 (Qt 6).
- **Filosofia Local-First:** Seus dados residem 100% no seu computador em um banco relacional **SQLite**. Sem telemetria, sem necessidade de login em servidores remotos e com operação padrão totalmente offline.
- **Inteligência Artificial Prática (BYOK):** Lançamento de despesas e receitas por linguagem natural (ex.: *"almoço 45 reais débito nubank"*) e diagnóstico automatizado de saúde financeira baseado na regra orçamentária **50-30-20**, alimentados pela API Google Gemini com sua própria chave gratuita.
- **Rendimento Automático de CDB:** Projeção diária precisa de rendimento (% do CDI) com base no calendário de dias úteis da B3.
- **Pronto para Produção:** Suíte com **97 testes automatizados** cobrindo regras de negócio, persistência SQLite e integridade visual de interface.

---

## 🔒 Privacidade e Armazenamento de Dados

A arquitetura do Plutos prioriza a total soberania e segurança das suas informações financeiras:

- **Armazenamento 100% Local:** Contas, saldos, transações e orçamentos ficam salvos exclusivamente no arquivo SQLite local (`.sqlite`), sem sincronização compulsória com a nuvem.
- **Backup Local em Tempo de Execução ("Backup Online"):** O termo técnico *"Backup Online"* refere-se estritamente à API nativa do SQLite (`sqlite3.backup`), que permite criar cópias a quente da base de dados local diretamente no disco (`dados_usuario/backups/`) enquanto o app está aberto, com retenção automática das últimas 6 versões. **Nenhum arquivo ou dado é enviado para a internet ou para servidores externos.**
- **Chamadas de Rede Opcionais (Opt-in):**
  1. **Assistente de IA (Google Gemini):** Ao usar o atalho de linguagem natural (`Ctrl+K`) ou solicitar o Diagnóstico de Saúde Financeira, **apenas o texto digitado ou os totais consolidados do mês** e a lista de categorias são enviados à API do Google Gemini. Seu banco de dados completo, histórico pessoal e saldos confidenciais nunca saem da sua máquina.
  2. **Open Finance (Pluggy):** Se ativado opcionalmente pelo usuário com credenciais próprias da Pluggy, a comunicação é feita diretamente entre o computador local e os bancos brasileiros homologados, sempre com tela de prévia e confirmação manual antes da gravação no banco.

---

## 🤖 Inteligência Artificial (Google Gemini — BYOK)

O Plutos integra recursos de Inteligência Artificial desenhados para eliminar o trabalho manual de categorização e fornecer inteligência orçamentária:

### 1. Lançamento por Linguagem Natural (`Ctrl+K` ou `Ctrl+J`)
Permite registrar transações complexas digitando frases simples do dia a dia:

<div align="center">
  <kbd>Ctrl</kbd> + <kbd>K</kbd> &nbsp;ou&nbsp; <kbd>Ctrl</kbd> + <kbd>J</kbd> &nbsp;(ou clique no botão com ícone de brilho no topo)
</div>

<br/>

- **Exemplos aceitos:**
  - *"Almoço executivo 45,90 no débito Nubank"*
  - *"Salário 4800 no Itaú dia 05"*
  - *"pão 12 padaria no dinheiro"*
  - *"Cinema 60 cartão Inter 2x"*
- **Multi-lançamentos:** Digite várias linhas simultaneamente para cadastrar múltiplas despesas de uma só vez.
- **Conferência Prévia:** A IA interpreta valor, data, conta, cartão, forma de pagamento e categoria existente. O usuário confere e valida em tela antes de salvar.

### 2. Diagnóstico de Saúde Financeira & Regra 50-30-20
Na tela de **Relatórios**, o botão **Diagnóstico IA** realiza uma análise financeira mensal completa:
- **Score Financeiro (0 a 100):** Avaliação ponderada entre taxa de poupança, controle de essenciais e solvência.
- **Enquadramento na Regra 50-30-20:**
  - **Gastos Essenciais (Meta até 50%):** Moradia, alimentação básica, saúde e contas fixas.
  - **Estilo de Vida (Meta até 30%):** Lazer, compras, restaurantes e entretenimento.
  - **Poupança & Investimentos (Meta mínima 20%):** Aportes em metas, caixinhas CDB e reservas.
- **Detecção de Anomalias:** Compara gastos da competência atual contra a média dos 2 meses anteriores para identificar estouros e desvios.
- **Recomendações Práticas:** A IA formula sugestões personalizadas e acionáveis para otimizar o orçamento do mês seguinte.

### 🔑 Configuração da Chave de API (BYOK — Bring Your Own Key)
A chave da API do Google Gemini é gratuita e obtida diretamente no [Google AI Studio](https://aistudio.google.com/). Ela **nunca** é gravada no código-fonte. O Plutos resolve a credencial na seguinte ordem:

1. **Interface Gráfica:** Acesse **Configurações → Inteligência Artificial**, informe a chave e clique em *Salvar*.
2. **Arquivo Local:** Crie o arquivo `dados_usuario/gemini_key.local` (ou `ai_key.local`) contendo a chave (já protegido pelo `.gitignore`).
3. **Variável de Ambiente:**
   ```powershell
   $env:GEMINI_API_KEY = "AIzaSy..."
   ```

*Modelo padrão:* `gemini-3.5-flash-lite` (baixo custo computacional, alta velocidade e excelente precisão para JSON estruturado).

---

## ✨ Principais Funcionalidades

### 📊 Visão Geral (Dashboard)
- Painel financeiro consolidado: Saldo Geral, Receitas, Despesas e Saldo Previsto do mês.
- Gráfico interativo em rosca nativo com distribuição percentual por categoria.
- Resumo de faturas de cartões e status de cumprimento de orçamentos.

### 💳 Cartões de Crédito e Faturas
- Múltiplos cartões com limites, bandeiras oficiais e acompanhamento visual do limite utilizado.
- Cálculo automático da data de fechamento, data de vencimento e melhor dia de compra.
- Gestão completa de parcelamentos em faturas futuras e liquidação com 1 clique vinculada à conta corrente.

### 🏦 Contas Bancárias & Caixinhas CDB
- Gestão de contas correntes, contas salário, poupança, carteiras físicas e investimentos.
- Catálogo com mais de 160 logotipos de bancos e fintechs nacionais.
- **Cálculo de Rendimento de CDB (% CDI):** Rendimento diário automático para Caixinhas e CDBs de liquidez diária com base na convenção de 252 dias úteis (B3/Anbima), 100% offline.

### 💸 Transações, Recorrências e Tags
- Lançamento de despesas, receitas e transferências entre contas com status efetivado ou pendente.
- Parcelamentos, compras parceladas e transações recorrentes.
- Sistema de **Tags (#)** para acompanhamento transversal (ex.: `#viagem`, `#reforma`, `#reembolso`).
- Rateio multi-categoria (splits) em um único lançamento.

### 📑 Orçamentos por Categoria
- Metas de gastos mensais por categoria com alertas visuais (*Dentro da Meta*, *Em Alerta* e *Estourado*).

### 🎯 Objetivos e Metas Financeiras
- Planejamento de metas de médio e longo prazo com data-alvo e sugestão matemática de aporte mensal.
- Histórico completo de depósitos e resgates por objetivo.

### 📈 Gráficos Analíticos Nativos (QtCharts)
- Quatro gráficos integrados:
  1. Despesas por Categoria (Rosca).
  2. Receitas por Categoria (Rosca).
  3. Comparativo Mensal de Receitas vs Despesas (Barras).
  4. Curva de Evolução do Saldo Previsto e Resultado Líquido (Linhas).

### 📋 Relatórios & Exportação
- Relatórios analíticos por Categoria, Subcategoria, Fluxo de Caixa Mensal e Tags.
- **Exportação:** Geração de relatórios completos em planilhas Excel (`.xlsx`) e arquivos `.csv`.
- **Importação Inteligente:** Leitor de extratos bancários em CSV com mapeamento flexível de colunas e prevenção de duplicatas via hash SHA-256.

### 🗓️ Calendário Financeiro
- Visão mensal com indicação de vencimentos de faturas, contas a pagar e recebimentos previstos.

### ⚙️ Perfis, Segurança e Utilitários
- Suporte a múltiplos perfis (Pessoal, Profissional) com bloqueio por PIN numérico local (hash SHA-256).
- Simulador de juros compostos para planejamento patrimonial.
- Controle de empréstimos concedidos e tomados.
- Bloco de notas financeiras rápidas.
- Integração opcional com Open Finance brasileiro via API Pluggy.

---

## 🖼️ Galeria de Telas

<div align="center">
  <table>
    <tr>
      <td width="50%">
        <img src="referencias/ref-plutos/transacoes.png" alt="Transações e Lançamentos" />
        <p align="center"><b>Lançamentos e Transações</b></p>
      </td>
      <td width="50%">
        <img src="referencias/ref-plutos/cartoes.png" alt="Cartões de Crédito" />
        <p align="center"><b>Cartões de Crédito e Faturas</b></p>
      </td>
    </tr>
    <tr>
      <td width="50%">
        <img src="referencias/ref-plutos/contas.png" alt="Contas Bancárias" />
        <p align="center"><b>Contas Bancárias e Rendimento CDB</b></p>
      </td>
      <td width="50%">
        <img src="referencias/ref-plutos/orcamentos.png" alt="Orçamentos" />
        <p align="center"><b>Orçamentos Mensais</b></p>
      </td>
    </tr>
    <tr>
      <td width="50%">
        <img src="referencias/ref-plutos/Objetivos.png" alt="Metas e Objetivos" />
        <p align="center"><b>Metas e Objetivos Financeiros</b></p>
      </td>
      <td width="50%">
        <img src="referencias/ref-plutos/Categorias.png" alt="Categorias e Subcategorias" />
        <p align="center"><b>Categorias e Subcategorias</b></p>
      </td>
    </tr>
    <tr>
      <td width="50%">
        <img src="referencias/ref-plutos/relatorios.png" alt="Relatórios Financeiros e Diagnóstico IA" />
        <p align="center"><b>Relatórios e Diagnóstico IA 50-30-20</b></p>
      </td>
      <td width="50%">
        <img src="referencias/ref-plutos/Graficos.png" alt="Gráficos Analíticos" />
        <p align="center"><b>Gráficos Analíticos (QtCharts)</b></p>
      </td>
    </tr>
    <tr>
      <td width="50%">
        <img src="referencias/ref-plutos/calendario.png" alt="Calendário Financeiro" />
        <p align="center"><b>Calendário de Vencimentos</b></p>
      </td>
      <td width="50%">
        <img src="referencias/ref-plutos/configuracoes_ia.png" alt="Configuração de IA" />
        <p align="center"><b>Configurações & Chaveiro de IA (BYOK)</b></p>
      </td>
    </tr>
    <tr>
      <td colspan="2" align="center">
        <img src="referencias/ref-plutos/dashboard_dark.png" alt="Visão Geral no Modo Escuro" width="80%" />
        <p align="center"><b>Visão Geral no Modo Escuro (Dark Theme Nativo)</b></p>
      </td>
    </tr>
  </table>
</div>

---

## 🏗️ Arquitetura do Software

O projeto adota uma arquitetura limpa em camadas com desacoplamento estrito entre interface e regras de negócio:

```text
Minhas Finanças/
├── app/
│   ├── assets/                 # SVGs, logotipos de bancos e fontes
│   ├── config/                 # Configurações do app, chaveiro de IA e temas (QSS)
│   ├── database/               # Conexões SQLite, migrations e backup automático
│   │   └── repositories/       # Padrão Repository (Accounts, Categories, Tags, Profiles)
│   ├── domain/                 # Entidades e modelos puros de negócio
│   │   └── services/           # Regras de negócio (Transactions, Cards, Analytics, AI)
│   ├── io_module/              # Manipulação de CSV/Excel e deduplicação SHA-256
│   ├── services/               # Integrações externas (Google Gemini REST, Pluggy Client)
│   ├── ui/                     # Interface gráfica em PySide6
│   │   ├── components.py       # Widgets customizados (StatCard, PillBadge, EmptyState)
│   │   ├── style_manager.py    # Gerenciador de temas dinâmicos (Light / Dark)
│   │   ├── dialogs/            # Modais (Lançamento IA, Edição de Fatura, etc.)
│   │   └── views/              # Telas (Dashboard, Cartões, Contas, Relatórios, etc.)
│   ├── main.py                 # Ponto de entrada da aplicação
│   └── version.py              # Versão oficial centralizada do sistema (1.3.6)
├── dados_usuario/              # Diretório local para bancos SQLite e backups (ignorado no Git)
├── docs/                       # Documentação técnica e manuais operacionais
├── installer/                  # Script do instalador Windows Inno Setup 6
├── referencias/                # Capturas de tela e especificações visuais
├── scripts/                    # Scripts de QA e auditoria automatizada de interface
├── tests/                      # Suíte com 97 testes automatizados (pytest)
└── build_executable_and_installer.ps1 # Script de automação de build e instalador
```

---

## 🚀 Como Executar em Desenvolvimento

### Pré-requisitos
- **Python 3.10, 3.11 ou 3.12** instalado ([Download oficial](https://www.python.org/))
- **Git** instalado

### Instalação e Execução

```powershell
# 1. Clone o repositório
git clone https://github.com/diogold01/plutosfinances.git
cd plutosfinances

# 2. Crie e ative um ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instale as dependências
pip install PySide6 openpyxl pytest

# 4. Inicie a aplicação
python -m app.main
```

---

## 🧪 Testes Automatizados

A confiabilidade do Plutos é assegurada por **97 testes automatizados** cobrindo regras de negócio financeiras, faturas de cartão, rendimento de CDB, operações de banco de dados, mocks de IA e validação de contratos visuais em modo offscreen:

```powershell
# Executar a suíte completa de testes
py -m pytest -v tests
```

---

## 📦 Compilação do Executável e Instalador Windows

Para gerar o executável standalone (`.exe`) via **PyInstaller** e o instalador de distribuição via **Inno Setup 6**:

```powershell
# Instalar PyInstaller no ambiente
pip install pyinstaller

# Executar script mestre de build
powershell -ExecutionPolicy Bypass -File .\build_executable_and_installer.ps1 -Version "1.3.6"
```

Os artefatos compilados são gerados em:
- `dist/Plutos/Plutos.exe` (Executável standalone com dependências embutidas)
- `dist/Instalador/Plutos_Setup_1.3.6.exe` (Instalador executável para Windows)

---

## 🛡️ Licença

Distribuído sob licença de uso pessoal e educacional. Todos os direitos reservados.

<div align="center">
  <b>Plutos v1.3.6</b>
</div>
