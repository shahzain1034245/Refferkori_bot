echo "#!/bin/bash" > start.sh
echo "pip install -r requirements.txt" >> start.sh
echo "python main.py" >> start.sh
chmod +x start.sh
