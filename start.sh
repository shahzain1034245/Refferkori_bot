#!/bin/bash
apt-get update && apt-get install -y sqlite3 libsqlite3-dev
pip install -r requirements.txt
python main.py
touch start.sh
echo "#!/bin/bash" > start.sh
echo "pip install -r requirements.txt" >> start.sh
echo "python main.py" >> start.sh
chmod +x start.sh
