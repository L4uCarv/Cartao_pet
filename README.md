# Cartão Pet

Aplicação em Streamlit para gestão de saúde pet.

## Requisitos

- Python 3.10+
- Dependências em [requirements.txt](requirements.txt)

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy no Streamlit Cloud

1. Faça upload deste repositório para o GitHub.
2. Crie um app no Streamlit Community Cloud.
3. Conecte o repositório.
4. Configure as secrets abaixo no painel do Streamlit Cloud:

```toml
[supabase]
url = "https://SEU-PROJETO.supabase.co"
key = "SUA_CHAVE_ANON_PUBLIC"

[email]
remetente = "seu-email@gmail.com"
senha_app = "SUA_SENHA_DE_APP"
```

5. Inicie o deploy.

> A aplicação já lê as variáveis de ambiente e secrets do Streamlit, então funciona tanto localmente quanto em部署.
