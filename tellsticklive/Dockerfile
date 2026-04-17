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
        libstdc++=15.2.0-r3 \
        socat=1.8.1.1-r0 \
    && apk add --no-cache --virtual .build-dependencies \
        argp-standalone=1.5.0-r1 \
        build-base=0.5-r4 \
        cmake=4.2.3-r0 \
        confuse-dev=3.3-r4 \
        gcc=15.2.0-r3 \
        git=2.53.0-r1 \
        libftdi1-dev=1.5-r4 \
    && ln -s /usr/include/libftdi1/ftdi.h /usr/include/ftdi.h \
    && mkdir -p /usr/src \
    && cd /usr/src \
    && git clone -b master --depth 1 https://github.com/erik73/telldus \
    && cd telldus/telldus-core \
    && sed -i \
        "/\<sys\/socket.h\>/a \#include \<sys\/select.h\>" \
        common/Socket_unix.cpp \
    && python3 -c "f=open('service/ProtocolNexa.cpp'); c=f.read(); f.close(); old='\t\t}\n\t\treturn str;\n\t}\n\treturn getStringSelflearning(method, data);'; new='\t\t} else if (ts->pid() == 0x0c31) {\n\t\t\t// TellStick Duo: use firmware-level repeat for picky receivers\n\t\t\tstr.insert(0, 1, 2);  // Repeat two times\n\t\t\tstr.insert(0, 1, (char)0x52);  // R prefix\n\t\t\tfor (int i = 0; i < 5; ++i) {\n\t\t\t\tcontroller->send(str);\n\t\t\t}\n\t\t}\n\t\treturn str;\n\t}\n\treturn getStringSelflearning(method, data);'; assert old in c, 'Patch target not found in ProtocolNexa.cpp'; c=c.replace(old,new,1); f=open('service/ProtocolNexa.cpp','w'); f.write(c); f.close(); print('ProtocolNexa.cpp patched: TellStick Duo learn signal with R-prefix added')" \
    && grep -q 'pid() == 0x0c31' service/ProtocolNexa.cpp \
    && python3 -c "h=open('common/Strings.h').read(); marker='std::string wideToString(const std::wstring &input);'; assert marker in h, 'Patch target not found in Strings.h'; h=h.replace(marker, marker+'\n\tstd::wstring charToWstringRaw(const char *value, size_t length);\n\tstd::string wideToStringRaw(const std::wstring &input);'); open('common/Strings.h','w').write(h); print('Strings.h patched'); s=open('common/Strings.cpp').read(); raw_funcs='\n// Binary-safe (Latin-1) clones for tdSendRawCommand -- byte 0-255 maps 1:1 to wchar_t (no iconv)\nstd::wstring TelldusCore::charToWstringRaw(const char *value, size_t length) {\n\tstd::wstring result;\n\tresult.reserve(length);\n\tfor (size_t i = 0; i < length; ++i) {\n\t\tresult += static_cast<wchar_t>(static_cast<unsigned char>(value[i]));\n\t}\n\treturn result;\n}\n\nstd::string TelldusCore::wideToStringRaw(const std::wstring &input) {\n\tstd::string result;\n\tresult.reserve(input.size());\n\tfor (size_t i = 0; i < input.size(); ++i) {\n\t\tresult += static_cast<char>(input[i] & 0xFF);\n\t}\n\treturn result;\n}\n'; s+=raw_funcs; open('common/Strings.cpp','w').write(s); print('Strings.cpp patched'); sock=open('common/Socket_unix.cpp').read(); old_read='return TelldusCore::charToWstring(msg.c_str());'; new_read='return TelldusCore::charToWstringRaw(msg.data(), msg.size());'; assert old_read in sock, 'Patch target not found in Socket_unix.cpp'; sock=sock.replace(old_read, new_read, 1); open('common/Socket_unix.cpp','w').write(sock); print('Socket_unix.cpp patched'); dm=open('service/DeviceManager.cpp').read(); old_send='retval = controller->send(TelldusCore::wideToString(command));'; new_send='retval = controller->send(TelldusCore::wideToStringRaw(command));'; count=dm.count(old_send); assert count==2, 'Expected 2 occurrences in DeviceManager.cpp, found %d' % count; dm=dm.replace(old_send, new_send); open('service/DeviceManager.cpp','w').write(dm); print('DeviceManager.cpp patched'); print('All binary-safe IPC patches applied successfully')" \
    && grep -q 'charToWstringRaw' common/Strings.h \
    && grep -q 'charToWstringRaw' common/Strings.cpp \
    && grep -q 'charToWstringRaw' common/Socket_unix.cpp \
    && grep -q 'wideToStringRaw' service/DeviceManager.cpp \
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
    maintainer="R00S" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="R00S" \
    org.opencontainers.image.authors="R00S" \
    org.opencontainers.image.licenses="GPL-3.0-or-later" \
    org.opencontainers.image.url="https://github.com/R00S/addon-tellstick-local" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
