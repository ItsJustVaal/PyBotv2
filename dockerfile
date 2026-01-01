# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.57.0-noble-arm64

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot
COPY . .

# If your bot starts via bot.py, keep this.
# Otherwise change it to your real entry file.
CMD ["python", "bot.py"]
