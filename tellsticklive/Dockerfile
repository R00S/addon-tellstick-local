ARG BUILD_FROM=ghcr.io/erik73/base-python/amd64:4.0.8
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION
ENV LANG=C.UTF-8

# Install Telldus library for TellStick (using same approach as in hassio docker installation)
RUN apk add --no-cache \
        confuse=3.3-r4 \
        libftdi1=1.5-r4 \
        libstdc++=14.2.0-r6 \
        socat=1.8.0.3-r1 \
    && apk add --no-cache --virtual .build-dependencies \
        argp-standalone=1.5.0-r1 \
        build-base=0.5-r3 \
        cmake=3.31.7-r1 \
        confuse-dev=3.3-r4 \
        gcc=14.2.0-r6 \
        git=2.49.1-r0 \
        libftdi1-dev=1.5-r4 \
    && ln -s /usr/include/libftdi1/ftdi.h /usr/include/ftdi.h \
    && mkdir -p /usr/src \
    && cd /usr/src \
    && git clone -b master --depth 1 https://github.com/erik73/telldus \
    && cd telldus/telldus-core \
    && sed -i \
        "/\<sys\/socket.h\>/a \#include \<sys\/select.h\>" \
        common/Socket_unix.cpp \
    && python3 -c " \
# Patch ProtocolNexa.cpp: repeat learn signal for TellStick Duo (PID 0x0c31) \
# Same approach as existing workaround for old TellStick (PID 0x0c30, FW<=2) \
# Some receivers (e.g. Luxorparts 50969) need multiple transmissions to learn \
with open('service/ProtocolNexa.cpp', 'r') as f: \
    content = f.read() \
old = '\t\t}\n\t\treturn str;\n\t}\n\treturn getStringSelflearning(method, data);' \
new = ('\t\t} else if (ts->pid() == 0x0c31) {\n' \
       '\t\t\t// TellStick Duo: repeat learn signal for receivers that need\n' \
       '\t\t\t// multiple transmissions for reliable learning\n' \
       '\t\t\tfor (int i = 0; i < 5; ++i) {\n' \
       '\t\t\t\tcontroller->send(str);\n' \
       '\t\t\t}\n' \
       '\t\t}\n' \
       '\t\treturn str;\n' \
       '\t}\n' \
       '\treturn getStringSelflearning(method, data);') \
assert old in content, 'Patch target not found in ProtocolNexa.cpp - telldus-core source may have changed' \
content = content.replace(old, new, 1) \
with open('service/ProtocolNexa.cpp', 'w') as f: \
    f.write(content) \
print('ProtocolNexa.cpp patched: TellStick Duo learn signal repetition added') \
" \
    && grep -q 'pid() == 0x0c31' service/ProtocolNexa.cpp \
    && cmake . \
        -DBUILD_LIBTELLDUS-CORE=ON \
        -DBUILD_TDADMIN=OFF \
        -DBUILD_TDTOOL=ON \
        -DGENERATE_MAN=OFF \
        -DFORCE_COMPILE_FROM_TRUNK=ON \
        -DFTDI_LIBRARY=/usr/lib/libftdi1.so \
    && make \
    && make install \
    && pip install --no-cache-dir \
       tellcore-py \
    && apk del .build-dependencies \
    && rm -rf /usr/src/telldus \
    && cd /

# Bundle companion integration (pre-copied into rootfs/usr/share/tellstick_local/ by CI before build)
# integration.sh copies it to /config/custom_components/tellstick_local/ at container startup

# Copy data for add-on (includes rootfs/usr/share/tellstick_local/ bundled by CI)
COPY rootfs /

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="Erik Hilton <erikhilton73@gmail.com>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Erik73 Hassio-Addons" \
    org.opencontainers.image.authors="Erik Hilton <erikhilton73@gmail.com>" \
    org.opencontainers.image.licenses="GPL-3.0-or-later" \
    org.opencontainers.image.url="https://github.com/erik73/hassio-addons" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
