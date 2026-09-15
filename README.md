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
4. Execute o script [supabase_associados.sql](supabase_associados.sql) no SQL Editor do Supabase.
5. Configure as credenciais necessárias diretamente no painel do Streamlit Cloud.
6. Inicie o deploy.

> A aplicação já lê as variáveis de ambiente e secrets do Streamlit, então funciona tanto localmente quanto em部署.
