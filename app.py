import streamlit as st
import pandas as pd
import os
import requests
from dotenv import load_dotenv
from datetime import datetime
import json

# Carregando variáveis de ambiente
load_dotenv()

# Configuração da página
st.set_page_config(
    page_title="Sequenciamento de Produção",
    layout="wide"
)

# Função para buscar arquivo do GitHub
def get_file_from_github():
    # Configurações do GitHub
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_REPO')
    branch = os.getenv('GITHUB_BRANCH')
    file_path = os.getenv('FILE_PATH')

    # URL da API do GitHub
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw"
    }

    try:
        # Fazendo a requisição para o GitHub
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Salvando o arquivo temporariamente
        temp_file = "temp_rotas.xlsx"
        with open(temp_file, "wb") as f:
            f.write(response.content)

        # Carregando o arquivo com pandas
        df = pd.read_excel(temp_file)

        # Removendo arquivo temporário
        os.remove(temp_file)

        return df, None

    except Exception as e:
        return None, str(e)

# Função para verificar atualizações no GitHub
@st.cache_data(ttl=300)  # Cache por 5 minutos
def check_github_update():
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_REPO')
    branch = os.getenv('GITHUB_BRANCH')
    file_path = os.getenv('FILE_PATH')

    url = f"https://api.github.com/repos/{repo}/commits?path={file_path}&sha={branch}"
    headers = {"Authorization": f"token {token}"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        commits = response.json()
        if commits:
            return commits[0]['sha']
        return None
    except Exception:
        return None

# Título da aplicação
st.title("Sequenciamento de Produção")

# Verificando atualizações e carregando dados
if 'last_commit' not in st.session_state:
    st.session_state.last_commit = None

current_commit = check_github_update()

# Se houver nova atualização, recarrega os dados
if current_commit != st.session_state.last_commit:
    st.session_state.last_commit = current_commit
    rotas_df, error = get_file_from_github()
    
    if error:
        st.error(f"Erro ao carregar arquivo do GitHub: {error}")
        st.stop()
else:
    # Se não houver atualização, usa o cache
    @st.cache_data(ttl=300)
    def load_rotas():
        df, error = get_file_from_github()
        if error:
            st.error(f"Erro ao carregar arquivo do GitHub: {error}")
            return None
        return df

    rotas_df = load_rotas()

# Mostrar informação sobre última atualização
if rotas_df is not None and current_commit:
    st.sidebar.info("📅 Última atualização do arquivo: " + 
                   datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

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
