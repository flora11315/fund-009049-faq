# 云平台部署说明

这个原型已经支持部署到常见云平台。服务入口是 `src/web_server.py`，前端和 API 是同一个进程提供。

## 运行参数

云平台通常会注入 `PORT` 环境变量。当前服务支持：

```text
HOST=0.0.0.0
PORT=8000
APP_USERNAME=可选用户名
APP_PASSWORD=可选密码
```

如果设置了 `APP_USERNAME` 和 `APP_PASSWORD`，页面和 API 会启用基础认证。正式分享建议开启。

## Docker 部署

构建镜像：

```bash
docker build -t fund-009049-faq .
```

本地运行：

```bash
docker run --rm -p 8000:8000 \
  -e APP_USERNAME=demo \
  -e APP_PASSWORD=change-me \
  fund-009049-faq
```

打开：

```text
http://127.0.0.1:8000
```

## 平台选择建议

推荐优先选支持 Docker 或 Python Web Service 的平台，例如：

- 阿里云 ECS / 腾讯云 CVM / 华为云 ECS：适合长期内网或公网部署，可控性强。
- Render / Railway / Fly.io：适合快速演示和小团队分享。
- Google Cloud Run / AWS App Runner / Azure Container Apps：适合容器化部署和自动扩缩容。

## Render/Railway 类平台

如果平台支持从 Git 仓库直接部署：

1. 把项目推到 GitHub/GitLab。
2. 新建 Web Service。
3. 选择 Dockerfile 部署，或选择 Python Web Service。
4. 设置启动命令：`python src/web_server.py`。
5. 设置环境变量：`HOST=0.0.0.0`，`APP_USERNAME`，`APP_PASSWORD`。
6. 部署完成后访问平台生成的 HTTPS 地址。

## 云服务器部署

在云服务器上安装 Docker 后：

```bash
git clone <你的仓库地址>
cd <项目目录>
docker build -t fund-009049-faq .
docker run -d --name fund-009049-faq \
  --restart unless-stopped \
  -p 8000:8000 \
  -e APP_USERNAME=demo \
  -e APP_PASSWORD=change-me \
  fund-009049-faq
```

如果需要正式 HTTPS 域名，建议在前面加 Nginx/Caddy 反向代理。

## 注意事项

- 当前采集结果写在本地 JSON 文件中。容器平台如果没有持久化磁盘，重新部署后会回到镜像内初始数据。
- `/api/collect` 会从公开网站拉取数据，云平台需要允许出站访问互联网。
- 这是 FAQ 原型，不是生产投顾系统。正式对外前，应补充登录、访问日志、错误监控、限流和合规审核。
- 健康检查地址：`/healthz`。
