#!/bin/bash
set -e

echo "=== Browser Automation Container Startup ==="

# Set up display
export DISPLAY=:99

# Create log directories
mkdir -p /var/log/supervisor

# Start dbus (required for Chrome)
if [ -f /var/run/dbus/pid ]; then
    rm /var/run/dbus/pid
fi
dbus-daemon --system --fork 2>/dev/null || true

# Set VNC password if provided
if [ -n "$VNC_PASSWORD" ]; then
    mkdir -p /home/browseruser/.vnc
    x11vnc -storepasswd "$VNC_PASSWORD" /home/browseruser/.vnc/passwd
    chown browseruser:browseruser /home/browseruser/.vnc/passwd
    # Update supervisor config to use password
    sed -i 's/-nopw/-rfbauth \/home\/browseruser\/.vnc\/passwd/' /etc/supervisor/supervisord.conf
fi

# Create required directories with proper permissions
echo "Creating directory structure..."

mkdir -p /home/browseruser/.conversations
mkdir -p /home/browseruser/.browser-sessions
mkdir -p /home/browseruser/Downloads
mkdir -p /home/browseruser/.vnc
mkdir -p /home/browseruser/.config

# Set ownership to browseruser
echo "Setting directory ownership..."
chown -R browseruser:browseruser /home/browseruser/.conversations
chown -R browseruser:browseruser /home/browseruser/.browser-sessions
chown -R browseruser:browseruser /home/browseruser/Downloads

# Set secure permissions
# - Conversations: readable by all (755)
# - Sessions: secure, only browseruser (700)
# - Downloads: standard (755)
echo "Setting directory permissions..."
chmod 755 /home/browseruser/.conversations
chmod 700 /home/browseruser/.browser-sessions  # Secure!
chmod 755 /home/browseruser/Downloads

# Verify mounts
echo "Verifying volume mounts..."
if [ -d "/home/browseruser/.conversations" ]; then
    echo "  ✓ Conversations directory ready"
else
    echo "  ✗ Conversations directory missing!"
fi

if [ -d "/home/browseruser/.browser-sessions" ]; then
    echo "  ✓ Sessions directory ready"
else
    echo "  ✗ Sessions directory missing!"
fi

if [ -d "/home/browseruser/Downloads" ]; then
    echo "  ✓ Downloads directory ready"
else
    echo "  ✗ Downloads directory missing!"
fi

# Create browser-use config directory with proper permissions
mkdir -p /home/browseruser/.config/browseruse
chown -R browseruser:browseruser /home/browseruser/.config

# Create symlink so browser-use can write to /root/.config/browseruse
mkdir -p /root/.config
ln -sf /home/browseruser/.config/browseruse /root/.config/browseruse
chown -R browseruser:browseruser /root/.config/browseruse

# Create fluxbox init file to disable wallpaper setting
mkdir -p /home/browseruser/.fluxbox
cat > /home/browseruser/.fluxbox/init << 'EOF'
session.screen0.rootCommand:	/usr/bin/true
EOF
chown -R browseruser:browseruser /home/browseruser/.fluxbox

# Display usage
echo "=== Volume Mount Summary ==="
echo "Conversations: /home/browseruser/.conversations → ./browser-conversations"
echo "Sessions:      /home/browseruser/.browser-sessions → ./browser-sessions"
echo "Downloads:     /home/browseruser/Downloads → ./browser-downloads"
echo "================================"

echo "Starting browser automation container..."
echo "VNC: localhost:5900"
echo "noVNC: http://localhost:6080"
echo "API: http://localhost:8001"

# Execute the command
exec "$@"