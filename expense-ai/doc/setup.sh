sudo apt update
sudo apt install -y ca-certificates curl git

echo "Docker’s official repository"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

echo "Docker’s installation"

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo systemctl status docker --no-pager
sudo usermod -aG docker ubuntu

cd /home/ubuntu
git clone --depth 1 https://github.com/ravik775/ai-architecture-lab.git
cd ai-architecture-lab
ls -la
find . -maxdepth 2 -iname "docker-compose*.yml" -o -iname "compose*.yaml"
openssl rand -base64 18
exit


docker --version
docker compose version
docker run --rm hello-world

cat > .end
chmod 600 .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs app

???
sudo ufw status
sudo ufw allow OpenSSH
sudo ufw allow 8000/tcp
sudo ufw enable
???
Useful:

# Show running containers
docker compose ps

# Show recent logs
docker compose logs --tail=100

# Restart the stack
docker compose restart

# Stop containers without deleting them
docker compose stop

# Stop and remove containers/network
docker compose down

# Update code and redeploy
git pull
docker compose up -d --build

# See resource consumption
docker stats

# Inspect failed containers
docker compose ps -a
docker compose logs --tail=200 app