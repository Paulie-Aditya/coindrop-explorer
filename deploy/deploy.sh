#!/usr/bin/env bash
# Run once on the EC2 instance:
#   bash deploy.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="/home/ubuntu/coindrop-explorer"
SERVICE_NAME="coindrop-explorer"

echo "==> Checking port 8002 is free (8000 = api.coindrop.cc, 8001 = coindrop-backend)"
if sudo ss -tlnp | grep -q ':8002\b'; then
    echo "    ⚠️  port 8002 is already in use -- pick another and update the service + nginx files"; exit 1
fi

echo "==> Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx

echo "==> Creating virtualenv"
python3 -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo "==> Running SQL schema"
# Edit the credentials below or run manually
# mysql -h YOUR_DB_HOST -u YOUR_DB_USER -p YOUR_DB_NAME < "$PROJECT_DIR/sql/explorer_schema.sql"
echo "    ⚠️  Run sql/explorer_schema.sql manually against your coindrop DB"

echo "==> Copying .env"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "    ⚠️  Edit $PROJECT_DIR/.env before starting the service"
    echo "    ⚠️  EXPLORER_SIGNING_SECRET must match the bot's and coindrop-backend's"
fi

echo "==> Installing systemd service"
sudo cp "$PROJECT_DIR/deploy/coindrop-explorer.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "==> Installing nginx config"
sudo cp "$PROJECT_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$SERVICE_NAME"
sudo ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/$SERVICE_NAME"
sudo nginx -t

echo ""
echo "Done. Next steps:"
echo "  1. Edit $PROJECT_DIR/.env"
echo "  2. sudo systemctl start $SERVICE_NAME && sudo systemctl reload nginx"
echo "  3. sudo certbot --nginx -d explorer.coindrop.cc   (needs the DNS record live first)"
echo "  4. curl https://explorer.coindrop.cc/health"
