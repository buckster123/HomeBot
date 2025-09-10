#!/bin/bash

# install.sh: Automated Setup Script for HomeBot on Raspberry Pi OS (Desktop or Lite)
# This script installs HomeBot on a fresh Raspberry Pi OS install. It handles dependencies,
# Python setup, repo cloning, and configuration. Run with sudo for system-wide installs.
# Supports headless (Lite) mode – access via browser on another device.

# Exit on errors
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables (customize if needed)
REPO_URL="https://github.com/buckster123/HomeBot.git"  # Replace with your actual repo URL
APP_DIR="$HOME/HomeBot"
VENV_DIR="$APP_DIR/venv"
PYTHON_VERSION="3.12.0"  # Target version; script installs if missing
SQLITE_VEC_URL="https://github.com/asg017/sqlite-vec/releases/latest/download/vec0.so"  # Latest vec0.so

echo -e "${YELLOW}=== HomeBot Installation Script ===${NC}"
echo "This script will set up HomeBot on your Raspberry Pi. It works on both Desktop and Lite (headless) versions."
echo "You'll need internet access. For headless, access the app via http://<pi-ip>:8501 from another device."
read -p "Proceed? (y/n): " confirm
if [[ $confirm != "y" ]]; then
    echo "Installation aborted."
    exit 0
fi

# Step 1: Update System and Install Base Dependencies
echo -e "${GREEN}Step 1: Updating system and installing base dependencies...${NC}"
sudo apt update && sudo apt upgrade -y
sudo apt install -y git build-essential libatlas-base-dev libsqlite3-dev libssl-dev zlib1g-dev libbz2-dev libreadline-dev libffi-dev wget curl

# Step 2: Install Python 3.12 if not present
echo -e "${GREEN}Step 2: Checking and installing Python 3.12...${NC}"
if ! command -v python3.12 &> /dev/null; then
    echo "Python 3.12 not found. Installing from source..."
    cd /tmp
    wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
    tar -xvf Python-$PYTHON_VERSION.tgz
    cd Python-$PYTHON_VERSION
    ./configure --enable-optimizations
    make -j $(nproc)
    sudo make altinstall
    cd ~
    echo "Python 3.12 installed."
else
    echo "Python 3.12 already installed."
fi

# Step 3: Clone the Repository
echo -e "${GREEN}Step 3: Cloning the HomeBot repository...${NC}"
if [ -d "$APP_DIR" ]; then
    echo -e "${YELLOW}Directory $APP_DIR already exists. Overwrite? (y/n): ${NC}"
    read overwrite
    if [[ $overwrite == "y" ]]; then
        rm -rf "$APP_DIR"
    else
        echo "Installation aborted to avoid overwriting existing files."
        exit 0
    fi
fi
git clone $REPO_URL $APP_DIR
cd $APP_DIR

# Step 4: Create and Activate Virtual Environment
echo -e "${GREEN}Step 4: Setting up virtual environment...${NC}"
python3.12 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# Step 5: Install Python Dependencies
echo -e "${GREEN}Step 5: Installing Python packages...${NC}"
pip install --upgrade pip
pip install streamlit openai passlib python-dotenv ntplib pygit2 requests black numpy sentence-transformers torch --extra-index-url https://download.pytorch.org/whl/cpu  # CPU-only Torch for Pi

# Step 6: Download sqlite-vec Extension
echo -e "${GREEN}Step 6: Downloading sqlite-vec extension...${NC}"
mkdir -p sqlite-vec/dist
wget -O sqlite-vec/dist/vec0.so $SQLITE_VEC_URL

# Step 7: Configure Environment Variables
echo -e "${GREEN}Step 7: Configuring .env file...${NC}"
echo "Enter your xAI API Key (required; get from https://x.ai/):"
read -s XAI_KEY
echo "Enter your LangSearch API Key (optional; for web search; get from https://langsearch.com/):"
read -s LANGSEARCH_KEY

cat << EOF > .env
XAI_API_KEY=$XAI_KEY
LANGSEARCH_API_KEY=$LANGSEARCH_KEY
EOF
echo ".env file created."

# Step 8: Test and Run Instructions
echo -e "${GREEN}Installation Complete!${NC}"
echo "To run the app:"
echo "  cd $APP_DIR"
echo "  source $VENV_DIR/bin/activate"
echo "  streamlit run app.py"
echo ""
echo "Access at http://localhost:8501 (Desktop) or http://<your-pi-ip>:8501 (headless/from another device)."
echo "For headless: Find Pi IP with 'hostname -I'. Ensure port 8501 is open."
echo "First run auto-creates defaults (prompts, DB, sandbox)."
echo "Enjoy HomeBot! If issues arise, check app.log or reinstall."
echo "Sqlite-vec may need to be compiled. Ask an online grok about it, i have no clue, i just copy paste."

deactivate  # Exit venv
