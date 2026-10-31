# Chave de API do Gemini (BYOK)

O recurso de **Lançamento Rápido por IA** usa a sua própria chave do Google AI Studio (BYOK).

## Regra permanente
- A chave **nunca** é versionada no Git nem empacotada no instalador.
- Local de armazenamento: `dados_usuario/gemini_key.local` (listado no `.gitignore`).
- Ordem de leitura:
  1. Variável de ambiente `GEMINI_API_KEY`
  2. Arquivo `dados_usuario/gemini_key.local`
  3. Campo na tela de Configurações → Inteligência Artificial
- `dados_usuario/gemini_key.local.example` é apenas um modelo vazio (versionável).
- Quem clonar o projeto começa sem chave e cola a própria.
- A chave não pode aparecer em logs nem em mensagens de erro.

## Status
- Etapa 1 (backend `AIService`): concluída.
- Leitura do arquivo `.local` e campo na tela: **pendentes (Etapa 2)**.
- Instruções de uso passo a passo serão entregues ao fim de todas as etapas.
