FROM node:20

# Install Python 3.11 and system deps
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user
RUN useradd -m claude-user
WORKDIR /workspace
RUN chown -R claude-user:claude-user /workspace

USER claude-user

CMD ["claude"]
