#!/bin/bash

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🔨 Iniciando compilación para Linux...${NC}\n"

# Limpiar builds anteriores
rm -rf build dist *.spec

# Compilar para Linux
pyinstaller --onefile --name hardwareMonitor main.py

# Copiar ejecutable Linux a la raíz
cp dist/hardwareMonitor ./hardwareMonitor-Linux
chmod +x hardwareMonitor-Linux

# Resumen
echo -e "\n${BLUE}════════════════════════════════════════${NC}"
echo -e "${GREEN}📊 Compilación completada${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"

SIZE=$(du -h hardwareMonitor-Linux | cut -f1)
echo -e "${GREEN}✓${NC} Linux: hardwareMonitor-Linux ($SIZE)"

echo -e "\n${YELLOW}Para Windows y macOS:${NC}"
echo -e "  GitHub Actions compilará automáticamente cuando hagas push de un tag"
echo -e "\n${YELLOW}Próximos pasos:${NC}"
echo -e "  1. git add ."
echo -e "  2. git commit -m 'Nueva versión'"
echo -e "  3. git tag v0.0.X"
echo -e "  4. git push origin main --tags"
echo -e "\n${BLUE}════════════════════════════════════════${NC}"