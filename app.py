import streamlit as st
import pandas as pd
import os
import requests
import io
from dotenv import load_dotenv
from datetime import datetime
import time
import base64

# Carregando variáveis de ambiente
load_dotenv()

# Forçar tema claro diretamente no app (CSS + tentativa de gravar preferência no localStorage)
def force_light_theme():
    js = """
    <script>
    try {
        // salva preferência de tema (tenta várias chaves usadas por diferentes versões)
        localStorage.setItem('streamlit:theme', JSON.stringify({"base":"light"}));
        localStorage.setItem('theme', 'light');
        document.documentElement.setAttribute('data-theme', 'light');
    } catch(e){}
    </script>
    """

    css = """
    <style>
    /* Força cores claras como fallback, independentemente do tema */
    html, body, .stApp, .block-container {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    .stButton>button, .css-1emrehy.edgvbvh3 { background-color: #1f77b4 !important; color: #fff !important; }
    </style>
    """

    try:
        st.markdown(js + css, unsafe_allow_html=True)
    except Exception:
        pass

# Aplica o tema claro logo no início
force_light_theme()

# Configuração da página
st.set_page_config(
    page_title="Sequenciamento de Produção",
    layout="wide"
)

# Configurações do GitHub
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '').strip('"').strip()
GITHUB_REPO = os.getenv('GITHUB_REPO', '').strip('"').strip()
GITHUB_BRANCH = os.getenv('GITHUB_BRANCH', '').strip('"').strip()
GITHUB_FILE = os.getenv('FILE_PATH', '').strip('"').strip() or 'Data/RotasProcesso.xlsx'

# Função para extrair usuário/repositório do GitHub
def clean_github_url(url):
    if not url:
        return None
    url = url.strip('"').strip()
    if url.endswith('.git'):
        url = url[:-4]
    if 'github.com/' in url:
        parts = url.split('github.com/')
        if len(parts) > 1:
            return parts[1]
    return url

# Função para carregar arquivo do GitHub
@st.cache_data(ttl=300)
def load_github_file():
    """Carrega o arquivo Excel do repositório GitHub configurado em GITHUB_REPO/GITHUB_FILE."""
    try:

        repo = clean_github_url(GITHUB_REPO)
        if not repo:
            st.sidebar.error("Repositório GitHub inválido ou não configurado.")
            return None

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else None,
            "Accept": "application/vnd.github.v3+json"
        }
        # Remove None headers
        headers = {k: v for k, v in headers.items() if v}

        # Primeiro tenta a URL raw (funciona bem para repositórios públicos e branches)
        branch_for_raw = GITHUB_BRANCH or 'main'
        raw_url = f"https://raw.githubusercontent.com/{repo}/{branch_for_raw}/{GITHUB_FILE}"

    # informações de conexão suprimidas por solicitação

        # Tenta raw.githubusercontent.com primeiro
        try:
            raw_resp = requests.get(raw_url, headers=headers, timeout=20)
            if raw_resp.status_code == 200:
                try:
                    df = pd.read_excel(io.BytesIO(raw_resp.content))
                    return df
                except Exception as e:
                    st.sidebar.error(f"Falha ao ler Excel a partir do conteúdo raw: {e}")
        except requests.exceptions.RequestException:
            # Falha no raw; seguirá para o endpoint contents
            pass

        # Fallback: usar endpoint /contents para obter base64 (necessita autenticação para repositórios privados)
        api_url = f"https://api.github.com/repos/{repo}/contents/{GITHUB_FILE}"
        if GITHUB_BRANCH:
            api_url += f"?ref={GITHUB_BRANCH}"

        response = requests.get(api_url, headers=headers, timeout=20)
        # Mostra status para diagnóstico
        if response.status_code != 200:
            try:
                body = response.json()
            except Exception:
                body = response.text
            st.sidebar.error(f"Requisição API /contents retornou {response.status_code}: {body}")
            return None

        file_content = response.json()
        if isinstance(file_content, dict) and 'content' in file_content:
            raw_b64 = file_content['content']
        else:
            st.sidebar.error("Resposta da API não contém campo 'content'.")
            return None

        # Decodifica e lê o Excel
        try:
            file_data = base64.b64decode(raw_b64)
            df = pd.read_excel(io.BytesIO(file_data))
        except Exception as e:
            st.sidebar.error(f"Erro ao decodificar/ler o arquivo retornado pela API: {e}")
            return None

        with st.sidebar.expander("✅ Status"):
            st.success("Conexão estabelecida com sucesso!")
            st.write(f"📊 Registros carregados: {len(df)}")
            st.write(f"🕒 Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        return df
    except requests.exceptions.RequestException as e:
        with st.sidebar.expander("❌ Erro de Conexão"):
            st.error(f"Erro na requisição HTTP: {e}")
            if hasattr(e, 'response') and e.response is not None:
                st.write("Status:", e.response.status_code)
                st.write("Detalhes:", e.response.text)
        return None
    except Exception as e:
        with st.sidebar.expander("❌ Erro"):
            st.error(f"Erro inesperado ao carregar arquivo do GitHub: {e}")
        return None


# --- Funções para enviar/atualizar arquivo no GitHub ---
def push_file_to_github(file_bytes: bytes, target_path: str, repo: str, branch: str | None = None, token: str | None = None):
    """Envia ou atualiza um arquivo no repositório GitHub usando o endpoint /contents.
    Retorna (success: bool, message: str).
    """
    if not repo:
        return False, "Repositório não configurado"
    if token is None or token == "":
        return False, "GITHUB_TOKEN ausente - necessário para escrever em repositórios privados ou autenticar gravação."

    api_url = f"https://api.github.com/repos/{repo}/contents/{target_path}"
    if branch:
        api_url += f"?ref={branch}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Verifica se o arquivo já existe para obter o sha
    try:
        get_resp = requests.get(api_url, headers=headers, timeout=20)
    except Exception as e:
        return False, f"Erro na requisição GET ao GitHub: {e}"

    sha = None
    if get_resp.status_code == 200:
        try:
            body = get_resp.json()
            sha = body.get('sha')
        except Exception:
            sha = None
    elif get_resp.status_code not in (404,):
        # se não for 404 (não encontrado), retorna erro com corpo para diagnóstico
        try:
            return False, f"Erro GET ({get_resp.status_code}): {get_resp.json()}"
        except Exception:
            return False, f"Erro GET ({get_resp.status_code}): {get_resp.text}"

    content_b64 = base64.b64encode(file_bytes).decode('utf-8')
    payload = {
        "message": f"Atualiza {target_path} via Streamlit",
        "content": content_b64,
    }
    if branch:
        payload['branch'] = branch
    if sha:
        payload['sha'] = sha

    try:
        put_resp = requests.put(f"https://api.github.com/repos/{repo}/contents/{target_path}", headers=headers, json=payload, timeout=30)
    except Exception as e:
        return False, f"Erro na requisição PUT ao GitHub: {e}"

    if put_resp.status_code in (200, 201):
        try:
            data = put_resp.json()
            return True, f"Arquivo enviado com sucesso. Commit: {data.get('commit', {}).get('sha', '')}"
        except Exception:
            return True, "Arquivo enviado com sucesso (sem detalhes de commit)"
    else:
        try:
            return False, f"Falha ao enviar (HTTP {put_resp.status_code}): {put_resp.json()}"
        except Exception:
            return False, f"Falha ao enviar (HTTP {put_resp.status_code}): {put_resp.text}"


# --- UI: botão na sidebar para importar RotasProcesso.xlsx para o GitHub ---
with st.sidebar.expander('Atualizar Rotas Processo'):
    st.write('Enviar/atualizar o arquivo RotasProcesso.xlsx.')

    # Preferir arquivo local no workspace
    local_path = os.path.join(os.getcwd(), 'Data', 'RotasProcesso.xlsx')
    file_to_send = None
    file_label = ''

    if os.path.exists(local_path):
        st.write(f'Arquivo local encontrado: {local_path}')
        use_local = st.checkbox('Usar arquivo local Data/RotasProcesso.xlsx', value=True)
        if use_local:
            try:
                with open(local_path, 'rb') as f:
                    file_to_send = f.read()
                    file_label = local_path
            except Exception as e:
                st.error(f'Erro ao ler arquivo local: {e}')
    if file_to_send is None:
        uploaded_for_push = st.file_uploader('', type=['xlsx'])
        if uploaded_for_push is not None:
            file_to_send = uploaded_for_push.read()
            file_label = getattr(uploaded_for_push, 'name', 'uploaded')

    if st.button('Atualizar'):
        if not file_to_send:
            st.sidebar.error('Nenhum arquivo disponível para envio. Coloque o arquivo em Data/RotasProcesso.xlsx ou faça upload.')
        else:
            st.sidebar.info('Enviando arquivo...')
            success, msg = push_file_to_github(file_to_send, GITHUB_FILE, clean_github_url(GITHUB_REPO), GITHUB_BRANCH or 'main', GITHUB_TOKEN)
            if success:
                st.sidebar.success(msg)
                # Limpa cache para forçar recarregamento do arquivo via load_github_file
                try:
                    st.cache_data.clear()
                except Exception:
                    pass

                # Observação: o endpoint /contents já cria um commit remoto.
                # Para forçar um rerun compatível com diferentes versões do Streamlit,
                # atualizamos os query params (isso provoca rerun no navegador).
                try:
                    params = st.experimental_get_query_params()
                    params['_updated'] = str(int(time.time()))
                    st.experimental_set_query_params(**params)
                except Exception:
                    # fallback simples
                    st.experimental_set_query_params(_updated=str(int(time.time())))
            else:
                st.sidebar.error(msg)

# Função para verificar atualizações no GitHub
@st.cache_data(ttl=300)  # Cache por 5 minutos
def check_github_update():
    token = os.getenv('GITHUB_TOKEN', '').strip('"')
    repo = clean_github_url(os.getenv('GITHUB_REPO', ''))
    branch = os.getenv('GITHUB_BRANCH', '').strip('"')
    file_path = os.getenv('FILE_PATH', '').strip('"')

    if not all([token, repo, file_path]):
        return None

    url = f"https://api.github.com/repos/{repo}/commits"
    params = {
        "path": file_path,
        "sha": branch if branch else "main",
        "per_page": 1
    }
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        commits = response.json()
        if commits and isinstance(commits, list) and len(commits) > 0:
            return commits[0]['sha']
        return None
    except Exception as e:
        with st.sidebar.expander("⚠️ Aviso de Atualização"):
            st.warning(f"Não foi possível verificar atualizações: {str(e)}")
        return None

# Título da aplicação
st.title("Sequenciamento de Produção")

# Verificando configurações do GitHub
if not all([GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE]):
    st.error("⚠️ Configurações do GitHub ausentes ou incompletas")
    st.stop()

# Carregando dados do GitHub
rotas_df = load_github_file()

if rotas_df is None:
    st.error("❌ Não foi possível carregar os dados do GitHub")
    st.stop()

if rotas_df is not None:
    # Criando o filtro de operações
    operacoes = sorted(rotas_df['Operação'].unique())
    operacao_selecionada = st.selectbox(
        "Selecione a Operação:",
        operacoes
    )

    # Upload do arquivo complementar
    st.subheader("Importar Planilha de Cobertura")
    uploaded_file = st.file_uploader("Escolha o arquivo Excel", type=['xlsx'])

    if uploaded_file is not None:
        try:
            # Carregando dados do arquivo importado
            cobertura_df = pd.read_excel(uploaded_file)

            # Verificando se as colunas necessárias existem
            required_columns = ['Material', 'Nível de Cobertura', 'Consumo(Pico)']
            if all(col in cobertura_df.columns for col in required_columns):
                # Filtrando dados pela operação selecionada
                rotas_filtradas = rotas_df[rotas_df['Operação'] == operacao_selecionada]

                # Realizando o merge dos dataframes
                resultado = pd.merge(
                    rotas_filtradas,
                    cobertura_df,
                    left_on='Semiacabado',
                    right_on='Material',
                    how='inner'
                )

                if not resultado.empty:
                    # Definindo a ordem de prioridade para Nível de Cobertura
                    nivel_ordem = {'CRÍTICO': 0, 'BAIXO': 1, 'MODERADO': 2}
                    resultado['Nível_Ordem'] = resultado['Nível de Cobertura'].map(nivel_ordem)

                    # Dicionário para armazenar os dataframes por centro de trabalho
                    dados_por_centro = {}
                    
                    # Processando dados primeiro
                    centros_trabalho = resultado['Centro de Trabalho'].unique()

                    # Processar todos os dados antes de mostrar os botões
                    for centro in centros_trabalho:
                        # Filtrando dados do centro de trabalho e removendo EXCEDENTE
                        dados_centro = resultado[
                            (resultado['Centro de Trabalho'] == centro) & 
                            (resultado['Nível de Cobertura'] != 'EXCEDENTE')
                        ].copy()

                        if not dados_centro.empty:
                            # Ordenando por Nível de Cobertura e Consumo (Pico)
                            dados_centro = dados_centro.sort_values(
                                by=['Nível_Ordem', 'Consumo(Pico)'],
                                ascending=[True, False]
                            )

                            # Adicionando coluna de sequência
                            dados_centro = dados_centro.reset_index(drop=True)
                            dados_centro['Sequencia'] = dados_centro.index + 1

                            # Armazenando dados formatados para exportação
                            colunas_exibir = ['Sequencia', 'Semiacabado', 'Nível de Cobertura', 'Consumo(Pico)']
                            dados_por_centro[centro] = dados_centro[colunas_exibir].copy()

                    # Área de botões no topo
                    st.markdown("---")  # Linha divisória
                    
                    # Criando duas colunas para os botões
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        export_button = st.button("📥 Gerar Arquivo Excel", use_container_width=True)
                    
                    if export_button:
                        if dados_por_centro:
                            try:
                                # Criar um Excel writer usando pandas
                                output = pd.ExcelWriter(f'Sequenciamento_{operacao_selecionada}.xlsx', engine='openpyxl')
                                
                                # Escrever cada centro de trabalho em uma aba separada
                                for centro, df in dados_por_centro.items():
                                    sheet_name = str(centro)[:31]
                                    df.to_excel(output, sheet_name=sheet_name, index=False)
                                
                                output.close()
                                
                                # Ler o arquivo em bytes para download
                                with open(f'Sequenciamento_{operacao_selecionada}.xlsx', 'rb') as f:
                                    bytes_data = f.read()
                                    
                                # Mostrar botão de download na segunda coluna
                                with col2:
                                    st.download_button(
                                        label="⬇️ Download Excel File",
                                        data=bytes_data,
                                        file_name=f'Sequenciamento_{operacao_selecionada}.xlsx',
                                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                        use_container_width=True
                                    )
                                st.success("✅ Arquivo Excel gerado com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao gerar arquivo Excel: {str(e)}")
                        else:
                            st.warning("Não há dados para exportar. Todos os itens podem estar marcados como EXCEDENTE.")
                    
                    st.markdown("---")  # Linha divisória
                    
                    # Exibindo os dados processados
                    for centro in centros_trabalho:
                        if centro in dados_por_centro:
                            st.subheader(f"Centro de Trabalho: {centro}")
                            # Exibindo resultados
                            st.dataframe(
                                dados_por_centro[centro],
                                hide_index=True
                            )

                    # Mensagem de sucesso após processamento
                    if export_button:
                        st.success("✅ Arquivo Excel gerado com sucesso!")

                else:
                    st.warning("Nenhum item encontrado para a operação selecionada.")

            else:
                missing_cols = [col for col in required_columns if col not in cobertura_df.columns]
                st.error(f"Colunas obrigatórias ausentes no arquivo: {', '.join(missing_cols)}")

        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")
else:
    st.error("Não foi possível carregar o arquivo de rotas. Verifique se o arquivo existe no diretório correto.")
