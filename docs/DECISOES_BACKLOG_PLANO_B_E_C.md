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
