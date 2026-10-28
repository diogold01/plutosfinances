---
description: Regras obrigatórias de versionamento e compilação do Plutos
globs: ["build_executable_and_installer.ps1", "installer/*.iss", "app/version.py", "app/ui/main_window.py"]
---

# Regras Obrigatórias de Versionamento e Compilação do Plutos

Toda vez que for solicitado gerar executável, compilar o projeto ou criar o instalador, o assistente DEVE OBRIGATORIAMENTE seguir estes passos antes de rodar o build:

1. **Fonte da Verdade da Versão:**
   - A versão oficial do aplicativo está definida em `app/version.py` (`__version__ = "X.Y.Z"`).
   - O título oficial da janela (`APP_TITLE`) também é derivado dele.

2. **Verificação Pré-Build:**
   - Conferir se a versão em `app/version.py` reflete a versão pretendida da release (SemVer: Major.Minor.Patch).
   - Se novas funcionalidades foram adicionadas (ex.: v1.2.0 -> v1.3.0) ou correções pontuais (ex.: v1.2.0 -> v1.2.1), confirme ou atualize o número em `app/version.py`.

3. **Sincronização Obrigatória em 3 Arquivos:**
   - `app/version.py`: `__version__ = "X.Y.Z"`
   - `installer/Plutos_Setup.iss`: `#define MyAppVersion "X.Y.Z"`
   - `build_executable_and_installer.ps1`: padrão `$Version = "X.Y.Z"` (o script também lê dinamicamente de `app/version.py`)

4. **Validação de Testes:**
   - NUNCA compilar sem antes rodar a suíte completa de testes: `py -m pytest -v "tests"`.
   - Apenas avançar para a compilação se todos os testes passarem sem falhas (exit code 0).

5. **Execução da Compilação:**
   - Executar o script oficial: `powershell -ExecutionPolicy Bypass -File .\build_executable_and_installer.ps1 -Version "X.Y.Z"`.
   - Confirmar a existência de ambos os binários gerados:
     - `dist/Plutos/Plutos.exe`
     - `dist/Instalador/Plutos_Setup_X.Y.Z.exe`
