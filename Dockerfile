FROM httpd:2.4.54-alpine
ENV DOCKER=true

RUN apk add \ 
    git \
    python3 \
    py3-requests

EXPOSE 80

RUN mkdir -p /app/tests
VOLUME /app/tests
VOLUME /app/w3id.org
WORKDIR /app
RUN git clone --depth 1 https://github.com/perma-id/w3id.org 

COPY httpd.conf /usr/local/apache2/conf/httpd.conf
COPY testW3id.py testW3id.py
RUN chmod +x testW3id.py

ENTRYPOINT [ "python3", "/app/testW3id.py" ]
