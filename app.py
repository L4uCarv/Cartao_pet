import base64
import calendar
import io
import math
import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fpdf import FPDF
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
from postgrest.exceptions import APIError
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Sistema Integrado de Saúde Pet",
    page_icon="🐾",
    layout="wide",
)

# ==============================================================================
# 1. LEITURA DE SEGREDOS & CLIENTE SUPABASE
# ==============================================================================
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
    EMAIL_REMETENTE = st.secrets["email"]["remetente"]
    EMAIL_SENHA_APP = st.secrets["email"]["senha_app"]
except KeyError as e:
    st.error(f"⚠️ Chave ausente em secrets.toml: {e}")
    st.stop()

@st.cache_resource
def get_supabase_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase_client()
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

INFO_VACINAS = {
    "Polivalente V10": {
        "cat": "Vacina Polivalente",
        "doencas": ["Cinomose", "Parvovirose", "Coronavirose", "Hepatite Infecciosa", "Adenovirose Tipo 2", "Parainfluenza", "Leptospirose"],
        "intervalo_filhote": 21,
        "intervalo_adulto": 365,
    },
    "Polivalente V8": {
        "cat": "Vacina Polivalente",
        "doencas": ["Cinomose", "Parvovirose", "Coronavirose", "Hepatite Infecciosa", "Adenovirose Tipo 2", "Parainfluenza"],
        "intervalo_filhote": 21,
        "intervalo_adulto": 365,
    },
    "Vacina Antirrábica": {
        "cat": "Vacina Essencial",
        "doencas": ["Raiva Canina"],
        "intervalo_filhote": 365,
        "intervalo_adulto": 365,
    },
    "Vacina contra Tosse dos Canis (Gripe)": {
        "cat": "Vacina Complementar",
        "doencas": ["Bordetella bronchiseptica", "Parainfluenza"],
        "intervalo_filhote": 21,
        "intervalo_adulto": 365,
    },
    "Vacina contra Giardíase": {
        "cat": "Vacina Complementar",
        "doencas": ["Giardia duodenalis"],
        "intervalo_filhote": 21,
        "intervalo_adulto": 365,
    },
}

# ==============================================================================
# 2. ESTILIZAÇÃO CSS
# ==============================================================================
st.markdown(
    """
    <style>
    .stApp {
        background-color: #FAF8F5;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    div.stButton > button:first-child {
        background-color: #4E877C !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #3B6B62 !important;
        color: #FFFFFF !important;
    }
    div.stButton > button[kind="primary"] {
        background-color: #D47A5B !important;
        color: #FFFFFF !important;
        border: none !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #C06649 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF;
        border: 1px solid #E2DBD0 !important;
        border-radius: 12px !important;
    }
    h1, h2, h3, h4 {
        color: #2F4F48 !important;
        font-weight: 700 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. FUNÇÕES AUXILIARES & CÁLCULOS
# ==============================================================================
def garantir_autenticacao_ativa():
    if st.session_state.get("refresh_token"):
        try:
            res = supabase.auth.refresh_session(st.session_state.refresh_token)
            if res and res.session:
                st.session_state.access_token = res.session.access_token
                st.session_state.refresh_token = res.session.refresh_token
                supabase.postgrest.auth(res.session.access_token)
                return True
        except Exception:
            pass
    if st.session_state.get("access_token"):
        supabase.postgrest.auth(st.session_state.access_token)
        return True
    return False

def obter_bytes_pdf(pdf_obj):
    out = pdf_obj.output(dest='S')
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode('latin1')

def obter_meses_idade(data_nascimento_str):
    try:
        data_nasc = datetime.strptime(str(data_nascimento_str), "%Y-%m-%d").date()
        hoje = date.today()
        return (hoje.year - data_nasc.year) * 12 + (hoje.month - data_nasc.month)
    except Exception:
        return 0

def calcular_idade(data_nascimento_str):
    try:
        data_nasc = datetime.strptime(str(data_nascimento_str), "%Y-%m-%d").date()
        hoje = date.today()
        anos = hoje.year - data_nasc.year
        meses = hoje.month - data_nasc.month
        dias = hoje.day - data_nasc.day
        if dias < 0:
            meses -= 1
        if meses < 0:
            anos -= 1
            meses += 12
        total_meses = (anos * 12) + meses
        if total_meses < 1:
            return f"{(hoje - data_nasc).days} dia(s)"
        elif anos < 1:
            return f"{meses} mês(es)"
        else:
            return f"{anos} ano(s)" if meses == 0 else f"{anos} ano(s) e {meses} m."
    except Exception:
        return "Idade Não Informada"

def calcular_idade_humana_equivalente(meses_idade, peso=0.0):
    if meses_idade <= 1:
        return "1 ano"
    elif meses_idade <= 3:
        return "3 a 4 anos"
    elif meses_idade <= 6:
        return "8 a 10 anos (Infância)"
    elif meses_idade <= 12:
        return "14 a 16 anos (Adolescência)"
    elif meses_idade <= 24:
        return "22 a 24 anos (Jovem Adulto)"
    else:
        anos_cao = meses_idade / 12.0
        if peso > 45:
            mult = 7.5
        elif peso > 25:
            mult = 6.0
        elif peso > 10:
            mult = 5.0
        else:
            mult = 4.0
        idade_h = 24 + int((anos_cao - 2) * mult)
        return f"~{idade_h} anos humanos"

def calcular_previsao_primeiro_cio(data_nascimento_str):
    try:
        return datetime.strptime(str(data_nascimento_str), "%Y-%m-%d").date() + timedelta(days=180)
    except Exception:
        return date.today()

def calcular_data_parto(data_cruzamento):
    return data_cruzamento + timedelta(days=63)

def sugerir_proxima_vacina(nome_vacina, data_ap, meses_idade):
    info = INFO_VACINAS.get(nome_vacina)
    if not info:
        return data_ap + timedelta(days=21)
    if meses_idade < 4 and "Antirrábica" not in nome_vacina:
        return data_ap + timedelta(days=info["intervalo_filhote"])
    return data_ap + timedelta(days=info["intervalo_adulto"])

def sugerir_proxima_desparasitacao(tipo_tratamento, data_ap, meses_idade):
    if "Externa" in tipo_tratamento:
        return data_ap + timedelta(days=30)
    elif meses_idade < 6:
        return data_ap + timedelta(days=15)
    else:
        return data_ap + timedelta(days=90)

def carregar_imagem_base64(uploaded_file):
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        base64_str = base64.b64encode(bytes_data).decode()
        return f"data:{uploaded_file.type};base64,{base64_str}"
    return None

# ==============================================================================
# 4. FUNÇÕES DE CACHE EM SESSÃO
# ==============================================================================
def recarregar_dados_sessao(user_id, tipo_perfil):
    garantir_autenticacao_ativa()
    try:
        if tipo_perfil == "Clinica":
            st.session_state.cache_pets = supabase.table("pets").select("*").execute().data or []
        else:
            st.session_state.cache_pets = supabase.table("pets").select("*").eq("tutor_id", user_id).execute().data or []
    except APIError as e:
        if "JWT expired" in str(e):
            st.session_state.clear()
            st.warning("A sua sessão expirou por inatividade. Por favor, inicie sessão novamente.")
            st.rerun()

def obter_dados_pet(pet_id):
    garantir_autenticacao_ativa()
    try:
        if f"vacinas_{pet_id}" not in st.session_state:
            st.session_state[f"vacinas_{pet_id}"] = supabase.table("vacinas").select("*").eq("pet_id", pet_id).order("data_aplicacao", desc=True).execute().data or []
        if f"desps_{pet_id}" not in st.session_state:
            st.session_state[f"desps_{pet_id}"] = supabase.table("desparasitacoes").select("*").eq("pet_id", pet_id).order("data_aplicacao", desc=True).execute().data or []
        return st.session_state[f"vacinas_{pet_id}"], st.session_state[f"desps_{pet_id}"]
    except APIError as e:
        if "JWT expired" in str(e):
            st.session_state.clear()
            st.warning("Sessão expirada. Por favor, entre novamente.")
            st.rerun()
        return [], []

def invalidar_cache_pet(pet_id):
    st.session_state.pop(f"vacinas_{pet_id}", None)
    st.session_state.pop(f"desps_{pet_id}", None)
    st.session_state.pop(f"reps_{pet_id}", None)
    st.session_state.pop(f"ninhadas_{pet_id}", None)

# ==============================================================================
# 5. GERADORES DE PDF COM ALINHAMENTO EXATO E ESPAÇAMENTO ORTOGRÁFICO
# ==============================================================================
class CartaoControlePDF(FPDF):
    def __init__(self):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.set_auto_page_break(auto=False)

def desenhar_calendario(pdf, x, y, w, h, titulo, data_alvo, cor_cabecalho):
    meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    ano = data_alvo.year
    mes = data_alvo.month
    dia_marcado = data_alvo.day
    
    pdf.set_fill_color(255, 252, 248)
    pdf.rect(x, y, w, h, "F")
    
    pdf.set_xy(x, y - 5)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(47, 79, 72)
    pdf.cell(w, 4, titulo.upper(), 0, 0, "C")
    
    pdf.set_xy(x, y)
    pdf.set_fill_color(*cor_cabecalho)
    pdf.rect(x, y, w, 6, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(w, 6, f"{meses_pt[mes]} / {ano}", 0, 0, "C")
    
    dias_semana = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]
    pdf.set_xy(x, y + 6)
    pdf.set_font("Helvetica", "B", 6)
    pdf.set_text_color(110, 100, 90)
    col_w = w / 7.0
    for d in dias_semana:
        pdf.cell(col_w, 4, d, 0, 0, "C")
        
    cal = calendar.monthcalendar(ano, mes)
    curr_y = y + 10
    pdf.set_font("Helvetica", "", 6.5)
    
    for row in cal:
        pdf.set_xy(x, curr_y)
        for d in row:
            if d == 0:
                pdf.cell(col_w, 4, "", 0, 0, "C")
            elif d == dia_marcado:
                center_x = pdf.get_x() + (col_w / 2.0)
                center_y = curr_y + 2
                pdf.set_fill_color(212, 122, 91)
                pdf.circle(center_x, center_y, 2.2, "F")
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 6.5)
                pdf.cell(col_w, 4, str(d), 0, 0, "C")
                pdf.set_font("Helvetica", "", 6.5)
            else:
                pdf.set_text_color(60, 60, 60)
                pdf.cell(col_w, 4, str(d), 0, 0, "C")
        curr_y += 4

def desenhar_cabecalho_base(pdf, tutor_info, pet, titulo_doc="Cartão de Controlo"):
    pdf.set_fill_color(250, 248, 245)
    pdf.rect(0, 0, 297, 210, "F")

    x_verde, y_verde, w_verde, h_verde = 12, 12, 185, 186
    pdf.set_fill_color(78, 135, 124)
    pdf.rect(x_verde, y_verde, w_verde, h_verde, "F")

    pdf.set_xy(x_verde + 8, y_verde + 5)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(w_verde - 16, 7, titulo_doc, 0, 1, "C")

    y_dados = y_verde + 14
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(x_verde + 8, y_dados)
    pdf.cell(85, 5, "DADOS DO TUTOR / RESPONSÁVEL", 0, 0, "L")
    pdf.set_xy(x_verde + 96, y_dados)
    pdf.cell(85, 5, "DADOS DO ANIMAL", 0, 1, "L")

    pdf.set_font("Helvetica", "", 8.5)
    t_nome = tutor_info.get("nome", "Laurentina de Carvalho")
    t_email = tutor_info.get("email", "Não Informado")
    t_end = tutor_info.get("endereco", "Luanda, Angola")
    t_tel = tutor_info.get("telefone", "936342306 / 934071334")
    t_status = tutor_info.get("tipo_perfil", "Tutor")

    p_nome = pet["nome"]
    p_raca = pet.get("raca", "Sem Raça Definida (SRD)")
    p_idade = calcular_idade(pet["data_nascimento"])
    p_sexo = pet.get("sexo", "Macho")
    p_pelo = pet.get("pelo", "Curto")

    linhas_tutor = [f"Nome: {t_nome}", f"E-mail: {t_email}", f"Endereço: {t_end}", f"Telefone: {t_tel}", f"Perfil: {t_status}"]
    linhas_pet = [f"Nome: {p_nome}", f"Raça: {p_raca}", f"Idade: {p_idade}", f"Sexo: {p_sexo}", f"Pêlo: {p_pelo}"]

    for idx, (lt, lp) in enumerate(zip(linhas_tutor, linhas_pet)):
        y_curr = y_dados + 5 + (idx * 4.6)
        pdf.set_xy(x_verde + 8, y_curr)
        pdf.cell(85, 4.6, lt, 0, 0, "L")
        pdf.set_xy(x_verde + 96, y_curr)
        pdf.cell(85, 4.6, lp, 0, 0, "L")

    return x_verde, y_dados + 30, w_verde

def desenhar_painel_lateral_com_todas_observacoes(pdf, vacinas, desparasitacoes, pet, filhotes=None, ninhadas=None):
    x_dir = 208
    w_dir = 76
    dt_alvo_v = date.today() + timedelta(days=21)
    if vacinas and vacinas[0].get("proxima_dose"):
        try:
            dt_alvo_v = datetime.strptime(vacinas[0]["proxima_dose"], "%Y-%m-%d").date()
        except Exception:
            pass
    desenhar_calendario(pdf, x_dir, 20, w_dir, 44, "Próxima Vacina", dt_alvo_v, (212, 122, 91))

    dt_alvo_d = date.today() + timedelta(days=30)
    if desparasitacoes and desparasitacoes[0].get("proxima_dose"):
        try:
            dt_alvo_d = datetime.strptime(desparasitacoes[0]["proxima_dose"], "%Y-%m-%d").date()
        except Exception:
            pass
    desenhar_calendario(pdf, x_dir, 74, w_dir, 44, "Próxima Desparasitação", dt_alvo_d, (78, 135, 124))

    y_notes = 128
    pdf.set_fill_color(255, 252, 248)
    pdf.rect(x_dir, y_notes, w_dir, 70, "F")
    pdf.set_xy(x_dir + 4, y_notes + 4)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(47, 79, 72)
    pdf.cell(w_dir - 8, 4, "ANOTAÇÕES & CARIMBO VETERINÁRIO", 0, 1, "L")
    
    linhas_obs = []
    if pet.get("esta_doente"):
        linhas_obs.append(f"Diag: {pet.get('doenca_nome', 'N/I')[:22]}")
        linhas_obs.append(f"Local: {pet.get('local_tratamento', 'N/I')[:22]}")
        if pet.get("medicamentos_em_uso"):
            linhas_obs.append(f"Meds: {pet.get('medicamentos_em_uso')[:24]}")
        if pet.get("evolucao_melhorias"):
            linhas_obs.append(f"Evol: {pet.get('evolucao_melhorias')[:24]}")
    else:
        linhas_obs.append(f"Saúde: Animal saudável. Em dia.")
        linhas_obs.append(f"Ref. Peso Atual: {pet.get('peso_atual', 0.0)} kg")

    if ninhadas and len(ninhadas) > 0 and ninhadas[0].get("observacoes"):
        obs_nin = str(ninhadas[0]["observacoes"])
        if obs_nin.strip():
            linhas_obs.append(f"Obs Parto: {obs_nin[:22]}")

    if filhotes:
        for f in filhotes[:3]:
            dono_str = f.get('novo_dono_nome') or 'Utilizador Sistema'
            linhas_obs.append(f"Filhote ({f['sexo'][0]}): {dono_str[:18]}")

    y_line_start = y_notes + 14
    num_lines = 9
    line_spacing = 5.6

    pdf.set_draw_color(210, 200, 190)
    for idx in range(num_lines):
        curr_line_y = y_line_start + (idx * line_spacing)
        pdf.line(x_dir + 4, curr_line_y, x_dir + w_dir - 4, curr_line_y)
        
        if idx < len(linhas_obs):
            txt = linhas_obs[idx]
            pdf.set_font("Helvetica", "", 6.5)
            pdf.set_text_color(50, 50, 50)
            pdf.set_xy(x_dir + 4, curr_line_y - 4.5)
            pdf.cell(w_dir - 8, 4.2, txt, 0, 0, "L")

def desenhar_imagem_rodape_verde(pdf, x_verde, y_verde, w_verde, h_verde, y_quadro, h_quadro):
    possiveis_caminhos = [
        "Contorno de caes e gatos_2.jpg",
        "Contorno de caes e gatos.jpg", 
        "Contorno de caes e gatos.png",
        "logo_pet.png",
        "logo.png"
    ]
    caminho_imagem = None
    for p in possiveis_caminhos:
        if os.path.exists(p):
            caminho_imagem = p
            break
            
    if caminho_imagem:
        try:
            temp_proc = "temp_contorno_espacado.png"
            img = Image.open(caminho_imagem).convert("L")
            cor_quadro_corpo = (64, 114, 104)
            white_fg = (255, 255, 255)
            
            new_img = Image.new("RGB", img.size, cor_quadro_corpo)
            pixels = img.load()
            new_pixels = new_img.load()
            
            for x in range(img.width):
                for y in range(img.height):
                    val = pixels[x, y]
                    if val < 210:
                        factor = (210 - val) / 210.0
                        r = int(cor_quadro_corpo[0] + (white_fg[0] - cor_quadro_corpo[0]) * factor)
                        g = int(cor_quadro_corpo[1] + (white_fg[1] - cor_quadro_corpo[1]) * factor)
                        b = int(cor_quadro_corpo[2] + (white_fg[2] - cor_quadro_corpo[2]) * factor)
                        new_pixels[x, y] = (r, g, b)
                    else:
                        new_pixels[x, y] = cor_quadro_corpo
                        
            new_img.save(temp_proc, format="PNG")
            
            img_w = 90
            img_h = 72
            img_x = x_verde + 8 + (w_verde - 16) - img_w
            img_y = y_quadro + h_quadro - img_h
            
            pdf.image(temp_proc, x=img_x, y=img_y, w=img_w, h=img_h)
        except Exception:
            pass

def gerar_pdf_cartao_final(tutor_info, pet, vacinas, desparasitacoes):
    pdf = CartaoControlePDF()
    pdf.add_page()

    x_verde, y_quadro, w_verde = desenhar_cabecalho_base(pdf, tutor_info, pet, "Cartão de Controlo")
    desenhar_painel_lateral_com_todas_observacoes(pdf, vacinas, desparasitacoes, pet)

    h_quadro = 144
    pdf.set_fill_color(64, 114, 104)
    pdf.rect(x_verde + 8, y_quadro, w_verde - 16, h_quadro, "F")

    desenhar_imagem_rodape_verde(pdf, 12, 12, 185, 186, y_quadro, h_quadro)

    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(x_verde + 12, y_quadro + 5)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(w_verde - 24, 6, f"Resumo de Saúde Atual (Pet: {pet['nome']})", 0, 1, "L")

    pdf.set_xy(x_verde + 12, y_quadro + 16)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(26, 5.0, "Peso Atual:", 0, 0, "L")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(60, 5.0, f"{pet.get('peso_atual', 0.0)} kg", 0, 1, "L")

    pdf.set_xy(x_verde + 12, y_quadro + 28)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(w_verde - 24, 5.0, "Última Vacina Aplicada:", 0, 1, "L")
    pdf.set_font("Helvetica", "", 8)
    if vacinas:
        v = vacinas[0]
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, f"- {v['nome_vacina']} (Aplicada: {v['data_aplicacao']} | Prevista: {v['proxima_dose']})", 0, 1, "L")
        if v.get("doencas_protegidas"):
            pdf.set_x(x_verde + 16)
            pdf.cell(w_verde - 28, 5.0, f"  Protege contra: {v['doencas_protegidas'][:65]}", 0, 1, "L")
    else:
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, "- Nenhuma vacina registrada até o momento.", 0, 1, "L")

    pdf.set_xy(x_verde + 12, y_quadro + 56)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(w_verde - 24, 5.0, "Último Desparasitante Aplicado:", 0, 1, "L")
    pdf.set_font("Helvetica", "", 8)
    if desparasitacoes:
        d = desparasitacoes[0]
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, f"- {d['nome_produto']} ({d['tipo']} | Aplicada: {d['data_aplicacao']} | Prevista: {d['proxima_dose']})", 0, 1, "L")
    else:
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, "- Nenhum desparasitante registrado.", 0, 1, "L")

    pdf.set_xy(x_verde + 12, y_quadro + 82)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(w_verde - 24, 5.0, "Anti-pulga e Controlo Anti-carraças:", 0, 1, "L")
    pdf.set_font("Helvetica", "", 8)
    desps_ext = [d for d in desparasitacoes if "Externa" in d.get("tipo", "") or "Combinado" in d.get("tipo", "")]
    if desps_ext:
        de = desps_ext[0]
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, f"- {de['nome_produto']} ({de.get('observacoes', 'Dosagem padrão')} | Prevista: {de['proxima_dose']})", 0, 1, "L")
    else:
        pdf.set_x(x_verde + 16)
        pdf.cell(w_verde - 28, 5.0, "- Sem registo de tratamento externo ativo.", 0, 1, "L")

    pdf.set_xy(x_verde + 12, y_quadro + 112)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(220, 235, 230)
    pdf.cell(w_verde - 70, 4.5, "* Observações de saúde encontram-se descritas no quadro lateral de Anotações.", 0, 1, "L")

    return obter_bytes_pdf(pdf)

def gerar_pdf_historico_completo(tutor_info, pet, vacinas, desparasitacoes, reproducoes=None, ninhadas=None, filhotes=None):
    pdf = CartaoControlePDF()
    pdf.add_page()

    x_verde, y_quadro, w_verde = desenhar_cabecalho_base(pdf, tutor_info, pet, "Histórico Clínico Completo")
    desenhar_painel_lateral_com_todas_observacoes(pdf, vacinas, desparasitacoes, pet, filhotes, ninhadas)

    h_quadro = 144
    pdf.set_fill_color(64, 114, 104)
    pdf.rect(x_verde + 8, y_quadro, w_verde - 16, h_quadro, "F")

    desenhar_imagem_rodape_verde(pdf, 12, 12, 185, 186, y_quadro, h_quadro)

    pdf.set_text_color(255, 255, 255)
    curr_y = y_quadro + 5.0
    
    # Alinhamento exato aos limites do quadro do corpo (largura interna total = 169 mm)
    t_x = x_verde + 8
    w_t = w_verde - 16

    # 1. TABELA HISTÓRICO CLÍNICO (Oculta se não houver clínica)
    clinica_nome = pet.get("local_tratamento")
    if clinica_nome and clinica_nome.strip():
        pdf.set_xy(t_x + 4, curr_y)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(w_t - 8, 4, "1. HISTÓRICO CLÍNICO (CLÍNICA RESPONSÁVEL)", 0, 1, "L")
        curr_y += 5.0

        pdf.set_xy(t_x + 4, curr_y)
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_fill_color(50, 95, 86)
        pdf.cell(70, 5.5, "  Local / Clínica", 1, 0, "L", True)
        pdf.cell(55, 5.5, "  Diagnóstico / Acompanhamento", 1, 0, "L", True)
        pdf.cell(36, 5.5, "  Médico / Status", 1, 1, "L", True)
        curr_y += 5.5

        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_fill_color(58, 104, 95)
        pdf.set_xy(t_x + 4, curr_y)
        pdf.cell(70, 5.5, f"  {clinica_nome[:35]}", 1, 0, "L", True)
        pdf.cell(55, 5.5, f"  {(pet.get('doenca_nome') or 'Rotina / Em dia')[:28]}", 1, 0, "L", True)
        pdf.cell(36, 5.5, "  Equipa Veterinária", 1, 1, "L", True)
        curr_y += 9.0

    # 2. TABELA HISTÓRICO DE VACINAÇÃO (Largura total 161 mm)
    pdf.set_xy(t_x + 4, curr_y)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(w_t - 8, 4, "2. HISTÓRICO DE VACINAÇÃO", 0, 1, "L")
    curr_y += 5.0

    pdf.set_xy(t_x + 4, curr_y)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_fill_color(50, 95, 86)
    pdf.cell(24, 5.5, "  Data", 1, 0, "L", True)
    pdf.cell(55, 5.5, "  Vacina & Doenças Protegidas", 1, 0, "L", True)
    pdf.cell(35, 5.5, "  Nome Comercial", 1, 0, "L", True)
    pdf.cell(27, 5.5, "  Vinheta (L/Val)", 1, 0, "L", True)
    pdf.cell(20, 5.5, "  Aplicador", 1, 1, "L", True)
    curr_y += 5.5

    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_fill_color(58, 104, 95)
    if vacinas:
        for v in vacinas[:3]:
            pdf.set_xy(t_x + 4, curr_y)
            pdf.cell(24, 5.5, f"  {str(v.get('data_aplicacao', '-'))}", 1, 0, "L", True)
            pdf.cell(55, 5.5, f"  {v.get('nome_vacina','-')} ({v.get('doencas_protegidas','-')[:18]})", 1, 0, "L", True)
            pdf.cell(35, 5.5, f"  {str(v.get('nome_vacina', '-'))[:16]}", 1, 0, "L", True)
            pdf.cell(27, 5.5, "  L: Padrão", 1, 0, "L", True)
            pdf.cell(20, 5.5, "  Vet.", 1, 1, "L", True)
            curr_y += 5.5
    else:
        pdf.set_xy(t_x + 4, curr_y)
        pdf.cell(w_t - 8, 5.5, "  Nenhuma vacina registada até o momento.", 1, 1, "L", True)
        curr_y += 5.5

    curr_y += 5.0

    # 3. TABELA HISTÓRICO DE DESPARASITAÇÃO INTERNA E EXTERNA
    pdf.set_xy(t_x + 4, curr_y)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(w_t - 8, 4, "3. HISTÓRICO DE DESPARASITAÇÃO INTERNA E EXTERNA", 0, 1, "L")
    curr_y += 5.0

    pdf.set_xy(t_x + 4, curr_y)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_fill_color(50, 95, 86)
    pdf.cell(24, 5.5, "  Data", 1, 0, "L", True)
    pdf.cell(35, 5.5, "  Tipo", 1, 0, "L", True)
    pdf.cell(76, 5.5, "  Medicamento & Dosagem / Peso", 1, 0, "L", True)
    pdf.cell(26, 5.5, "  Aplicador", 1, 1, "L", True)
    curr_y += 5.5

    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_fill_color(58, 104, 95)
    if desparasitacoes:
        for d in desparasitacoes[:3]:
            pdf.set_xy(t_x + 4, curr_y)
            pdf.cell(24, 5.5, f"  {str(d.get('data_aplicacao', '-'))}", 1, 0, "L", True)
            pdf.cell(35, 5.5, f"  {str(d.get('tipo', '-'))[:18]}", 1, 0, "L", True)
            pdf.cell(76, 5.5, f"  {d.get('nome_produto','-')} ({d.get('observacoes','Dosagem padrão')[:18]}) - {d.get('peso_kg',0)}kg", 1, 0, "L", True)
            pdf.cell(26, 5.5, "  Vet.", 1, 1, "L", True)
            curr_y += 5.5
    else:
        pdf.set_xy(t_x + 4, curr_y)
        pdf.cell(w_t - 8, 5.5, "  Nenhum controlo parasitário registado.", 1, 1, "L", True)
        curr_y += 5.5

    curr_y += 5.0

    # 4. CONTROLO REPRODUTIVO E NINHADAS (Se for Fêmea)
    if pet.get("sexo") == "Fêmea":
        pdf.set_xy(t_x + 4, curr_y)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(w_t - 8, 4, "4. CONTROLO REPRODUTIVO, GESTAÇÃO E NINHADAS", 0, 1, "L")
        curr_y += 5.0

        pdf.set_xy(t_x + 4, curr_y)
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_fill_color(50, 95, 86)
        pdf.cell(24, 5.5, "  Último Cio", 1, 0, "L", True)
        pdf.cell(24, 5.5, "  Cruzamento", 1, 0, "L", True)
        pdf.cell(35, 5.5, "  Macho Padreador", 1, 0, "L", True)
        pdf.cell(26, 5.5, "  Data Parto", 1, 0, "L", True)
        pdf.cell(14, 5.5, "  Tot.", 1, 0, "L", True)
        pdf.cell(14, 5.5, "  Mach.", 1, 0, "L", True)
        pdf.cell(14, 5.5, "  Fêm.", 1, 0, "L", True)
        pdf.cell(10, 5.5, "  Ób.", 1, 1, "L", True)
        curr_y += 5.5

        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_fill_color(58, 104, 95)
        pdf.set_xy(t_x + 4, curr_y)

        if reproducoes:
            r = reproducoes[0]
            cio_str = str(r.get("data_cio", "-"))
            cruz_str = str(r.get("data_cruzamento", "-")) if r.get("cruzou") else "Não cruzou"
            macho_str = str(r.get("macho_nome", "Não informado"))[:17]
            
            parto_str = "-"
            tot_str = "-"
            m_str = "-"
            f_str = "-"
            o_str = "-"

            if ninhadas:
                n = ninhadas[0]
                parto_str = str(n.get("data_parto", "-"))
                tot_str = str(n.get("total_nascidos", 0))
                m_str = str(n.get("total_machos", 0))
                f_str = str(n.get("total_femeas", 0))
                o_str = str(n.get("total_obitos", 0))
            elif r.get("ficou_gravida"):
                parto_str = f"Prev:{r.get('data_provavel_parto','-')}"
                tot_str = "Gest."

            pdf.cell(24, 5.5, f"  {cio_str}", 1, 0, "L", True)
            pdf.cell(24, 5.5, f"  {cruz_str}", 1, 0, "L", True)
            pdf.cell(35, 5.5, f"  {macho_str}", 1, 0, "L", True)
            pdf.cell(26, 5.5, f"  {parto_str}", 1, 0, "L", True)
            pdf.cell(14, 5.5, f"  {tot_str}", 1, 0, "L", True)
            pdf.cell(14, 5.5, f"  {m_str}", 1, 0, "L", True)
            pdf.cell(14, 5.5, f"  {f_str}", 1, 0, "L", True)
            pdf.cell(10, 5.5, f"  {o_str}", 1, 1, "L", True)
        else:
            prev_cio = calcular_previsao_primeiro_cio(pet["data_nascimento"]).strftime('%d/%m/%Y')
            pdf.cell(w_t - 8, 5.5, f"  Sem registo de cruzamentos. Previsão para o 1.º Cio: ~{prev_cio}", 1, 1, "L", True)

    pdf.set_xy(t_x + 4, h_quadro + y_quadro - 6)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(220, 235, 230)
    pdf.cell(w_t - 8, 4, "* Observações clínicas e destino de filhotes descritos no quadro lateral de Anotações.", 0, 1, "L")

    return obter_bytes_pdf(pdf)

# ==============================================================================
# 6. DIALOGS (JANELAS FLUTUANTES)
# ==============================================================================
@st.dialog("✏️ Editar Perfil do Pet")
def modal_editar_pet(pet_obj):
    st.markdown(f"Alterar dados cadastrais de **{pet_obj['nome']}**:")
    
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        e_nome = st.text_input("Nome Pet:", value=pet_obj["nome"], key="ed_pet_nome")
        e_raca = st.text_input("Raça:", value=pet_obj.get("raca", "SRD"), key="ed_pet_raca")
        dt_val = datetime.strptime(str(pet_obj["data_nascimento"]), "%Y-%m-%d").date() if pet_obj.get("data_nascimento") else date.today()
        e_nasc = st.date_input("Data de Nascimento:", value=dt_val, key="ed_pet_nasc")
    with col_e2:
        lista_sexos = ["Fêmea", "Macho"]
        idx_sexo = lista_sexos.index(pet_obj.get("sexo", "Fêmea")) if pet_obj.get("sexo") in lista_sexos else 0
        e_sexo = st.selectbox("Sexo:", lista_sexos, index=idx_sexo, key="ed_pet_sexo")
        
        lista_pelos = ["Curto", "Longo", "Ondulado", "Liso"]
        idx_pelo = lista_pelos.index(pet_obj.get("pelo", "Curto")) if pet_obj.get("pelo") in lista_pelos else 0
        e_pelo = st.selectbox("Tipo de Pêlo:", lista_pelos, index=idx_pelo, key="ed_pet_pelo")
        e_peso = st.number_input("Peso Atual (kg):", value=float(pet_obj.get("peso_atual", 0.0)), step=0.1, min_value=0.0, key="ed_pet_peso")

    e_foto = st.file_uploader("Alterar Foto (opcional):", type=["png", "jpg", "jpeg"], key="ed_pet_foto")

    if st.button("Salvar Alterações", type="primary", use_container_width=True, key="btn_save_ed_pet"):
        garantir_autenticacao_ativa()
        dados_up = {
            "nome": e_nome,
            "raca": e_raca,
            "data_nascimento": str(e_nasc),
            "sexo": e_sexo,
            "pelo": e_pelo,
            "peso_atual": e_peso,
        }
        if e_foto:
            dados_up["foto_url"] = carregar_imagem_base64(e_foto)

        supabase.table("pets").update(dados_up).eq("id", pet_obj["id"]).execute()
        st.session_state.pop("cache_pets", None)
        invalidar_cache_pet(pet_obj["id"])
        st.success("Perfil do pet atualizado com sucesso!")
        st.rerun()

@st.dialog("⚠️ Confirmar Exclusão")
def modal_eliminar_pet(pet_obj):
    st.error(f"Tem a certeza de que deseja eliminar o perfil de **{pet_obj['nome']}**?")
    st.caption("Esta ação apagará permanentemente todos os registros de vacinas, desparasitações e histórico reprodutivo deste animal.")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        if st.button("Sim, Eliminar", type="primary", use_container_width=True, key="btn_conf_del"):
            garantir_autenticacao_ativa()
            supabase.table("pets").delete().eq("id", pet_obj["id"]).execute()
            st.session_state.pop("cache_pets", None)
            invalidar_cache_pet(pet_obj["id"])
            if st.session_state.get("pet_selecionado_id") == pet_obj["id"]:
                st.session_state.pet_selecionado_id = None
            st.success("Perfil eliminado com sucesso!")
            st.rerun()
    with col_d2:
        if st.button("Cancelar", use_container_width=True, key="btn_canc_del"):
            st.rerun()

@st.dialog("📝 Lançar Nova Vacina")
def modal_editar_vacina(pet_obj):
    st.markdown(f"Registar nova aplicação para **{pet_obj['nome']}**:")
    v_escolha = st.selectbox("Escolha a vacina:", ["-- Selecione uma vacina --"] + list(INFO_VACINAS.keys()), index=0, key="m_v_sel_vazia")
    
    chk_selecionados = []
    if v_escolha != "-- Selecione uma vacina --":
        st.write("**Doenças Prevenidas:**")
        for d in INFO_VACINAS[v_escolha]["doencas"]:
            if st.checkbox(d, value=True, key=f"m_chk_v_{d}"):
                chk_selecionados.append(d)
                
    c1, c2 = st.columns(2)
    with c1:
        d_ap = st.date_input("Data da Aplicação", date.today(), key="m_v_ap_vazia")
    with c2:
        meses = obter_meses_idade(pet_obj["data_nascimento"])
        d_sug = sugerir_proxima_vacina(v_escolha, d_ap, meses) if v_escolha != "-- Selecione uma vacina --" else date.today() + timedelta(days=21)
        d_px = st.date_input("Data Prevista para a Próxima", d_sug, key="m_v_px_vazia")
        
    if st.button("Gravar", type="primary", use_container_width=True, key="btn_modal_save_v"):
        if v_escolha != "-- Selecione uma vacina --":
            garantir_autenticacao_ativa()
            supabase.table("vacinas").insert({
                "pet_id": pet_obj["id"],
                "tipo_registro": "Vacina",
                "nome_vacina": v_escolha,
                "dose_descricao": INFO_VACINAS[v_escolha]["cat"],
                "doencas_protegidas": ", ".join(chk_selecionados),
                "data_aplicacao": str(d_ap),
                "proxima_dose": str(d_px),
                "peso_kg": pet_obj.get("peso_atual", 0.0),
            }).execute()
            invalidar_cache_pet(pet_obj["id"])
            st.success("Vacina gravada com sucesso!")
            st.rerun()
        else:
            st.warning("Por favor, selecione a vacina antes de gravar.")

@st.dialog("📝 Lançar Desparasitante / Controlo Anti-Carraças")
def modal_editar_desparasitante(pet_obj):
    st.markdown(f"Registar novo controlo para **{pet_obj['nome']}**:")
    c1, c2 = st.columns(2)
    with c1:
        t_trat = st.selectbox("Tipo de Tratamento:", ["-- Selecione o tipo --", "Interna (Vermes)", "Externa (Carraças/Pulgas)", "Combinado"], index=0, key="m_d_tipo_vazio")
        n_prod = st.text_input("Produto:", value="", placeholder="Ex: Simparica, Drontal...", key="m_d_prod_vazio")
    with c2:
        f_farm = st.selectbox(
            "Forma Farmacêutica:", 
            ["-- Selecione a apresentação --", "Comprimido", "Líquido / Suspensão", "Pipeta (Spot-on)", "Pasta oral", "Coleira", "Injetável", "Outro"], 
            index=0, 
            key="m_d_farm_vazia"
        )
        p_reg = st.number_input("Peso Atual do Pet (kg):", value=0.0, step=0.1, min_value=0.0, key="m_d_peso_vazio")

    c_d1, c_d2 = st.columns(2)
    with c_d1:
        dt_ap = st.date_input("Data de Aplicação", date.today(), key="m_d_ap_vazia")
    with c_d2:
        meses = obter_meses_idade(pet_obj["data_nascimento"])
        tipo_real = t_trat if t_trat != "-- Selecione o tipo --" else "Interna"
        dt_sug = sugerir_proxima_desparasitacao(tipo_real, dt_ap, meses)
        dt_px = st.date_input("Próxima Dose", dt_sug, key="m_d_px_vazia")

    if st.button("Gravar", type="primary", use_container_width=True, key="btn_modal_save_d"):
        if t_trat != "-- Selecione o tipo --" and n_prod.strip() != "":
            garantir_autenticacao_ativa()
            supabase.table("desparasitacoes").insert({
                "pet_id": pet_obj["id"],
                "tipo": t_trat,
                "nome_produto": n_prod,
                "peso_kg": p_reg if p_reg > 0 else pet_obj.get("peso_atual", 0.0),
                "data_aplicacao": str(dt_ap),
                "proxima_dose": str(dt_px),
                "observacoes": f"Forma: {f_farm}",
            }).execute()

            if p_reg > 0:
                supabase.table("pets").update({"peso_atual": p_reg}).eq("id", pet_obj["id"]).execute()
                
            invalidar_cache_pet(pet_obj["id"])
            st.session_state.pop("cache_pets", None)
            st.success("Registo gravado com sucesso!")
            st.rerun()
        else:
            st.warning("Por favor, preencha o tipo de tratamento e o nome do produto.")

@st.dialog("✏️ Editar Ninhada e Filhotes")
def modal_editar_ninhada(ninhada_obj, pet_obj):
    st.markdown(f"Alterar informações da ninhada da fêmea **{pet_obj['nome']}**:")
    
    c_dt, c_tot = st.columns(2)
    with c_dt:
        dt_nasc_edit = st.date_input("Data Real do Parto:", value=datetime.strptime(str(ninhada_obj["data_parto"]), "%Y-%m-%d").date(), key="ed_nin_dt")
    with c_tot:
        total_edit = st.number_input("Total de Filhotes Nascidos:", min_value=0, value=int(ninhada_obj.get("total_nascidos", 0)), key="ed_nin_tot")

    c1, c2, c3 = st.columns(3)
    with c1:
        m_edit = st.number_input("Machos:", min_value=0, value=int(ninhada_obj.get("total_machos", 0)), key="ed_nin_m")
    with c2:
        f_edit = st.number_input("Fêmeas:", min_value=0, value=int(ninhada_obj.get("total_femeas", 0)), key="ed_nin_f")
    with c3:
        o_edit = st.number_input("Óbitos:", min_value=0, value=int(ninhada_obj.get("total_obitos", 0)), key="ed_nin_o")

    obs_edit = st.text_input("Observações do Parto:", value=str(ninhada_obj.get("observacoes", "")), key="ed_nin_obs")

    if (m_edit + f_edit + o_edit) != total_edit and total_edit > 0:
        st.caption(f"ℹ️ Nota: A soma dos detalhes ({m_edit + f_edit + o_edit}) difere do total manual informado ({total_edit}).")

    if st.button("Salvar Alterações da Ninhada", type="primary", use_container_width=True, key="btn_save_ed_nin"):
        garantir_autenticacao_ativa()
        supabase.table("ninhadas").update({
            "data_parto": str(dt_nasc_edit),
            "total_nascidos": int(total_edit),
            "total_machos": int(m_edit),
            "total_femeas": int(f_edit),
            "total_obitos": int(o_edit),
            "observacoes": obs_edit,
        }).eq("id", ninhada_obj["id"]).execute()

        invalidar_cache_pet(pet_obj["id"])
        st.success("Ninhada atualizada com sucesso!")
        st.rerun()

# ==============================================================================
# 7. SESSÃO & AUTENTICAÇÃO
# ==============================================================================
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "perfil" not in st.session_state:
    st.session_state.perfil = None
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None
if "pet_selecionado_id" not in st.session_state:
    st.session_state.pet_selecionado_id = None
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Pág. Inicial"

garantir_autenticacao_ativa()

if not st.session_state.usuario:
    st.title("🐾 Plataforma de Gestão e Saúde Pet")
    menu_auth = st.sidebar.radio("Acesso ao Sistema", ["Login", "Criar Conta"])

    if menu_auth == "Login":
        st.subheader("🔑 Iniciar Sessão")
        email_login = st.text_input("E-mail")
        senha_login = st.text_input("Palavra-passe", type="password")

        if st.button("Entrar", type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                if res.user and res.session:
                    st.session_state.usuario = res.user
                    st.session_state.access_token = res.session.access_token
                    st.session_state.refresh_token = res.session.refresh_token
                    supabase.postgrest.auth(res.session.access_token)

                    perfil_res = supabase.table("tutores").select("*").eq("id", res.user.id).execute()
                    if perfil_res.data:
                        st.session_state.perfil = perfil_res.data[0]
                    st.session_state.pop("cache_pets", None)
                    st.success("Login efetuado com sucesso!")
                    st.rerun()
            except Exception:
                st.error("Credenciais inválidas. Verifique os dados inseridos.")

    elif menu_auth == "Criar Conta":
        st.subheader("📝 Registo de Novo Utilizador")
        tipo_conta = st.radio("Selecione o perfil:", ["Tutor", "Criador", "Clínica Veterinária"])

        if tipo_conta == "Tutor":
            nome = st.text_input("Nome Completo do Tutor")
            email = st.text_input("E-mail")
            senha = st.text_input("Palavra-passe", type="password")
            nome_canil, nif = None, None
        elif tipo_conta == "Criador":
            nome_canil = st.text_input("Nome do Canil")
            nome = st.text_input("Nome do Responsável")
            email = st.text_input("E-mail")
            senha = st.text_input("Palavra-passe", type="password")
            nif = None
        else:
            nif = st.text_input("NIF da Clínica")
            nome = st.text_input("Nome da Clínica Veterinária")
            email = st.text_input("E-mail Institucional")
            senha = st.text_input("Palavra-passe", type="password")
            nome_canil = None

        if st.button("Concluir Registo", type="primary"):
            if not nome or not email or not senha:
                st.warning("Preencha todos os campos obrigatórios.")
            elif tipo_conta == "Criador" and not nome_canil:
                st.warning("O Nome do Canil é obrigatório.")
            elif tipo_conta == "Clínica Veterinária" and not nif:
                st.warning("O NIF é obrigatório para clínicas.")
            else:
                try:
                    res = supabase.auth.sign_up({"email": email, "password": senha})
                    if res.user:
                        if res.session:
                            st.session_state.access_token = res.session.access_token
                            st.session_state.refresh_token = res.session.refresh_token
                            supabase.postgrest.auth(res.session.access_token)

                        perfil_dict = {
                            "id": res.user.id,
                            "nome": nome,
                            "email": email,
                            "tipo_perfil": "Clinica" if tipo_conta == "Clínica Veterinária" else tipo_conta,
                        }
                        if tipo_conta == "Criador":
                            perfil_dict["nome_canil"] = nome_canil
                        elif tipo_conta == "Clínica Veterinária":
                            perfil_dict["nif"] = nif

                        supabase.table("tutores").insert(perfil_dict).execute()
                        st.session_state.usuario = res.user
                        st.session_state.perfil = perfil_dict
                        st.session_state.pop("cache_pets", None)
                        st.success("Conta criada com sucesso!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

# ==============================================================================
# 8. PAINEL PRINCIPAL
# ==============================================================================
else:
    perfil = st.session_state.perfil or {}
    tipo_perfil = perfil.get("tipo_perfil", "Tutor")
    user_id = st.session_state.usuario.id

    if "cache_pets" not in st.session_state or st.session_state.cache_pets is None:
        recarregar_dados_sessao(user_id, tipo_perfil)
    meus_pets = st.session_state.cache_pets

    if not st.session_state.pet_selecionado_id and meus_pets:
        st.session_state.pet_selecionado_id = meus_pets[0]["id"]

    # CABEÇALHO GLOBAL DE NAVEGAÇÃO
    col_nav1, col_nav2, col_nav3, col_nav4, col_exit = st.columns([1, 1.2, 1, 1.3, 0.6])

    with col_nav1:
        if st.button("🏠 Pág. inicial", use_container_width=True, type="primary" if st.session_state.pagina_atual == "Pág. Inicial" else "secondary"):
            st.session_state.pagina_atual = "Pág. Inicial"
            st.rerun()
    with col_nav2:
        if st.button("📝 Consultar e Editar", use_container_width=True, type="primary" if st.session_state.pagina_atual == "Consultar e Editar" else "secondary"):
            st.session_state.pagina_atual = "Consultar e Editar"
            st.rerun()
    with col_nav3:
        if st.button("🩺 Pág. Efermidades", use_container_width=True, type="primary" if st.session_state.pagina_atual == "Pág. Efermidades" else "secondary"):
            st.session_state.pagina_atual = "Pág. Efermidades"
            st.rerun()
    with col_nav4:
        if st.button("🍼 Reprodução & Ninhadas", use_container_width=True, type="primary" if st.session_state.pagina_atual == "Reprodução" else "secondary"):
            st.session_state.pagina_atual = "Reprodução"
            st.rerun()

    with col_exit:
        if st.button("🚪 Sair", use_container_width=True):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

    st.divider()

    # ==============================================================================
    # PÁGINA 1: PÁGINA INICIAL
    # ==============================================================================
    if st.session_state.pagina_atual == "Pág. Inicial":
        st.markdown("### 📋 Painel Geral de Pets")

        with st.container(border=True):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.markdown(f"**Nome do Responsável:** {perfil.get('nome', 'Laurentina de Carvalho')}")
                st.markdown(f"**Endereço:** {perfil.get('endereco', 'Luanda, Angola')}")
                st.markdown(f"**E-mail:** {perfil.get('email', 'N/I')}")
            with col_t2:
                st.markdown(f"**Telefone:** {perfil.get('telefone', '936342306 / 934071334')}")
                st.markdown(f"**Perfil:** {tipo_perfil}")
                if perfil.get("nome_canil"):
                    st.markdown(f"**Canil:** {perfil.get('nome_canil')}")

        st.write("")

        with st.expander("➕ Cadastrar Novo Pet"):
            col_np1, col_np2 = st.columns(2)
            with col_np1:
                np_nome = st.text_input("Nome do Pet")
                np_raca = st.text_input("Raça", value="SRD")
                np_nasc = st.date_input("Data de Nascimento", date(2026, 6, 15))
            with col_np2:
                np_sexo = st.selectbox("Sexo", ["Fêmea", "Macho"])
                np_pelo = st.selectbox("Tipo de Pêlo", ["Curto", "Longo", "Ondulado", "Liso"])
                np_peso = st.number_input("Peso Inicial (kg)", 1.5, step=0.1)
            np_foto = st.file_uploader("Foto do Pet", type=["png", "jpg", "jpeg"])

            if st.button("Salvar Pet", type="primary"):
                if np_nome:
                    foto_b64 = carregar_imagem_base64(np_foto)
                    garantir_autenticacao_ativa()
                    supabase.table("pets").insert({
                        "tutor_id": user_id,
                        "criador_original_id": user_id,
                        "nome": np_nome,
                        "raca": np_raca,
                        "data_nascimento": str(np_nasc),
                        "sexo": np_sexo,
                        "pelo": np_pelo,
                        "peso_atual": np_peso,
                        "foto_url": foto_b64,
                    }).execute()
                    st.session_state.pop("cache_pets", None)
                    st.success("Pet cadastrado com sucesso!")
                    st.rerun()

        st.write("")

        if meus_pets:
            for p in meus_pets:
                with st.container(border=True):
                    col_foto, col_info, col_links = st.columns([1, 1.8, 1.6])

                    with col_foto:
                        if p.get("foto_url"):
                            st.image(p["foto_url"], width=110)
                        else:
                            st.markdown("📷 *Sem foto*")

                    with col_info:
                        st.markdown(f"**Nome:** {p['nome']}")
                        st.markdown(f"**Raça:** {p.get('raca', 'SRD')}")
                        st.markdown(f"**Idade:** {calcular_idade(p['data_nascimento'])}")
                        st.markdown(f"**Sexo / Pêlo:** {p.get('sexo', 'Macho')} | {p.get('pelo', 'Curto')}")
                        st.markdown(f"**Peso:** {p.get('peso_atual', 0.0)} kg")
                        status_str = "🔴 Falecido" if p.get("status_vida") == "Falecido" else "🟢 Vivo"
                        st.markdown(f"**Status:** {status_str}")

                    with col_links:
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("✏️ Editar", key=f"btn_ed_pet_{p['id']}", use_container_width=True):
                                modal_editar_pet(p)
                        with col_b2:
                            if st.button("🗑️ Eliminar", key=f"btn_del_pet_{p['id']}", use_container_width=True):
                                modal_eliminar_pet(p)

                        if st.button("🔗 Consultar Detalhes", key=f"det_{p['id']}", use_container_width=True):
                            st.session_state.pet_selecionado_id = p["id"]
                            st.session_state.pagina_atual = "Consultar e Editar"
                            st.rerun()

                        if st.button("🩺 Enfermidades & Óbito", key=f"enf_{p['id']}", use_container_width=True):
                            st.session_state.pet_selecionado_id = p["id"]
                            st.session_state.pagina_atual = "Pág. Efermidades"
                            st.rerun()

                        vacs_p, desps_p = obter_dados_pet(p["id"])
                        pdf_b = gerar_pdf_cartao_final(perfil, p, vacs_p, desps_p)
                        st.download_button(
                            f"📥 Imprimir Cartão ({p['nome']})",
                            data=pdf_b,
                            file_name=f"cartao_{p['nome']}.pdf",
                            mime="application/pdf",
                            key=f"down_{p['id']}",
                            use_container_width=True
                        )
        else:
            st.info("Nenhum pet cadastrado sob a sua responsabilidade.")

    # ==============================================================================
    # PÁGINA 2: CONSULTAR E EDITAR
    # ==============================================================================
    elif st.session_state.pagina_atual == "Consultar e Editar":
        st.markdown("### 📝 Consultar e Editar")

        if meus_pets:
            pet_dict = {p["nome"]: p["id"] for p in meus_pets}
            lista_ids = list(pet_dict.values())
            idx_atual = lista_ids.index(st.session_state.pet_selecionado_id) if st.session_state.pet_selecionado_id in lista_ids else 0

            pet_sel_nome = st.selectbox("Selecionar Pet:", list(pet_dict.keys()), index=idx_atual)
            pet_id = pet_dict[pet_sel_nome]
            st.session_state.pet_selecionado_id = pet_id
            pet = next(p for p in meus_pets if p["id"] == pet_id)

            meses_pet = obter_meses_idade(pet["data_nascimento"])
            peso_pet = float(pet.get("peso_atual", 0.0))
            idade_humana_txt = calcular_idade_humana_equivalente(meses_pet, peso_pet)

            vacs_pet, desps_pet = obter_dados_pet(pet["id"])
            ultima_vac = vacs_pet[0] if vacs_pet else None
            ultimo_desp = desps_pet[0] if desps_pet else None

            with st.container(border=True):
                col_top_f, col_top_d, col_top_s, col_top_btns = st.columns([0.8, 1.8, 1, 1.4])
                with col_top_f:
                    if pet.get("foto_url"):
                        st.image(pet["foto_url"], width=80)
                    else:
                        st.caption("📷 *Sem foto*")
                with col_top_d:
                    st.markdown(f"**Nome:** {pet['nome']} | **Raça:** {pet.get('raca', 'SRD')}")
                    st.markdown(f"**Idade Real:** {calcular_idade(pet['data_nascimento'])} | **Sexo:** {pet.get('sexo', 'Macho')}")
                    st.markdown(f"👤 **Equivalência Humana:** `{idade_humana_txt}`")
                with col_top_s:
                    st.markdown(f"**Status:** {'🔴 Falecido' if pet.get('status_vida') == 'Falecido' else '🟢 Vivo'}")
                    st.markdown(f"**Peso Atual:** {peso_pet} kg")
                
                with col_top_btns:
                    pdf_ultimo = gerar_pdf_cartao_final(perfil, pet, vacs_pet, desps_pet)
                    st.download_button(
                        "📥 Imprimir Último Registo",
                        data=pdf_ultimo,
                        file_name=f"cartao_ultimo_registro_{pet['nome']}.pdf",
                        mime="application/pdf",
                        key="dl_u_direct",
                        use_container_width=True
                    )
                    
                    reps_data, nin_data, fil_data = None, None, None
                    garantir_autenticacao_ativa()
                    try:
                        if pet.get("sexo") == "Fêmea":
                            reps_data = supabase.table("reproducao").select("*").eq("femea_id", pet["id"]).order("data_cio", desc=True).execute().data or []
                            nin_data = supabase.table("ninhadas").select("*").eq("femea_id", pet["id"]).order("data_parto", desc=True).execute().data or []
                            if nin_data:
                                fil_data = supabase.table("filhotes_destino").select("*").eq("ninhada_id", nin_data[0]["id"]).execute().data or []
                    except APIError:
                        reps_data, nin_data, fil_data = [], [], []
                    
                    pdf_hist = gerar_pdf_historico_completo(perfil, pet, vacs_pet, desps_pet, reps_data, nin_data, fil_data)
                    st.download_button(
                        "📄 Imprimir Histórico Completo",
                        data=pdf_hist,
                        file_name=f"historico_completo_{pet['nome']}.pdf",
                        mime="application/pdf",
                        key="dl_h_direct",
                        use_container_width=True
                    )

            st.write("")

            # ==============================================================================
            # 🩺 TABELA DE EQUIVALÊNCIA POR PORTE & PARÂMETROS FISIOLÓGICOS
            # ==============================================================================
            with st.container(border=True):
                st.markdown("#### 🩺 Guia Clínico: Equivalência de Idade por Porte e Parâmetros Fisiológicos")
                
                col_eq_tab, col_fisio_tab = st.columns([1.3, 1.1], gap="medium")

                with col_eq_tab:
                    st.markdown("##### ⏳ Equivalência de Idade Canina vs. Humana por Porte")
                    df_equiv_porte = pd.DataFrame([
                        {"Idade do Cão": "1 mês", "Porte Pequeno (<10kg)": "1 ano", "Porte Médio (10-25kg)": "1 ano", "Porte Grande (25-45kg)": "1 ano", "Porte Gigante (>45kg)": "1 ano"},
                        {"Idade do Cão": "6 meses", "Porte Pequeno (<10kg)": "10 anos", "Porte Médio (10-25kg)": "10 anos", "Porte Grande (25-45kg)": "9 anos", "Porte Gigante (>45kg)": "8 anos"},
                        {"Idade do Cão": "1 ano", "Porte Pequeno (<10kg)": "15 anos", "Porte Médio (10-25kg)": "15 anos", "Porte Grande (25-45kg)": "14 anos", "Porte Gigante (>45kg)": "12 anos"},
                        {"Idade do Cão": "2 anos", "Porte Pequeno (<10kg)": "24 anos", "Porte Médio (10-25kg)": "24 anos", "Porte Grande (25-45kg)": "22 anos", "Porte Gigante (>45kg)": "20 anos"},
                        {"Idade do Cão": "3 anos", "Porte Pequeno (<10kg)": "28 anos", "Porte Médio (10-25kg)": "29 anos", "Porte Grande (25-45kg)": "30 anos", "Porte Gigante (>45kg)": "32 anos"},
                        {"Idade do Cão": "5 anos", "Porte Pequeno (<10kg)": "36 anos", "Porte Médio (10-25kg)": "39 anos", "Porte Grande (25-45kg)": "42 anos", "Porte Gigante (>45kg)": "49 anos"},
                        {"Idade do Cão": "7 anos", "Porte Pequeno (<10kg)": "44 anos", "Porte Médio (10-25kg)": "49 anos", "Porte Grande (25-45kg)": "54 anos", "Porte Gigante (>45kg)": "64 anos"},
                        {"Idade do Cão": "10 anos", "Porte Pequeno (<10kg)": "56 anos", "Porte Médio (10-25kg)": "64 anos", "Porte Grande (25-45kg)": "72 anos", "Porte Gigante (>45kg)": "86 anos"},
                    ])
                    st.dataframe(df_equiv_porte, use_container_width=True, hide_index=True)

                with col_fisio_tab:
                    st.markdown(f"##### 🔬 Constantes Fisiológicas Caninas ({pet['nome']})")
                    df_fisio = pd.DataFrame([
                        {"Parâmetro Fisiológico": "🌡️ Temperatura Rectal", "Valores de Referência": "38,0 °C a 39,2 °C"},
                        {"Parâmetro Fisiológico": "🫁 Frequência Respiratória", "Valores de Referência": "10 a 30 resp./minuto"},
                        {"Parâmetro Fisiológico": "💓 Pulsação (Freq. Cardíaca)", "Valores de Referência": "70 a 140 bpm"},
                        {"Parâmetro Fisiológico": "🌸 Idade da Puberdade", "Valores de Referência": "6 a 12 meses (F) / 6 a 10 m (M)"},
                        {"Parâmetro Fisiológico": "🔄 Frequência de Cios", "Valores de Referência": "2 vezes ao ano (~ 6 meses)"},
                        {"Parâmetro Fisiológico": "🐾 Período Favorável à Cobrição", "Valores de Referência": "9.º ao 14.º dia do cio"},
                        {"Parâmetro Fisiológico": "🤰 Duração da Gestação", "Valores de Referência": "58 a 68 dias (Média: 63 dias)"},
                    ])
                    st.dataframe(df_fisio, use_container_width=True, hide_index=True)

            st.write("")
            col_vac, col_desp = st.columns(2, gap="medium")

            # --- COLUNA VACINA ---
            with col_vac:
                with st.container(border=True):
                    col_vt, col_vb = st.columns([2.2, 0.8])
                    with col_vt:
                        st.markdown("#### 💉 Última Vacina Aplicada")
                    with col_vb:
                        if st.button("➕ Novo", key="btn_open_modal_v", use_container_width=True):
                            modal_editar_vacina(pet)

                    if ultima_vac:
                        st.markdown(f"**Vacina:** `{ultima_vac['nome_vacina']}`")
                        doencas_str = ultima_vac.get('doencas_protegidas') or "Informação não especificada."
                        st.info(f"🛡️ **Protege contra:** {doencas_str}")
                        st.write(f"📅 **Aplicação:** {ultima_vac['data_aplicacao']} | 🔄 **Próxima Dose:** {ultima_vac['proxima_dose']}")
                    else:
                        st.warning("Nenhuma vacina registrada para este pet.")

                    st.divider()
                    st.markdown("##### 📋 Histórico de Vacinas")
                    if vacs_pet:
                        st.dataframe(pd.DataFrame([{"Vacina": v["nome_vacina"], "Aplicação": v["data_aplicacao"], "Próxima Dose": v["proxima_dose"]} for v in vacs_pet]), use_container_width=True, hide_index=True)
                    else:
                        st.info("Sem histórico de vacinação.")

            # --- COLUNA DESPARASITANTE ---
            with col_desp:
                with st.container(border=True):
                    col_dt_t, col_dt_b = st.columns([2.2, 0.8])
                    with col_dt_t:
                        st.markdown("#### 🪱 Última Desparasitação")
                    with col_dt_b:
                        if st.button("➕ Novo", key="btn_open_modal_d", use_container_width=True):
                            modal_editar_desparasitante(pet)

                    if ultimo_desp:
                        st.markdown(f"**Produto:** `{ultimo_desp['nome_produto']}` ({ultimo_desp['tipo']})")
                        st.write(f"📅 **Aplicação:** {ultimo_desp['data_aplicacao']} | 🔄 **Próxima:** {ultimo_desp['proxima_dose']} | ⚖️ **Peso:** {ultimo_desp['peso_kg']} kg")
                    else:
                        st.warning("Nenhum controlo registrado.")

                    st.divider()
                    st.markdown("##### 📋 Histórico Parasitário")
                    if desps_pet:
                        st.dataframe(pd.DataFrame([{"Tipo": d["tipo"], "Produto": d["nome_produto"], "Peso": f"{d['peso_kg']} kg", "Aplicação": d["data_aplicacao"], "Próxima Dose": d["proxima_dose"]} for d in desps_pet]), use_container_width=True, hide_index=True)
                    else:
                        st.info("Sem histórico de desparasitação.")

            # --- SE FOR FÊMEA: RESUMO REPRODUTIVO ---
            if pet.get("sexo") == "Fêmea":
                st.write("")
                with st.container(border=True):
                    st.markdown("#### 🍼 Resumo Reprodutivo & Ninhadas (Fêmea)")
                    garantir_autenticacao_ativa()
                    try:
                        reps_f = supabase.table("reproducao").select("*").eq("femea_id", pet["id"]).order("data_cio", desc=True).execute().data or []
                        nins_f = supabase.table("ninhadas").select("*").eq("femea_id", pet["id"]).order("data_parto", desc=True).execute().data or []
                    except APIError:
                        reps_f, nins_f = [], []
                    
                    col_rf1, col_rf2 = st.columns(2)
                    with col_rf1:
                        if reps_f:
                            r_ult = reps_f[0]
                            st.write(f"🌸 **Último Cio Registado:** {r_ult.get('data_cio')}")
                            st.write(f"🐾 **Último Cruzamento:** {r_ult.get('data_cruzamento','Sem cruzamento')} (Macho: {r_ult.get('macho_nome','N/I')})")
                            st.write(f"🤰 **Gestação:** {'Confirmada' if r_ult.get('ficou_gravida') else 'Não confirmada'}")
                        else:
                            st.info("Nenhum ciclo reprodutivo registrado.")
                    with col_rf2:
                        if nins_f:
                            n_ult = nins_f[0]
                            st.write(f"🐣 **Último Parto:** {n_ult.get('data_parto')}")
                            st.write(f"📊 **Filhotes Nascidos:** {n_ult.get('total_nascidos')} (Machos: {n_ult.get('total_machos')}, Fêmeas: {n_ult.get('total_femeas')}, Óbitos: {n_ult.get('total_obitos')})")
                        else:
                            st.info("Nenhuma ninhada registrada.")

            # --- GRÁFICOS (TAMANHO COMPACTO) ---
            st.write("")
            with st.container(border=True):
                st.markdown("#### 📊 Análise Gráfica do Histórico Clínico")
                col_g1, col_g2 = st.columns(2, gap="medium")
                
                with col_g1:
                    df_peso_hist = pd.DataFrame(desps_pet)
                    if not df_peso_hist.empty and "peso_kg" in df_peso_hist.columns:
                        df_peso_hist = df_peso_hist[df_peso_hist["peso_kg"] > 0].sort_values("data_aplicacao")
                    
                    if not df_peso_hist.empty and len(df_peso_hist) > 0:
                        fig_p, ax_p = plt.subplots(figsize=(3.8, 2.2))
                        ax_p.plot(df_peso_hist["data_aplicacao"], df_peso_hist["peso_kg"], marker="o", color="#4E877C", linewidth=2, markersize=5)
                        ax_p.fill_between(df_peso_hist["data_aplicacao"], df_peso_hist["peso_kg"], color="#4E877C", alpha=0.15)
                        ax_p.set_title("📈 Evolução de Peso (kg)", fontsize=9, fontweight="bold", color="#2F4F48")
                        ax_p.set_ylabel("kg", fontsize=7.5)
                        ax_p.tick_params(axis='x', rotation=25, labelsize=7)
                        ax_p.tick_params(axis='y', labelsize=7)
                        plt.tight_layout()
                        st.pyplot(fig_p)
                        plt.close(fig_p)
                    else:
                        st.info("💡 Registe os pesos nas desparasitações para gerar a curva de crescimento corporal.")

                with col_g2:
                    total_v = len(vacs_pet)
                    total_d = len(desps_pet)
                    
                    if total_v > 0 or total_d > 0:
                        fig_b, ax_b = plt.subplots(figsize=(3.8, 2.2))
                        labels_b = ["Vacinas", "Parasitário"]
                        valores_b = [total_v, total_d]
                        cores_b = ["#D47A5B", "#4E877C"]
                        
                        wedges, texts, autotexts = ax_b.pie(
                            valores_b, 
                            labels=labels_b, 
                            autopct="%1.0f%%", 
                            startangle=90, 
                            colors=cores_b,
                            wedgeprops=dict(width=0.4, edgecolor='white', linewidth=1.5)
                        )
                        for at in autotexts:
                            at.set_color('white')
                            at.set_weight('bold')
                            at.set_fontsize(7.5)
                        for t in texts:
                            t.set_fontsize(7.5)
                            
                        ax_b.set_title("🛡️ Imunização & Prevenção", fontsize=9, fontweight="bold", color="#2F4F48")
                        plt.tight_layout()
                        st.pyplot(fig_b)
                        plt.close(fig_b)
                    else:
                        st.info("💡 Nenhum procedimento realizado ainda.")

    # ==============================================================================
    # PÁGINA 3: ENFERMIDADES
    # ==============================================================================
    elif st.session_state.pagina_atual == "Pág. Efermidades":
        st.markdown("### 🩺 Gestão de Enfermidades e Óbitos")

        if meus_pets:
            pet_dict = {p["nome"]: p["id"] for p in meus_pets}
            lista_ids = list(pet_dict.values())
            idx_atual = lista_ids.index(st.session_state.pet_selecionado_id) if st.session_state.pet_selecionado_id in lista_ids else 0

            pet_sel_nome = st.selectbox("Selecionar Pet:", list(pet_dict.keys()), index=idx_atual)
            pet_id = pet_dict[pet_sel_nome]
            st.session_state.pet_selecionado_id = pet_id
            pet = next(p for p in meus_pets if p["id"] == pet_id)

            with st.container(border=True):
                col_top_f, col_top_d, col_top_s = st.columns([1, 2, 1])
                with col_top_f:
                    if pet.get("foto_url"):
                        st.image(pet["foto_url"], width=80)
                    else:
                        st.caption("📷 *Sem foto*")
                with col_top_d:
                    st.markdown(f"**Nome:** {pet['nome']} | **Raça:** {pet.get('raca', 'SRD')}")
                    st.markdown(f"**Idade:** {calcular_idade(pet['data_nascimento'])} | **Sexo:** {pet.get('sexo', 'Macho')}")
                with col_top_s:
                    st.markdown(f"**Status:** {'🔴 Falecido' if pet.get('status_vida') == 'Falecido' else '🟢 Vivo'}")

            st.write("")
            col_enf_form, col_enf_hist = st.columns([1.2, 1], gap="medium")

            with col_enf_form:
                with st.container(border=True):
                    st.markdown("#### 🩺 Acompanhamento Clínico")
                    local_trat = st.text_input("Onde está a ser tratado?", value=pet.get("local_tratamento") or "")
                    doenca_diag = st.text_input("Diagnóstico / Doença:", value=pet.get("doenca_nome") or "")
                    meds_uso = st.text_area("Medicamentos em uso:", value=pet.get("medicamentos_em_uso") or "")
                    evolucao_txt = st.text_area("Evolução clínica:", value=pet.get("evolucao_melhorias") or "")

                    st.markdown("#### 🔴 Notificação de Falecimento")
                    is_falecido = pet.get("status_vida") == "Falecido"
                    chk_falecido = st.checkbox("Marcar como Falecido", value=is_falecido, key="ck_f")
                    status_vida_final = "Falecido" if chk_falecido else "Vivo"

                    if st.button("Gravar Alterações", key="btn_gravar_enf", type="primary"):
                        esta_doente_flag = bool(doenca_diag.strip())
                        garantir_autenticacao_ativa()
                        supabase.table("pets").update({
                            "esta_doente": esta_doente_flag,
                            "doenca_nome": doenca_diag if esta_doente_flag else None,
                            "local_tratamento": local_trat if esta_doente_flag else None,
                            "medicamentos_em_uso": meds_uso if esta_doente_flag else None,
                            "evolucao_melhorias": evolucao_txt if esta_doente_flag else None,
                            "status_vida": status_vida_final,
                            "data_falecimento": str(date.today()) if status_vida_final == "Falecido" else None,
                        }).eq("id", pet["id"]).execute()
                        st.session_state.pop("cache_pets", None)
                        st.success("Informações clínicas atualizadas!")
                        st.rerun()

            with col_enf_hist:
                with st.container(border=True):
                    st.markdown("#### Histórico Atual:")
                    if pet.get("doenca_nome"):
                        st.markdown(f"**Diagnóstico:** {pet.get('doenca_nome')}")
                        st.markdown(f"**Local:** {pet.get('local_tratamento', 'N/I')}")
                        st.markdown(f"**Medicamentos:** {pet.get('medicamentos_em_uso', 'N/I')}")
                        st.markdown(f"**Evolução:** {pet.get('evolucao_melhorias', 'N/I')}")
                    else:
                        st.info("Nenhuma enfermidade ativa registrada.")

    # ==============================================================================
    # PÁGINA 4: REPRODUÇÃO & NINHADAS
    # ==============================================================================
    elif st.session_state.pagina_atual == "Reprodução":
        st.markdown("### 🍼 Ciclo Reprodutivo, Gestação e Ninhadas")

        femeas = [p for p in meus_pets if p.get("sexo") == "Fêmea"]
        machos_sistema = [p for p in meus_pets if p.get("sexo") == "Macho"]

        if not femeas:
            st.warning("⚠️ Cadastre uma fêmea na Página Inicial para aceder ao controlo reprodutivo.")
        else:
            femea_dict = {f["nome"]: f for f in femeas}
            f_nome_sel = st.selectbox("Selecione a Fêmea:", list(femea_dict.keys()), key="sb_femea_rep")
            femea_sel = femea_dict[f_nome_sel]

            idade_f = calcular_idade(femea_sel["data_nascimento"])
            meses_f = obter_meses_idade(femea_sel["data_nascimento"])
            prev_1_cio = calcular_previsao_primeiro_cio(femea_sel["data_nascimento"])

            with st.container(border=True):
                col_f1, col_f2, col_f3 = st.columns([0.8, 1.5, 1.5])
                with col_f1:
                    if femea_sel.get("foto_url"):
                        st.image(femea_sel["foto_url"], width=80)
                with col_f2:
                    st.markdown(f"**Fêmea:** {femea_sel['nome']} ({femea_sel.get('raca','SRD')})")
                    st.markdown(f"🎂 **Idade Atual:** {idade_f}")
                with col_f3:
                    if meses_f < 6:
                        st.info(f"🌸 **Previsão 1.º Cio:** ~**{prev_1_cio.strftime('%d/%m/%Y')}**.")
                    else:
                        st.success("🌸 **Status:** Adulta / Apta para reprodução.")

            st.write("")
            aba_rep1, aba_rep2 = st.tabs(["🐾 1. Registo de Cruzamento & Gestação", "🍼 2. Parto, Ninhada & Destino dos Filhotes"])

            # --- ABA 1 ---
            with aba_rep1:
                st.markdown("#### 🧬 Registar Cruzamento")
                with st.form(f"form_cruzamento_{femea_sel['id']}"):
                    col_cr1, col_cr2 = st.columns(2)
                    with col_cr1:
                        dt_cio = st.date_input("Data Início do Cio:", date.today())
                        cruzou_flag = st.checkbox("Houve cruzamento?", value=True)
                        dt_cruzamento = st.date_input("Data do Cruzamento:", date.today())
                    with col_cr2:
                        opcoes_macho = ["Macho Externo"] + [m["nome"] for m in machos_sistema]
                        macho_sel = st.selectbox("Macho Reprodutor:", opcoes_macho)
                        macho_nome_manual = st.text_input("Nome do Macho (se externo):", value="" if macho_sel != "Macho Externo" else "Padreador")
                        ficou_gravida = st.checkbox("Gravidez Confirmada?", value=True)

                    dt_parto_estimada = calcular_data_parto(dt_cruzamento) if ficou_gravida else None
                    if ficou_gravida:
                        st.info(f"⏳ **Data Provável do Parto:** **{dt_parto_estimada.strftime('%d/%m/%Y')}**")

                    notas_gest = st.text_area("Notas Clínicas:", placeholder="Ex: Ecografia dia 30 confirmou 5 fetos...")

                    if st.form_submit_button("Salvar Cruzamento", type="primary"):
                        macho_final = macho_sel if macho_sel != "Macho Externo" else macho_nome_manual
                        macho_id_final = next((m["id"] for m in machos_sistema if m["nome"] == macho_sel), None)

                        garantir_autenticacao_ativa()
                        supabase.table("reproducao").insert({
                            "femea_id": femea_sel["id"],
                            "data_cio": str(dt_cio),
                            "proximo_cio_estimado": str(dt_cio + timedelta(days=180)),
                            "cruzou": cruzou_flag,
                            "data_cruzamento": str(dt_cruzamento) if cruzou_flag else None,
                            "macho_nome": macho_final,
                            "macho_id": macho_id_final,
                            "ficou_gravida": ficou_gravida,
                            "data_provavel_parto": str(dt_parto_estimada) if dt_parto_estimada else None,
                            "notas_acompanhamento": notas_gest,
                        }).execute()
                        invalidar_cache_pet(femea_sel["id"])
                        st.success("Registo reprodutivo salvo!")
                        st.rerun()

                st.divider()
                st.markdown("##### 📜 Histórico de Cruzamentos")
                garantir_autenticacao_ativa()
                if f"reps_{femea_sel['id']}" not in st.session_state:
                    try:
                        st.session_state[f"reps_{femea_sel['id']}"] = supabase.table("reproducao").select("*").eq("femea_id", femea_sel["id"]).order("data_cio", desc=True).execute().data or []
                    except APIError:
                        st.session_state[f"reps_{femea_sel['id']}"] = []
                reps_femea = st.session_state[f"reps_{femea_sel['id']}"]

                if reps_femea:
                    for r in reps_femea:
                        with st.container(border=True):
                            st.markdown(f"**Data do Cio:** {r['data_cio']} | **Macho:** {r.get('macho_nome','N/I')}")
                            if r.get("ficou_gravida"):
                                st.success(f"🤰 **Gestação Confirmada** | Parto Previsto: **{r.get('data_provavel_parto','-')}**")
                else:
                    st.info("Nenhum cruzamento registrado.")

            # --- ABA 2 ---
            with aba_rep2:
                st.markdown("#### 🍼 Registo de Ninhadas e Destino")
                garantir_autenticacao_ativa()
                if f"reps_{femea_sel['id']}" not in st.session_state:
                    try:
                        st.session_state[f"reps_{femea_sel['id']}"] = supabase.table("reproducao").select("*").eq("femea_id", femea_sel["id"]).order("data_cio", desc=True).execute().data or []
                    except APIError:
                        st.session_state[f"reps_{femea_sel['id']}"] = []
                reps_ativas = [r for r in st.session_state[f"reps_{femea_sel['id']}"] if r.get("ficou_gravida")]

                if not reps_ativas:
                    st.info("Registe primeiro uma gestação na aba ao lado.")
                else:
                    rep_escolhida = reps_ativas[0]
                    
                    with st.container(border=True):
                        st.markdown(f"##### 🐣 Lançar Parto de **{femea_sel['nome']}**")
                        
                        col_dt, col_tot_manual = st.columns(2)
                        with col_dt:
                            dt_parto_real = st.date_input("Data do Parto:", date.today(), key="in_dt_parto")
                        with col_tot_manual:
                            total_nasc_manual = st.number_input(
                                "🔢 Total Geral de Filhotes Nascidos (Inserir Manualmente):",
                                min_value=0,
                                value=5,
                                help="Insira o número total de filhotes nascidos no parto.",
                                key="in_total_manual"
                            )

                        st.write("**Detalhamento dos Filhotes:**")
                        col_n2, col_n3, col_n4 = st.columns(3)
                        with col_n2:
                            n_machos = st.number_input("Machos Nascidos:", min_value=0, value=2, key="in_m_count")
                        with col_n3:
                            n_femeas = st.number_input("Fêmeas Nascidas:", min_value=0, value=3, key="in_f_count")
                        with col_n4:
                            n_obitos = st.number_input("Óbitos (Falecidos):", min_value=0, value=0, key="in_o_count")

                        obs_ninhada = st.text_input("Observações do Parto:", value="Parto normal e saudável.")

                        if st.button("Gravar Parto e Ninhada", type="primary", key="btn_save_nin"):
                            supabase.table("ninhadas").insert({
                                "reproducao_id": rep_escolhida["id"],
                                "femea_id": femea_sel["id"],
                                "data_parto": str(dt_parto_real),
                                "total_nascidos": int(total_nasc_manual),
                                "total_machos": int(n_machos),
                                "total_femeas": int(n_femeas),
                                "total_obitos": int(n_obitos),
                                "observacoes": obs_ninhada,
                            }).execute()
                            invalidar_cache_pet(femea_sel["id"])
                            st.success("Ninhada registada com sucesso!")
                            st.rerun()

                    st.divider()

                    if f"ninhadas_{femea_sel['id']}" not in st.session_state:
                        try:
                            st.session_state[f"ninhadas_{femea_sel['id']}"] = supabase.table("ninhadas").select("*").eq("femea_id", femea_sel["id"]).order("data_parto", desc=True).execute().data or []
                        except APIError:
                            st.session_state[f"ninhadas_{femea_sel['id']}"] = []
                    ninhadas_db = st.session_state[f"ninhadas_{femea_sel['id']}"]

                    if ninhadas_db:
                        n_atual = ninhadas_db[0]
                        
                        with st.container(border=True):
                            col_info_nin, col_btn_ed_nin = st.columns([3, 1])
                            with col_info_nin:
                                st.markdown(f"#### 🐾 Ninhada Ativa (Data do Parto: `{n_atual['data_parto']}`)")
                                st.markdown(
                                    f"🔢 **Total de Nascidos:** `{n_atual.get('total_nascidos', 0)}`  |  "
                                    f"♂️ **Machos:** `{n_atual.get('total_machos', 0)}`  |  "
                                    f"♀️ **Fêmeas:** `{n_atual.get('total_femeas', 0)}`  |  "
                                    f"⚠️ **Óbitos:** `{n_atual.get('total_obitos', 0)}`"
                                )
                            with col_btn_ed_nin:
                                if st.button("✏️ Editar Ninhada", key=f"btn_ed_nin_{n_atual['id']}", use_container_width=True):
                                    modal_editar_ninhada(n_atual, femea_sel)

                        st.write("")
                        st.markdown("### 🐾 Atribuição e Destino Individual dos Filhotes")
                        
                        with st.expander("➕ Registar / Atribuir Destino a um Filhote"):
                            col_f1, col_f2 = st.columns(2)
                            with col_f1:
                                id_filhote = st.text_input("Nome/Identificação do Filhote:", placeholder="Ex: Filhote 1 - Macho Castanho")
                                sexo_f = st.selectbox("Sexo:", ["Macho", "Fêmea"], key="sb_s_f")
                                st_filhote = st.selectbox("Status:", ["Vivo", "Falecido"], key="sb_st_f")
                            with col_f2:
                                tipo_dest = st.radio("Entregue a:", ["Utilizador na App", "Pessoa Externa"])
                                tutor_app_id, ext_nome, ext_tel = None, None, None

                                if tipo_dest == "Utilizador na App":
                                    email_busca = st.text_input("E-mail do Utilizador:")
                                    if email_busca:
                                        usr_f = supabase.table("tutores").select("id, nome").eq("email", email_busca).execute().data
                                        if usr_f:
                                            tutor_app_id = usr_f[0]["id"]
                                            st.success(f"Encontrado: {usr_f[0]['nome']}")
                                        else:
                                            st.warning("Utilizador não encontrado.")
                                else:
                                    ext_nome = st.text_input("Nome:")
                                    ext_tel = st.text_input("Telefone:")

                            if st.button("Guardar Destino", type="primary"):
                                if id_filhote:
                                    supabase.table("filhotes_destino").insert({
                                        "ninhada_id": n_atual["id"],
                                        "identificacao_filhote": id_filhote,
                                        "sexo": sexo_f,
                                        "status_vida": st_filhote,
                                        "destino_tipo": "Sistema" if tipo_dest == "Utilizador na App" else "Externo",
                                        "tutor_sistema_id": tutor_app_id,
                                        "novo_dono_nome": ext_nome,
                                        "novo_dono_telefone": ext_tel,
                                    }).execute()

                                    if tutor_app_id and st_filhote == "Vivo":
                                        supabase.table("pets").insert({
                                            "tutor_id": tutor_app_id,
                                            "criador_original_id": user_id,
                                            "nome": id_filhote,
                                            "raca": femea_sel.get("raca", "SRD"),
                                            "data_nascimento": n_atual["data_parto"],
                                            "sexo": sexo_f,
                                            "pelo": "Curto",
                                            "peso_atual": 1.0,
                                        }).execute()

                                    invalidar_cache_pet(femea_sel["id"])
                                    st.session_state.pop("cache_pets", None)
                                    st.success(f"Destino de {id_filhote} guardado!")
                                    st.rerun()

                        try:
                            filhotes_cad = supabase.table("filhotes_destino").select("*").eq("ninhada_id", n_atual["id"]).execute().data or []
                        except APIError:
                            filhotes_cad = []
                            
                        if filhotes_cad:
                            tab_f = [{"Identificação": fc["identificacao_filhote"], "Sexo": fc["sexo"], "Status": fc["status_vida"], "Destino": fc.get("novo_dono_nome") or "Utilizador Sistema"} for fc in filhotes_cad]
                            st.dataframe(pd.DataFrame(tab_f), use_container_width=True, hide_index=True)
                        else:
                            st.info("Nenhum filhote atribuído nesta ninhada.")