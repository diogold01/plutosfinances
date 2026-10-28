# Regras Permanentes de Desenvolvimento do Plutos

Este arquivo define as regras obrigatórias e invioláveis para qualquer agente ou assistente trabalhando neste repositório. Estas regras são carregadas automaticamente pelo sistema em todas as sessões e turnos.

---

## 🚫 1. Proibição Estrita de Compilação Não Autorizada
- **NUNCA executar compilações (`build_executable_and_installer.ps1`, PyInstaller ou Inno Setup) por iniciativa própria.**
- O assistente só pode rodar o processo de compilação quando o usuário **pedir expressamente** ou autorizar de forma inequívoca na mensagem atual.
- Se o usuário pedir apenas para "corrigir código", "analisar" ou "testar", limite-se ao código, aos testes (`pytest`) e à validação em tela. **JAMAIS gere instaladores ou executáveis sem autorização prévia.**

---

## 🔢 2. Controle Rigoroso de Versionamento (SemVer)
- Antes de qualquer compilação autorizada pelo usuário, o assistente **DEVE OBRIGATORIAMENTE**:
  1. Verificar a última versão gerada em `dist/Instalador/` e em `app/version.py`.
  2. Confirmar expressamente com o usuário qual será a versão da release (ex.: se for correção de bug, incremento de patch `1.1.1` -> `1.1.2`; se funcionalidade, `1.2.0`).
  3. Garantir a sincronização exata nos 3 arquivos oficiais:
     - `app/version.py` (`__version__ = "X.Y.Z"`)
     - `installer/Plutos_Setup.iss` (`#define MyAppVersion "X.Y.Z"`)
     - `build_executable_and_installer.ps1` (`$Version = "X.Y.Z"`)
  4. NUNCA sobrescrever instaladores existentes sem permissão ou usar versões fora de sequência.

---

## 🧪 3. Validação de Testes Pré-Build
- Nenhuma compilação pode ser iniciada sem antes rodar a suíte completa de testes:
  ```powershell
  py -m pytest tests
  ```
- Se qualquer teste falhar, a compilação é abortada imediatamente.

---

## 🔒 4. Bloqueio de Publicação no GitHub (Git Push)
- **NUNCA fazer `git push` automaticamente.**
- Commits e push para o repositório remoto só podem ser executados após validação visual do usuário e ordem explícita para enviar.
- Manter arquivos pessoais, bancos SQLite locais (`*.sqlite`, `*.db`), caches e a pasta `dados_usuario/app_settings.json` estritamente fora do controle de versão.
