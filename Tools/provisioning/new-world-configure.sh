#!/bin/bash
set -euo pipefail
id gamer >/dev/null 2>&1 || useradd -m -s /bin/bash gamer
usermod -aG audio,video,input,render gamer
install -d /etc/X11/xorg.conf.d /etc/lightdm/lightdm.conf.d
cat > /etc/X11/xorg.conf.d/20-nvidia-headless.conf <<'EOF'
Section "Device"
    Identifier "NVIDIA L4"
    Driver "nvidia"
    BusID "PCI:1:0:0"
    Option "AllowEmptyInitialConfiguration" "true"
EndSection
Section "Screen"
    Identifier "Headless"
    Device "NVIDIA L4"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Virtual 1920 1080
    EndSubSection
EndSection
EOF
cat > /etc/lightdm/lightdm.conf.d/50-gaming.conf <<'EOF'
[Seat:*]
autologin-user=gamer
autologin-user-timeout=0
user-session=xfce
xserver-command=X -nolisten tcp
EOF
install -d -o gamer -g gamer /home/gamer/.config/{sunshine,pulse,autostart,systemd/user}
chmod 700 /home/gamer/.config/sunshine
cat > /home/gamer/.config/pulse/default.pa <<'EOF'
.include /etc/pulse/default.pa
load-module module-null-sink sink_name=game_audio sink_properties=device.description=GameAudio rate=48000 channels=2
set-default-sink game_audio
EOF
cat > /home/gamer/.config/sunshine/sunshine.conf <<'EOF'
sunshine_name = new-world-capture
origin_web_ui_allowed = pc
upnp = disabled
capture = x11
encoder = nvenc
wan_encryption_mode = 2
lan_encryption_mode = 2
EOF
cat > /home/gamer/.config/autostart/gaming-stream.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Gaming streaming service
Exec=sh -c "xrandr --output DVI-D-0 --mode 1920x1080 --rate 60 --pos 0x0; xset s off; xset -dpms; systemctl --user import-environment DISPLAY XAUTHORITY; systemctl --user start sunshine.service"
EOF
cat > /home/gamer/.config/autostart/steam.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Steam
Exec=steam -silent
EOF
chown -R gamer:gamer /home/gamer/.config
printf 'uinput\n' > /etc/modules-load.d/sunshine.conf
modprobe uinput
loginctl enable-linger gamer
# Desktop autostart starts Sunshine only after X11 and its authentication are ready.
systemctl enable lightdm
