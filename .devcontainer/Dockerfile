FROM mcr.microsoft.com/devcontainers/base:ubuntu

# System packages (incl. redis + tcpdump for labs)
RUN apt-get update && apt-get install -y \
    curl git python3 python3-pip python3-venv \
    redis-server tcpdump \
 && rm -rf /var/lib/apt/lists/*

# --- PERSISTENT BASH HISTORY (root + vscode) ---
RUN mkdir -p /commandhistory \
 && chmod 777 /commandhistory \
 && touch /commandhistory/.bash_history \
 && chmod 666 /commandhistory/.bash_history \
 && printf '\n# Persistent bash history (devcontainer)\nexport HISTFILE=/commandhistory/.bash_history\nexport HISTSIZE=100000\nexport HISTFILESIZE=200000\nshopt -s histappend\nPROMPT_COMMAND="history -a; history -n; $PROMPT_COMMAND"\n' \
    >> /etc/bash.bashrc

# Install project (editable) + dev deps from pyproject.toml
# NOTE: This relies on your pyproject optional deps: dev = [...]
WORKDIR /workspaces/pyrad-server
COPY pyproject.toml README*.md LICENSE.rst ./
COPY src ./src
RUN pip install --no-cache-dir --break-system-packages -e ".[dev]"

# (optional) install your pyrad fork
# ARG GIT_REF=developmnet-slieberth
# RUN pip install --no-cache-dir --break-system-packages \
#     git+https://github.com/slieberth/pyrad.git@${GIT_REF}

# Entrypoint
COPY .devcontainer/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
