#!/bin/bash

set -e  

echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "Installing prerequisites..."
sudo apt install python3 python3-pip python3-venv git build-essential libatlas-base-dev libsqlite3-dev -y

echo "Cloning HomeBot repository..."
git clone https://github.com/buckster123/HomeBot.git
cd HomeBot

echo "Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing dependencies (excluding torch for special handling)..."
pip install \
    streamlit==1.38.0 \
    openai==1.40.0 \
    passlib==1.7.4 \
    python-dotenv==1.0.1 \
    ntplib==0.4.0 \
    pygit2==1.15.0 \
    requests==2.32.3 \
    black==24.8.0 \
    numpy==2.0.1 \
    sentence-transformers==3.0.1 \
    jsbeautifier==1.15.1 \
    cssbeautifier==1.15.1 \
    pyyaml==6.0.2 \
    sqlparse==0.5.1 \
    beautifulsoup4==4.12.3

echo "Installing torch with CPU wheels for Raspberry Pi..."
pip install torch==2.4.0 --extra-index-url https://download.pytorch.org/whl/cpu

echo "Installing SQLite-vec extension for embeddings..."
cd ..
git clone https://github.com/asg017/sqlite-vec.git
cd sqlite-vec
make loadable-dist
cp vec0.so ../HomeBot/
cd ../HomeBot

echo "Configuring .env file..."
read -p "Enter your XAI_API_KEY: " XAI_KEY
read -p "Enter your LANGSEARCH_API_KEY (optional, press enter if none): " LANG_KEY

cat > .env << EOF
XAI_API_KEY=$XAI_KEY
LANGSEARCH_API_KEY=$LANG_KEY
EOF

echo "Installation complete! To run HomeBot:"
echo "cd HomeBot"
echo "source venv/bin/activate"
echo "streamlit run app.py"
echo "Access at http://<your-pi-ip>:8501"
```
