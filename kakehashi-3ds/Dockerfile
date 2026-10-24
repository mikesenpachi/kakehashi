# Build image for the kakehashi 3DS plugin: devkitARM, libctru, CTRPluginFramework and 3gxtool.
# amd64, because ThePixellizerOSS builds 3gxtool only for x86_64 Linux (Docker emulates it on Apple Silicon).
FROM --platform=linux/amd64 devkitpro/devkitarm:20260610

RUN printf '\n[thepixellizeross-lib]\nServer = https://thepixellizeross.gitlab.io/packages/any\nSigLevel = Optional\n\n[thepixellizeross-linux]\nServer = https://thepixellizeross.gitlab.io/packages/x86_64/linux\nSigLevel = Optional\n' \
        >> /opt/devkitpro/pacman/etc/pacman.conf \
    && dkp-pacman -Sy --noconfirm libctrpf 3gxtool \
    && dkp-pacman -Scc --noconfirm

WORKDIR /plugin
