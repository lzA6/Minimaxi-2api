# Dockerfile (v9.0 - 回归初心，全程 Root)

FROM python:3.10-slim

# 从头到尾，我们都是 root。
# WORKDIR /app
# RUN useradd -m user
# USER user
# 这些都是狗屎，忘掉它们。

WORKDIR /app

# 1. 安装系统依赖 (以 root 身份)
RUN apt-get update && apt-get install -y \
    # 这里列出所有 Playwright 可能需要的依赖，以防万一
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 2. 复制并安装 Python 依赖 (以 root 身份)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 关键修正：以 root 身份安装 Playwright 及其所有依赖
# 这次，它有全部权限去安装任何它想装的东西
RUN playwright install --with-deps chromium

# 4. 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8085

# 启动命令
# Playwright 启动浏览器时需要 --no-sandbox 参数，因为我们现在是 root
# 我们在 Python 代码里已经加了，这里只是提醒
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8085"]
