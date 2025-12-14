#!/bin/bash
echo "=========================================="
echo "   CyRide Network Diagnostic Tool"
echo "=========================================="

# 1. Test Local Connection (Proves the app is working)
echo "[1] Testing Local Connection (localhost:80)..."
HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}\n" http://localhost)
if [ "$HTTP_CODE" == "200" ]; then
    echo "    SUCCESS: App is replying locally (HTTP 200)."
else
    echo "    FAILURE: App returned HTTP $HTTP_CODE (Expected 200)."
fi

# 2. Check Internal Firewall (UFW)
echo ""
echo "[2] Checking Firewall (UFW)..."
if command -v ufw > /dev/null; then
    STATUS=$(sudo ufw status | grep "Status: active")
    if [ ! -z "$STATUS" ]; then
        echo "    UFW is ACTIVE."
        # Check if 80 is allowed
        ALLOWED=$(sudo ufw status | grep "80.*ALLOW")
        if [ -z "$ALLOWED" ]; then
            echo "    CRITICAL: Port 80 is BLOCKED."
            echo "    -> Run: sudo ufw allow 80/tcp"
        else
            echo "    SUCCESS: Port 80 is ALLOWED in UFW."
        fi
    else
        echo "    WARNING: UFW is INACTIVE (Firewall is off locally)."
    fi
else
    echo "    UFW not installed. Skipping."
fi

# 3. Check for Cloud/External IP
echo ""
echo "[3] Connection Information"
INTERNAL_IP=$(hostname -I | awk '{print $1}')
EXTERNAL_IP=$(curl -s ifconfig.me)
echo "    Internal IP: $INTERNAL_IP"
echo "    External IP: $EXTERNAL_IP"
echo ""
echo "    TRY CONNECTING HERE -> http://$EXTERNAL_IP"
echo ""

# 4. Cloud Firewall Warning
if [[ "$INTERNAL_IP" == 10.* ]] || [[ "$INTERNAL_IP" == 172.* ]]; then
    echo "    NOTE: You have a private IP ($INTERNAL_IP)."
    echo "    If you are on Google Cloud, AWS, or Azure, you MUST allow"
    echo "    Port 80 in your Cloud Console Security Groups / Firewall Rules."
fi
echo "=========================================="
