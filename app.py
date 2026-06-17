import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta


# --- SISTEMA DE LOGIN SIMPLES ---
palavra_passe_correta = st.secrets["senha_app"]
senha_digitada = st.sidebar.text_input("🔐 Palavra-passe de Acesso", type="password")

if senha_digitada != palavra_passe_correta:
    st.warning("Por favor, introduza a palavra-passe no menu lateral esquerdo para aceder ao extrator de contratos.")
    st.stop()


# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Contratos", layout="wide")
st.title("Extrator de Contratos")

# Colunas padrão para blindar a tabela
COLUNAS_PADRAO = ["Cliente", "Parcela", "Data_Prevista", "Mes_Competencia", "Valor_R$", "Regra"]

if 'base_faturamento' not in st.session_state:
    st.session_state.base_faturamento = pd.DataFrame(columns=COLUNAS_PADRAO)

# --- 2. FUNÇÃO DE EXTRAÇÃO DE DADOS ---
def extrair_dados_pdf(arquivo_pdf):
    texto_completo = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + " "
            
    texto_limpo = re.sub(r'\s+', ' ', texto_completo)
            
    match_data = re.search(r'Data da Proposta:\s*(\d{2}/\d{2}/\d{4})', texto_limpo)
    data_base = datetime.strptime(match_data.group(1), '%d/%m/%Y') if match_data else datetime.today()
        
    match_valor = re.search(r'Investimento.*?(\d{1,3}(?:\.\d{3})*,\d{2})', texto_limpo, re.IGNORECASE)
    if match_valor:
        valor_total = float(match_valor.group(1).replace('.', '').replace(',', '.'))
    else:
        match_fallback = re.search(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', texto_limpo)
        valor_total = float(match_fallback.group(1).replace('.', '').replace(',', '.')) if match_fallback else 0.0

    return texto_limpo, data_base, valor_total

def extrair_parcelas_dinamicas(texto_limpo, data_base, valor_total):
    mapa_sprints = {
        r'décim[oa]\s+primeir[oa]|decim[oa]\s+primeir[oa]': 11,
        r'décim[oa]\s+segund[oa]|decim[oa]\s+segund[oa]': 12,
        r'décim[oa]|decim[oa]': 10,
        r'primeir[oa]': 1, r'segund[oa]': 2, r'terceir[oa]': 3,
        r'quart[oa]': 4, r'quint[oa]': 5, r'sext[oa]': 6,
        r'sétim[oa]|setim[oa]': 7, r'oitav[oa]': 8, r'non[oa]': 9
    }

    parcelas = []
    
    match_cond = re.search(r'Condições de pagamento:(.*?)10\.\s*Premissas', texto_limpo, re.IGNORECASE)
    texto_condicoes = match_cond.group(1) if match_cond else texto_limpo
    
    blocos_nf = re.split(r'\d+[º°a-zA-Z]*\s*NF\s*-', texto_condicoes, flags=re.IGNORECASE)
    
    contador_parcela = 1
    for bloco in blocos_nf[1:]:
        bloco_min = bloco.lower()
        
        match_perc = re.search(r'(\d+(?:,\d+)?)%', bloco_min)
        if not match_perc: continue
        
        percentual = float(match_perc.group(1).replace(',', '.')) / 100
        valor_parcela = valor_total * percentual
        
        dias_sprint, prazo_nf = 0, 0
        
        if "antecipado" in bloco_min or "sinal" in bloco_min:
            dias_sprint = 0
            regra_str = "Antecipado"
        else:
            for padrao, numero in mapa_sprints.items():
                if re.search(padrao, bloco_min):
                    dias_sprint = numero * 14
                    break
                    
            match_prazo = re.search(r'(\d+)\s*dias', bloco_min)
            if match_prazo:
                prazo_nf = int(match_prazo.group(1))
                
            regra_str = f"Sprint ({dias_sprint}d) + NF ({prazo_nf}d)" if dias_sprint > 0 else f"NF ({prazo_nf}d)"
            
        data_vencimento = data_base + timedelta(days=(dias_sprint + prazo_nf))
        
        parcelas.append({
            "Cliente": "", 
            "Parcela": f"{contador_parcela}ª",
            "Data_Prevista": data_vencimento.strftime('%d/%m/%Y'),
            "Mes_Competencia": data_vencimento.strftime('%Y-%m'), 
            "Valor_R$": round(valor_parcela, 2),
            "Regra": regra_str
        })
        
        contador_parcela += 1 
        
    return parcelas

# Função auxiliar para formatar a tabela
def formatar_tabela_moeda(df):
    if "Valor_R$" in df.columns:
        return df.style.format({
            "Valor_R$": lambda x: f"R$ {x:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')
        })
    return df

# --- 3. INTERFACE DO UTILIZADOR (PÁGINA ÚNICA) ---
st.header("Upload de Documentos")
ficheiros_enviados = st.file_uploader("Arraste os contratos em PDF aqui", type="pdf", accept_multiple_files=True)

# Colocando os botões lado a lado para um visual mais limpo
col_btn1, col_btn2 = st.columns([1, 5])

with col_btn1:
    if st.button("Processar Contratos"):
        if ficheiros_enviados:
            novas_linhas = []
            for ficheiro in ficheiros_enviados:
                nome_cliente = ficheiro.name.split('.') 
                
                texto_limpo, data_base, valor_total = extrair_dados_pdf(ficheiro)
                parcelas = extrair_parcelas_dinamicas(texto_limpo, data_base, valor_total)
                
                for p in parcelas:
                    p["Cliente"] = nome_cliente
                    novas_linhas.append(p)
                    
            if novas_linhas:
                df_novos = pd.DataFrame(novas_linhas)
                st.session_state.base_faturamento = pd.concat([st.session_state.base_faturamento, df_novos], ignore_index=True)
                st.success(f"{len(ficheiros_enviados)} contrato(s) processado(s) com sucesso!")
        else:
            st.warning("Por favor, carregue pelo menos um ficheiro PDF primeiro.")

with col_btn2:
    if st.button("Limpar Base de Dados"):
        st.session_state.base_faturamento = pd.DataFrame(columns=COLUNAS_PADRAO)
        st.success("Base limpa com sucesso! Memória zerada.")

st.divider() # Uma linha horizontal para separar o upload do resultado

# Mostrar resultados apenas se houver dados
if not st.session_state.base_faturamento.empty:
    df_dash = st.session_state.base_faturamento.copy()
    df_dash['Cliente'] = df_dash['Cliente'].astype(str)
    
    total_previsto = df_dash['Valor_R$'].sum()
    col1, col2 = st.columns(2)
    col1.metric("Total de Contratos Processados", len(df_dash['Cliente'].unique()))
    col2.metric("Faturamento Total Projetado", f"R$ {total_previsto:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.'))
    
    st.subheader("📋 Detalhamento das Parcelas")
    st.dataframe(formatar_tabela_moeda(df_dash), use_container_width=True)
else:
    st.info("Nenhum dado processado. Faça o upload dos contratos acima para visualizar a tabela.")
