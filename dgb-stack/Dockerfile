FROM moonkyu23403/digibyte:latest AS digibyte-bins


FROM debian:bookworm-slim AS ckpool-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    yasm \
    autoconf \
    automake \
    libtool \
    pkgconf \
    libzmq3-dev \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY _ref_ckpool /src/ckpool
WORKDIR /src/ckpool
RUN find . -type f \( -name "*.sh" -o -name "*.ac" -o -name "*.am" -o -name "*.m4" \) -exec sed -i 's/\r$//' {} + && \
    sh ./autogen.sh && ./configure && make -j"$(nproc)"


FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor curl libzmq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=digibyte-bins /usr/bin/digibyted /usr/bin/digibyted
COPY --from=digibyte-bins /usr/bin/digibyte-cli /usr/bin/digibyte-cli

COPY --from=ckpool-builder /src/ckpool/src/ckpool /usr/local/bin/ckpool
COPY --from=ckpool-builder /src/ckpool/src/ckpmsg /usr/local/bin/ckpmsg

COPY dgb-stack/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dgb-stack/app ./app
COPY dgb-stack/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY dgb-stack/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8085 3335

ENTRYPOINT ["/entrypoint.sh"]