# Use Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Node.js for Angular build
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy package files and install npm dependencies
COPY package*.json ./
RUN npm install

# Copy all source code
COPY . .

# Build Angular frontend
RUN npm run build

# Create static directory and copy built files
RUN mkdir -p /app/static
RUN cp -r dist/mohamy-masry/browser/* /app/static/

# Expose port
EXPOSE 7860

# Set environment variable for port
ENV PORT=7860

# Run the application
CMD ["uvicorn", "mohamy:app", "--host", "0.0.0.0", "--port", "7860"]
