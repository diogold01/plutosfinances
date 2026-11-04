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
