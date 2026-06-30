import streamlit as st
import os
import uuid
import glob
from google import genai
from google.genai import types
from supabase import create_client, Client
import extra_streamlit_components as stx

# 1. CONFIGURAÇÃO DA PÁGINA (Aparência de App Nativo)
st.set_page_config(
    page_title="ElAI",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Estilização para embutir comportamento visual limpo
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .block-container {padding-top: 2rem;}
        .stButton>button {width: 100%; border-radius: 8px;}
    </style>
""", unsafe_allow_html=True)

# 2. CONEXÃO COM OS SERVIÇOS (Supabase & Gemini via Secrets do Streamlit)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "SUA_URL_DO_SUPABASE_AQUI")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "SUA_ANON_KEY_DO_SUPABASE_AQUI")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "SUA_GEMINI_API_KEY_AQUI")

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")

# 3. GERENCIAMENTO DE IDENTIDADE PERSISTENTE (Via Cookies do Navegador)
#@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

# Resgata de forma segura o cookie do celular ou gera um UUID definitivo de primeiro acesso
if "user_id" not in st.session_state:
    uuid_salvo = cookie_manager.get(cookie="guidoc_user_uuid")
    if uuid_salvo:
        st.session_state.user_id = uuid_salvo
    else:
        novo_uuid = str(uuid.uuid4())
        st.session_state.user_id = novo_uuid
        cookie_manager.set(cookie="guidoc_user_uuid", val=novo_uuid)

user_id = st.session_state.get("user_id", str(uuid.uuid4()))

# Inicializa estados de histórico e arquivos locais
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "initialized" not in st.session_state:
    st.session_state.initialized = False

# 4. CARREGAR CONFIGURAÇÕES E HISTÓRICO DO SUPABASE (Apenas no início da sessão)
if not st.session_state.initialized and "supabase" in globals():
    try:
        # Carrega histórico anterior filtrado por UUID
        chat_res = supabase.table("chat_history").select("role", "content").eq("user_id", user_id).order("created_at").execute()
        st.session_state.chat_history = [{"role": row["role"], "content": row["content"]} for row in chat_res.data]
        
        # Carrega arquivos selecionados anteriormente pelo usuário
        settings_res = supabase.table("user_settings").select("selected_files").eq("user_id", user_id).execute()
        if settings_res.data:
            st.session_state.selected_files = settings_res.data[0]["selected_files"]
        else:
            st.session_state.selected_files = []
            
        st.session_state.initialized = True
    except Exception as e:
        st.session_state.selected_files = []
        st.session_state.initialized = True

# Garantia de inicialização do estado de seleção
if "selected_files" not in st.session_state:
    st.session_state.selected_files = []

# 5. MAPEAMENTO DO DIRETÓRIO DO GITHUB (docs/manuais e docs/tips)
def listar_documentos_disponiveis():
    manuais = glob.glob("docs/manuais/*")
    tips = glob.glob("docs/tips/*")
    return sorted(manuais), sorted(tips)

manuais_disponiveis, tips_disponiveis = listar_documentos_disponiveis()

# 6. INTERFACE: MENU DE CONFIGURAÇÕES (Engrenagem Expansível)
with st.expander("⚙️ Configurações do Veículo (Selecione seus Manuais e Dicas)"):
    st.markdown("Marque os conteúdos que o Agente deve usar como base de conhecimento:")
    
    novos_selecionados = []
    
    if manuais_disponiveis:
        st.markdown("**📄 Manuais do Proprietário:**")
        for caminho in manuais_disponiveis:
            nome_arquivo = os.path.basename(caminho)
            ja_marcado = caminho in st.session_state.selected_files
            if st.checkbox(nome_arquivo, value=ja_marcado, key=f"chk_{caminho}"):
                novos_selecionados.append(caminho)
                
    if tips_disponiveis:
        st.markdown("**⚡ Dicas e Guias de Carregamento:**")
        for caminho in tips_disponiveis:
            nome_arquivo = os.path.basename(caminho)
            ja_marcado = caminho in st.session_state.selected_files
            if st.checkbox(nome_arquivo, value=ja_marcado, key=f"chk_{caminho}"):
                novos_selecionados.append(caminho)

    if st.button("💾 Salvar Configurações"):
        try:
            st.session_state.selected_files = novos_selecionados
            supabase.table("user_settings").upsert({
                "user_id": user_id,
                "selected_files": novos_selecionados
            }).execute()
            st.success("Configurações salvas com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar configurações: {e}")

st.markdown("---")

# 7. INTERFACE PRINCIPAL DO CHAT
st.title("⚡ ElAI")
st.caption("Electric Assistant Intelligence | Protegido conforme regras da LGPD")
st.caption(f"ID do Dispositivo: '{user_id[:8]}...'")

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Como posso ajudar com o seu veículo elétrico hoje?"):
    if not st.session_state.selected_files:
        st.warning("⚠️ Abra a engrenagem ⚙️ acima e selecione pelo menos um manual ou guia para ativar o assistente.")
    else:
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        try:
            supabase.table("chat_history").insert({"user_id": user_id, "role": "user", "content": prompt}).execute()
        except Exception:
            pass

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                
                contexto_documentos = ""
                for caminho_arquivo in st.session_state.selected_files:
                    if os.path.exists(caminho_arquivo):
                        nome = os.path.basename(caminho_arquivo)
                        if caminho_arquivo.endswith(('.txt', '.md', '.tips')):
                            with open(caminho_arquivo, 'r', encoding='utf-8') as file_content:
                                contexto_documentos += f"\n--- CONTEÚDO DO ARQUIVO: {nome} ---\n"
                                contexto_documentos += file_content.read()
                        else:
                            contexto_documentos += f"\n[Arquivo de referência ativo na base: {nome}]\n"

                system_instruction = (
                    "Você é um engenheiro assistente especialista em veículos elétricos e focado estritamente nas bases de dados fornecidas.\n\n"
                    "Regras Absolutas de Resposta:\n"
                    "1. Responda APENAS com base nos conteúdos textuais e referências anexadas abaixo.\n"
                    "2. Se a resposta exata para a pergunta do usuário não estiver contida nos documentos fornecidos, responda estritamente: "
                    "'Desculpe, não encontrei essa informação na base de conhecimento que tenho acesso.'\n"
                    "3. Nunca infira ou invente dados ou use dados gerais de internet que não estejam listados nas fontes anexadas.\n"
                    "4. Seja direto, respeitoso, limpo e focado na segurança do condutor.\n"
                    "5. Sempre reforce com o condutor que a consulta não deve ser realizada durante direção/condução do veículo."
                )

                contents_payload = [
                    f"CONTEXTO DOS MANUAIS ATIVOS:\n{contexto_documentos}\n",
                    f"PERGUNTA DO USUÁRIO: {prompt}"
                ]

                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.0
                    )
                )

                resposta_final = response.text
                message_placeholder.markdown(resposta_final)
                
                st.session_state.chat_history.append({"role": "assistant", "content": resposta_final})
                supabase.table("chat_history").insert({"user_id": user_id, "role": "assistant", "content": resposta_final}).execute()

            except Exception as e:
                # Trata especificamente o erro de indisponibilidade ou alta demanda
                if "503" in str(e) or "high demand" in str(e).lower():
                    st.error("⚠️ O servidor da IA está muito carregado no momento devido à alta demanda global. Por favor, aguarde alguns segundos e envie sua pergunta novamente.")
                else:
                    st.error(f"Erro ao gerar resposta da Inteligência Artificial: {e}")
