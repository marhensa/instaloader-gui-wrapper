#!/bin/bash
echo "========================================"
echo "Building Instaloader GUI Wrapper"
echo "========================================"

# Check if running in virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install PyInstaller if not installed
if ! pip show pyinstaller > /dev/null 2>&1; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

# Build the executable
echo "Building executable with PyInstaller..."
pyinstaller --onefile --windowed --name "Instaloader-GUI-Wrapper" run.py

echo ""
echo "========================================"
echo "PyInstaller build complete!"
echo "Executable: dist/Instaloader-GUI-Wrapper"
echo "========================================"

# Ask if user wants to create AppImage
read -p "Create AppImage? (y/n): " create_appimage

if [[ "$create_appimage" == "y" || "$create_appimage" == "Y" ]]; then
    echo ""
    echo "Creating AppImage..."
    
    # Create AppDir structure
    APPDIR="Instaloader-GUI-Wrapper.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
    
    # Copy executable
    cp dist/Instaloader-GUI-Wrapper "$APPDIR/usr/bin/"
    
    # Create desktop file
    cat > "$APPDIR/usr/share/applications/instaloader-gui-wrapper.desktop" << EOF
[Desktop Entry]
Name=Instaloader GUI Wrapper
Exec=Instaloader-GUI-Wrapper
Icon=instaloader-gui-wrapper
Type=Application
Categories=Utility;Network;
Comment=Download Instagram content with a GUI
StartupWMClass=instaloader-gui-wrapper
EOF
    
    # Copy desktop file to AppDir root (required)
    cp "$APPDIR/usr/share/applications/instaloader-gui-wrapper.desktop" "$APPDIR/"
    
    # Create a simple icon if none exists (placeholder)
    if [ -f "assets/icon.png" ]; then
        cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/instaloader-gui-wrapper.png"
        cp assets/icon.png "$APPDIR/instaloader-gui-wrapper.png"
    else
        echo "Warning: No icon.png found. Using placeholder."
        # Create a simple placeholder icon (1x1 transparent PNG)
        echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > "$APPDIR/instaloader-gui-wrapper.png"
    fi
    
    # Create AppRun script
    cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
exec "${HERE}/usr/bin/Instaloader-GUI-Wrapper" "$@"
EOF
    chmod +x "$APPDIR/AppRun"
    
    # Download appimagetool if not present
    if [ ! -f "appimagetool-x86_64.AppImage" ]; then
        echo "Downloading appimagetool..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        chmod +x appimagetool-x86_64.AppImage
    fi
    
    # Create AppImage
    ARCH=x86_64 ./appimagetool-x86_64.AppImage "$APPDIR"
    
    # Cleanup
    rm -rf "$APPDIR"
    
    echo ""
    echo "========================================"
    echo "AppImage created!"
    echo "File: Instaloader-GUI-Wrapper-x86_64.AppImage"
    echo "========================================"
fi
