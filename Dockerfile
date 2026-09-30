# Usa uma imagem oficial leve do Python 3.10
FROM python:3.10-slim

# Instala dependências de sistema, incluindo o git (necessário para clonar os repositórios)
# O build-essential é útil para compilar pacotes C como o tree-sitter, se necessário.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia primeiro os requisitos para otimizar o cache de build do Docker
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o restante do código para o container
COPY . .

# Cria os diretórios necessários caso não existam
RUN mkdir -p data llm/output

# Define o Python como entrypoint padrão
ENTRYPOINT ["python"]
CMD ["run_pipeline_interactive.py"]
