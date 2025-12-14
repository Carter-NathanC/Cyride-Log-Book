name: Deploy Web Interface

on:
  workflow_dispatch:
  push:
    paths:
      - 'scripts/web_interface.py'
      - 'requirements.txt'
      - '.github/workflows/deploy_web.yml'

jobs:
  deploy:
    runs-on: self-hosted
    steps:
    - name: Checkout
      uses: actions/checkout@v3

    - name: Install Python Dependencies
      run: |
        /usr/bin/python3 -m pip install --upgrade pip
        /usr/bin/python3 -m pip install -r requirements.txt

    - name: Deploy Web Service
      run: |
        SCRIPT_PATH=$(pwd)/scripts/web_interface.py
        USER_NAME=$(whoami)
        
        cat <<EOF > cyride-web.service
        [Unit]
        Description=CyRide Web Interface
        After=network.target

        [Service]
        Type=simple
        User=$USER_NAME
        ExecStart=/usr/bin/python3 -u $SCRIPT_PATH
        Restart=always
        RestartSec=10
        Environment=CYRIDE_BASE_DIR=/home/sdr/CYRIDE
        # Standard logging
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=multi-user.target
        EOF

        sudo cp cyride-web.service /etc/systemd/system/cyride-web.service
        sudo systemctl daemon-reload
        sudo systemctl enable cyride-web.service
        sudo systemctl restart cyride-web.service
