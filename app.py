import streamlit as st
import os
import tempfile
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Gui AI Doc Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stButton>button {
            width: 100%;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_files_info" not in st.session_state:
    st.session_state.uploaded_files_info = {}

with st.sidebar:
    st.title("⚙️ Configurações & Fontes")
    api_key_input = st.text_input("Sua Gemini API Key:", type="password", value=st.session_state.api_key)
    if api_key_input:
        st.session_state.api_key = api_key_input
    
    st.markdown("---")
    st.subheader("📚 Gerenciador de Documentos")
    
    uploaded_files = st.file_uploader(
        "Adicione Manuais, PDFs ou Textos:", 
        type=["pdf", "txt", "md"], 
        accept_multiple_files=True,
        key="uploader"
    )
    
    if uploaded_files and st.session_state.api_key:
        try:
            client = genai.Client(api_key=st.session_state.api_key)
            for f in uploaded_files:
                if f.name not in st.session_state.uploaded_files_info:
                    with st.spinner(f"Indexando {f.name}..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{f.name.split('.')[-1]}") as tmp:
                            tmp.write(f.getvalue())
                            tmp_path = tmp.name
                        
                        gemini_file = client.files.upload(file=tmp_path)
                        st.session_state.uploaded_files_info[f.name] = gemini_file.name
                        os.remove(tmp_path)
            st.success("Documentos prontos!")
        except Exception as e:
            st.error(f"Erro: {e}")
            
    elif uploaded_files and not st.session_state.api_key:
        st.warning("⚠️ Insira sua API Key acima.")

    if st.session_state.uploaded_files_info:
        st.markdown("---")
        st.write("**Arquivos Ativos na Memória:**")
        
        arquivos_para_deletar = []
        for nome_arquivo, uri_gemini in list(st.session_state.uploaded_files_info.items()):
            col1, col2 = st.columns([4, 1])
            col1.text(f"📄 {nome_arquivo[:18]}...")
            if col2.button("❌", key=f"del_{nome_arquivo}"):
                arquivos_para_deletar.append(nome_arquivo)
                
        if arquivos_para_deletar:
            client = genai.Client(api_key=st.session_state.api_key)
            for name in arquivos_para_deletar:
                try: client.files.delete(name=st.session_state.uploaded_files_info[name])
                except: pass
                del st.session_state.uploaded_files_info[name]
            st.rerun()

        if st.button("🗑️ Limpar Tudo"):
            if st.session_state.api_key:
                client = genai.Client(api_key=st.session_state.api_key)
                for f_uri in st.session_state.uploaded_files_info.values():
                    try: client.files.delete(name=f_uri)
                    except: pass
            st.session_state.uploaded_files_info = {}
            st.session_state.chat_history = []
            st.rerun()

st.title("🤖 Agente Inteligente Multi-Documentos")
st.caption("Faça perguntas restritas à sua base de dados atualizada na barra lateral.")

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Faça sua pergunta aqui..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        try:
            client = genai.Client(api_key=st.session_state.api_key)
            active_files_objects = [client.files.get(name=uri) for uri in st.session_state.uploaded_files_info.values()]
            
            system_instruction = (
                "Você é um assistente ultraestrito focado exclusivamente nos documentos anexados a esta conversa. Seu objetivo é tirar dúvidas do usuário de forma clara e direta."
                "\nRegras Absolutas:"
                "\n1. Baseie suas respostas ÚNICA e EXCLUSIVAMENTE nas informações contimas nos arquivos fornecidos pelo usuário."
                "\n2. Se a resposta para a pergunta não estiver explicitamente descrita nos documentos, responda exatamente: 'Desculpe, não encontrei essa informação na base de conhecimento fornecida.'"
                "\n3. Nunca invente dados ou use conhecimentos externos da internet."
                "\n4. Se o usuário perguntar sobre assuntos aleatórios não cobertos pelos documentos, recuse educadamente."
            )
            
            contents_payload = []
            for f_obj in active_files_objects:
                contents_payload.append(f_obj)
            
            for hist in st.session_state.chat_history[-4:-1]:
                contents_payload.append(f"{hist['role'].upper()}: {hist['content']}")
            
            contents_payload.append(f"USER QUESTION: {prompt}")
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=contents_payload,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0
                )
            )
            
            full_response = response.text
            message_placeholder.markdown(full_response)
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            st.error(f"Erro ao processar: {e}")
