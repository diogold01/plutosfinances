# 📌 Registro de Decisões Estratégicas: Planos B e C (Backlog Futuro)

Este documento registra as decisões homologadas pelo usuário no dia 31/10/2026 para os **Planos B e C**, que serão desenvolvidos após a conclusão do **Plano A (Open Finance Pluggy)**.

---

## 📦 Plano B: Caixinha CDB & Rendimento Diário
* **Localização e Comportamento na UI:**
  - Será implementada como um **tipo especial de Conta Bancária** (com flag/tipo de investimento e liquidez diária).
  - O saldo é atualizado diariamente com base nos juros acumulados desde o aporte.
* **Origem da Taxa CDI:**
  - **Valor Fixo Customizável nas Configurações** (ex.: o usuário define 10,75% ao ano nas configurações do app), funcionando 100% offline e sem depender de APIs externas.
* **Modelo & Esforço Futuro:**
  - Backend/Matemática: **Gemini 3.8 Argon** (*Medium*)
  - UI/Card: **Sonnet 3.5** (*Low/Medium*)

---

## 🤖 Plano C: Assistente de Inteligência Financeira (Gemini BYOK)
* **Localização na UI:**
  - Ficará centralizado na **aba de 'Relatórios'**, como uma seção avançada de **'Análise Preditiva e Dicas de Saúde Financeira'**.
* **Comportamento:**
  - Gera diagnósticos sob demanda, avaliando categorias com maior gasto, comprometimento de renda e metas financeiras.
* **Modelo & Esforço Futuro:**
  - Prompt & Schemas: **Gemini 3.8 Argon** (*Medium*)
  - Telas e Threads Assíncronas: **Sonnet 3.5** (*Medium*)

---

## 🎨 Backlog Futuro de Refinamento de UI: Tela de Tags (`TagsView`)

* **Data do Registro:** 07/11/2026
* **Observações Visuais (Light e Dark Mode):**
  1. **Contraste na coluna "Cor Visual":**
     - Atualmente a coluna exibe uma pill com o texto do código hexadecimal (`#E5603D`) estilizado com transparência (`{color}22`).
     - Em **Dark Mode** e especialmente quando a linha da tabela está **selecionada** (fundo escuro/terracota), o contraste entre o texto do hex e o fundo fica reduzido, dificultando a leitura rápida.
     - **Solução Planejada:** Exibir uma amostra de cor visual (swatch/círculo sólido com borda sutil) acompanhada de texto com contraste adaptativo (ou apenas a amostra visual com tooltip), garantindo contraste WCAG AA tanto no tema claro quanto no escuro.
  2. **Preview no Modal "Nova Tag":**
     - Incluir pré-visualização dinâmica do chip da tag em tempo real conforme o usuário digita o nome e seleciona a cor no combobox.
