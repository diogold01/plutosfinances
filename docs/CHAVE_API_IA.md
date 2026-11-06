# Chave de API de Inteligência Artificial (BYOK)

O recurso de **Lançamento Rápido por IA** opera no modelo BYOK (*Bring Your Own Key*) através do Google AI Studio.

## Regras Permanentes de Segurança
- A chave **nunca** é versionada no Git nem empacotada no executável ou instalador.
- Local de armazenamento local: `dados_usuario/ai_key.local` (ou `dados_usuario/gemini_key.local`).
- Ordem de resolução:
  1. Variáveis de ambiente (`AI_API_KEY` ou `GEMINI_API_KEY`)
  2. Arquivos locais em `dados_usuario/` (`ai_key.local` ou fallback `gemini_key.local`)
  3. Campo na tela de Configurações → Inteligência Artificial
- `dados_usuario/ai_key.local.example` é apenas um modelo vazio de exemplo (versionável).
- O aplicativo nunca expõe a chave completa em logs, interface ou mensagens de erro.

## Como Obter sua Chave Gratuita (Passo a Passo)
1. Acesse o console oficial [Google AI Studio](https://aistudio.google.com/).
2. Faça login com a sua conta Google.
3. No menu lateral, clique em **Get API key** e depois em **Create API key**.
4. Copie a chave gerada (iniciada por `AIza...`).
5. No Plutos, vá em **Configurações → Inteligência Artificial**, cole a chave e clique em **Salvar Credenciais** (ou salve diretamente no arquivo `dados_usuario/ai_key.local`).

