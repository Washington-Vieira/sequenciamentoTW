# Sequenciamento de Produção (Streamlit)

Aplicativo Streamlit para sequenciar produção a partir de rotas de processo (GitHub) e planilha de cobertura enviada pelo usuário. Gera arquivos Excel por Centro de Trabalho, priorizando por nível de cobertura e consumo de pico.

## Requisitos
- Python 3.11+ (recomendado 3.11/3.12/3.13)
- Pip

## Instalação
```powershell
cd "C:\Users\20128767\OneDrive - Yazaki\SequenciamentoTW"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Execução
```powershell
streamlit run app.py
```

## Configuração de Credenciais
O app pode usar três fontes, nesta ordem:
1. Inputs na UI (sidebar) – sessão atual
2. Variáveis de ambiente / .env (carregadas com `load_dotenv()`)
3. `st.secrets` (`.streamlit/secrets.toml`)

Campos usados:
- `GITHUB_TOKEN`: token com escopo `repo` (se privado)
- `GITHUB_REPO`: URL do repositório ou `owner/repo`
- `GITHUB_BRANCH`: branch alvo (ex.: `main`)
- `FILE_PATH`: caminho do Excel no repo (ex.: `Data/RotasProcesso.xlsx`)
- `GH_ACCESS_PIN`: PIN para acessar a tela de credenciais

### 1) Configurar pela UI (recomendado para testes)
1. Na sidebar, abra “Acesso às Credenciais”.
2. Informe o PIN e clique “Entrar”. Por padrão, o PIN pode ser definido via `GH_ACCESS_PIN`; se não houver, pode estar desativado/conforme o código.
3. Em “Credenciais GitHub (Sessão)”, informe Token/Repo/Branch/Arquivo e clique “Aplicar credenciais”.

### 2) Variáveis de Ambiente / .env
Crie um arquivo `.env` na raiz:
```dotenv
GITHUB_TOKEN=seu_token
GITHUB_REPO=https://github.com/owner/repo
GITHUB_BRANCH=main
FILE_PATH=Data/RotasProcesso.xlsx
GH_ACCESS_PIN=XXXX
```

PowerShell (sessão atual):
```powershell
$env:GITHUB_TOKEN="seu_token"
$env:GITHUB_REPO="https://github.com/owner/repo"
$env:GITHUB_BRANCH="main"
$env:FILE_PATH="Data/RotasProcesso.xlsx"
$env:GH_ACCESS_PIN="XXXX"
streamlit run app.py
```

### 3) `.streamlit/secrets.toml`
```toml
GITHUB_TOKEN = "seu_token"
GITHUB_REPO = "https://github.com/owner/repo"
GITHUB_BRANCH = "main"
FILE_PATH = "Data/RotasProcesso.xlsx"
GH_ACCESS_PIN = "XXXX"
```

## Fluxo de Funcionamento
1. O app valida credenciais do GitHub e carrega o Excel de rotas do repositório.
2. Você escolhe a “Operação”.
3. Faz upload da “Planilha de Cobertura” (`xlsx`) com colunas: `Material`, `Nível de Cobertura`, `Consumo(Pico)`.
4. O app cruza os dados (merge por `Semiacabado` = `Material`), remove `EXCEDENTE`, ordena por prioridade (`CRÍTICO` > `BAIXO` > `MODERADO`) e `Consumo(Pico)` desc.
5. Exibe tabelas por “Centro de Trabalho” e permite gerar um Excel multi-aba com a sequência.

### Diagrama (Mermaid)
```mermaid
flowchart TD
    A[Início: Abrir App] --> B{Credenciais OK?}
    B -- Não --> C[Sidebar: Acesso às Credenciais]
    C --> D[Informar PIN]
    D --> E[Informar Token/Repo/Branch/Arquivo]
    E --> B
    B -- Sim --> F[Carregar Rotas do GitHub]
    F --> G[Selecionar Operação]
    G --> H[Upload Planilha de Cobertura]
    H --> I{Colunas válidas?}
    I -- Não --> J[Mostrar erro: colunas faltando]
    I -- Sim --> K[Merge Rotas x Cobertura]
    K --> L[Remover EXCEDENTE]
    L --> M[Ordenar por Nível e Consumo(Pico)]
    M --> N[Gerar sequência por Centro de Trabalho]
    N --> O[Exibir tabelas na tela]
    O --> P{Exportar Excel?}
    P -- Sim --> Q[Gerar Excel multi-aba]
    Q --> R[Disponibilizar Download]
    P -- Não --> S[Fim]

    subgraph Atualizar Rotas para GitHub
        T[Escolher arquivo local/upload] --> U[Clicar "Atualizar"]
        U --> V[Enviar via API /contents (commit)]
        V --> W[Rerun do App (URL estável)]
    end
```

## Atualização de Rotas para o GitHub
Na sidebar, em “Atualizar Rotas Processo”:
- O app pode usar o arquivo local `Data/RotasProcesso.xlsx` (preferência) ou um upload.
- Clique “Atualizar” para enviar via API `/contents` do GitHub (gera commit automático).
- Após enviar, o app faz apenas `rerun` (sem alterar parâmetros da URL). O link de acesso permanece estável.

## Tema (Light por padrão)
Configure em `.streamlit/config.toml`:
```toml
[theme]
base = "light"
```

## Estrutura de Pastas (principal)
```
SequenciamentoTW/
  app.py
  requirements.txt
  Data/
    RotasProcesso.xlsx
  Cronograma/
  .streamlit/
    config.toml
    secrets.toml
```

## Solução de Problemas
- Credenciais inválidas/ausentes: verifique `GITHUB_TOKEN`, `GITHUB_REPO`, `FILE_PATH` e se o token possui escopo `repo` para repositórios privados.
- Erro ao ler Excel (raw): o app já faz fallback para a API `/contents`. Veja mensagens na sidebar.
- `st.experimental_rerun` ausente: o código usa `st.rerun()` com fallback silencioso.

## Licença
Interno.

# sequenciamentoTW
