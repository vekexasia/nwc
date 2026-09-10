#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
ufw allow 22/tcp
ufw allow from YOUR_CLIENT_IP to any port 47984 proto tcp
ufw allow from YOUR_CLIENT_IP to any port 47989 proto tcp
ufw allow from YOUR_CLIENT_IP to any port 48010 proto tcp
ufw allow from YOUR_CLIENT_IP to any port 47998:48000 proto udp
ufw --force enable
apt-get install -y --no-install-recommends xfce4 xserver-xorg lightdm dbus-x11 pulseaudio pulseaudio-utils pavucontrol mesa-utils vulkan-tools ffmpeg steam-installer steam-devices libnvidia-gl-580-server libnvidia-gl-580-server:i386 libnvidia-encode-580-server libnvidia-encode-580-server:i386 xserver-xorg-video-nvidia-580-server x11-xserver-utils xauth
curl -fL https://github.com/LizardByte/Sunshine/releases/download/v2025.924.154138/sunshine-ubuntu-24.04-amd64.deb -o /root/sunshine-ubuntu-24.04-amd64.deb
apt-get install -y /root/sunshine-ubuntu-24.04-amd64.deb
