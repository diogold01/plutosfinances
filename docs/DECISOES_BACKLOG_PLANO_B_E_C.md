# Backlog e Decisões de Arquitetura

Registro de especificações técnicas e planejamento de evolução de módulos do Plutos.

---

## Módulo: Caixinha CDB e Rendimento Diário

- **Localização na UI:** Implementado como tipo especializado de conta bancária com liquidez diária.
- **Cálculo:** Atualização diária com base na convenção de 252 dias úteis bancários (B3/Anbima).
- **Taxa CDI:** Parâmetro fixo configurável em Configurações (ex.: 10,75% ao ano), funcionando 100% offline.

---

## Módulo: Diagnóstico de Saúde Financeira (Google Gemini BYOK)

- **Localização na UI:** Seção na aba de Relatórios com acionamento sob demanda via botão "Diagnóstico IA".
- **Comportamento:** Avaliação da conformidade orçamentária com a Regra 50-30-20, cálculo de score financeiro e detecção de anomalias em relação aos meses anteriores.
- **Integração:** Comunicação direta com a API REST do Google Gemini utilizando chave informada pelo usuário.

---

## Refinamento de Interface: Tela de Tags (TagsView)

- **Contraste na coluna Cor Visual:**
  - Substituir a renderização atual do código hexadecimal em pill translúcida por uma amostra de cor sólida (*swatch* circular) com contraste adaptativo (WCAG AA) em ambos os temas.
- **Preview Dinâmico:**
  - Adicionar pré-visualização ao vivo do chip da tag no modal de criação e edição conforme o usuário digita o nome e seleciona a cor.
