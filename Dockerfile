# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY ./simulator/app /app

# Se sua simulator/app/simple_server.py tivesse dependências externas (ex: Flask), você as instalaria aqui:
# RUN pip install --no-cache-dir -r requirements_app.txt
# (e teria um requirements_app.txt dentro da pasta app/)

# A variável de ambiente APP_PORT não é estritamente necessária aqui,
# pois o servidor já está codificado para a porta 80.
# Mas se quisesse torná-la configurável no build:
# ENV APP_PORT=80

EXPOSE 80 

# Comando para rodar a aplicação quando o container iniciar
CMD ["python", "simple_server.py"]
